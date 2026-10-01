# CLAUDE.md

給接手這個專案的 Claude Code（或任何工程師）快速上手用。這份文件記錄目前的架構、資料表結構、前後端欄位對應，以及幾個容易踩雷的落差與注意事項。

## 專案簡介

SOW（Statement of Work）案例知識庫。流程是：SOW PDF → Bedrock（Claude）萃取成結構化內容 → 存進 RDS PostgreSQL → 前端以案例卡片形式展示，Customer / PM / SA 三種角色可看到不同深度的內容（角色累加：Customer 只看 A，PM 看 A+B，SA 看 A+B+C）。

## 架構總覽

- **前端（案例庫，對外）**：`frontend/`，純 Vanilla JS 靜態頁面，沒有任何建置工具（無 npm/webpack/vite）。
  - `index.html`：SPA 骨架
  - `css/style.css`：樣式
  - `js/i18n.js`：中英文 UI 文案字典
  - `js/data.js`：`LABELS`（篩選代碼字典）+ `loadCases()`（向後端 fetch 真實案例資料）
  - `js/app.js`：狀態管理、渲染、事件處理（全域變數互相依賴，無模組化）
- **前端（審核頁，DRI / 主管內部用）**：`review-frontend/`，同樣是純 Vanilla JS、無建置工具，獨立於 `frontend/` 維護。
  - `dri.html` / `manager.html`：兩個幾乎一樣的殼，差別只在 `<script>window.REVIEW_MODE = 'dri' | 'manager'</script>`，實際渲染邏輯共用同一份 `js/app.js`
  - `js/data.js`：對 `backend/review.py` 的 `fetch()` 包裝（`apiGetReviewCase`/`apiSaveDraft`/`apiSubmitReview`/`apiAddComment`/`apiReturnToDri`/`apiApprove`）
  - `js/app.js`：狀態管理、渲染、事件處理；案例的 `token` 從網址 `?token=` 讀取，資料一律來自 API（無 mock、無 localStorage 案例資料）
  - 連結格式：`/review/dri.html?token={review_token}`、`/review/manager.html?token={review_token}`（Power Automate 在 Teams 卡片放的連結）。`review_token` 是 `HMAC-SHA256(REVIEW_LINK_SECRET, job_code)`，不再直接把 `job_code` 放在網址上。**`sow_document.job_code` 沒填就無法打開審核頁（API 404）**，`job_code` 已從「加分欄位」變成審核流程的必要前置條件
  - **目前仍然沒有登入驗證**——任何拿到連結的人都能操作；但姓名已經不是手動輸入了，送審人/核准人改由後端自動解析 `nda_work_station_apply` 的 email（見「已知落差」）
- **後端**：`backend/app.py`（FastAPI），共用邏輯拆在 `backend/common.py`，審核相關路由拆在 `backend/review.py`
  - `GET /api/cases`：回傳所有 `dri_status='approve'` 且 `manager_status='approve'` 的案例（含 detail），供卡片列表 + 篩選使用
  - `GET /api/cases/{sow_id}`：回傳單一已發布案例
  - `/api/review/*`：DRI / 主管審核流程用的路由，見下方「審核流程」章節
  - 用 `StaticFiles` 把 `review-frontend/` 掛載在 `/review`、`frontend/` 掛載在 `/`，同一個 server 同時服務頁面與 API（不用處理 CORS）；**掛載順序固定是 `include_router(review_router)` → `/review` mount → `/` mount**，`/` 是萬用 catch-all 必須放最後
  - 沿用 `backend/db.py` 既有的 `get_db()` / `SessionLocal`（SQLAlchemy）
- **資料庫**：AWS RDS PostgreSQL，DB 名稱 `SDXINTERN`。連線資訊在根目錄 `.env`（`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`）。**`.env` 含真實密碼，絕不能提交進版控、絕不能貼到聊天或文件裡。**
- **AI 產出格式**：`backend/json.txt` 定義的 `SOW_ANALYSIS_TOOL`（Bedrock tool-use 的 `input_schema`），描述 AI 應該產出的結構。裡面提到的 `bedrock_service.py` 目前還不存在，是規劃中、尚未實作的呼叫邏輯。
- **審核流程（Power Automate + Teams，外部串接）**：AWS 處理完成 → Power Automate 收到通知 → 發 Teams 卡片給 DRI（帶 `/review/dri.html?token=` 連結）→ DRI 編輯送出 → 回 Teams 卡片留言 → Power Automate 呼叫 `POST /api/review/cases/{token}/comments` 寫入留言、通知主管（帶 `/review/manager.html?token=` 連結）→ 主管核准或退回。**Power Automate 流程本身（觸發條件、Adaptive Card、Teams connector）不在這個 repo 裡，是在 Power Automate 網站另外設定**；這個 repo 只負責提供 `/api/review/*` 這組 API 與兩個審核頁面。

## 資料表（不只六張，以下是依實際 RDS `information_schema` 查到的現況）

| 表 | 用途 | 關鍵欄位 |
|---|---|---|
| `sow_document` | 一份 SOW 文件 = 一筆 | `id`, `file_name`, `s3_key`, `file_hash`, `page_count`, `char_count`, `model_version`, `dedup_status`, `processing_status`, `is_latest`, `version`, `edited_by`, `approved_by`, `reject_reason`, `created_at`, `updated_at`, `dri_status`, `manager_status`（取代原本單一欄位 `review_status`）, `dri_submitted_at`, `manager_reviewed_at`, `job_code`（見下方「人天／成本資料來源」）, `industry`（直接欄位，見下方說明）, `contact_id`, `review_token`（審核連結用，見下方「審核 API」） |
| `sow_structured_content` | AI 萃取出的結構化內容，`sow_id` 外鍵指向 `sow_document.id`。`version=1` 是 AI 原始萃取、不可變；主管核准審核後才會新增 `version=2`（用 `MAX(version)+1`），案例展示一律讀最新版本 | `sow_id`, `version`, `customer_context`(JSONB), `project_planning`(JSONB), `technical_design`(JSONB), `created_at` |
| `sow_review_draft` | DRI 審核中的暫存內容，有版本歷史：`(sow_id, version)` 複合唯一，一個案例可以有多筆（多輪審核）。DRI 存檔都是 in-place 更新目前最新版本；送出審查不新增版本（`dri_status`/`manager_status` 狀態機自然凍結）；**主管退回時才新增下一版**（複製剛審過的內容）給 DRI 繼續編輯。主管畫面比對的是「`sow_structured_content version=1`（original）vs 這張表最新版本（current）」；核准時讀最新版本升版成 `sow_structured_content` 新版本 | `sow_id`(FK), `version`, `customer_context`(JSONB), `project_planning`(JSONB), `technical_design`(JSONB), `updated_at`, `updated_by` |
| `sow_review_comment` | 審核留言記錄，**每個角色（DRI/MANAGER）對同一個 `section_key` 最多一筆留言**（可編輯、可刪除，不再是無限留言串）；DRI 在審核頁輸入的留言跟主管退回時的理由都存這裡 | `id`, `sow_id`(FK), `author_role`（`DRI`/`MANAGER`）, `author_name`（現在是 email，見「審核 API」）, `body`, `section_key`, `created_at`, `updated_at` |
| `skill_list` | 技能字典（分類＋技能兩層），取代原本四種 `tag_category` 的扁平標籤模型 | `id`, `category`, `skill` |
| `sow_skill_relation` | `sow_document` × `skill_list` 多對多關聯，**取代了舊的 `sow_tag_relation`**（表的 `id` 序列仍叫 `sow_tag_relation_id_seq`，是直接改名/改欄位而來，不是新建的表） | `sow_id`(FK), `skill_id`(FK → `skill_list.id`), `tag_source`（預設 `AUTO_LLM`）, `reviewed_by` |
| `tag_definition` | ⚠️ 還存在（82 筆）但**跟案例實際標籤分配已經脫鉤**：欄位不再是文件曾經描述的 `tag_category`/`tag_name`，現在只被 `GET /api/skill-taxonomy` 拿來產生「技能分類」參考字典，跟 `sow_skill_relation`/`skill_list` 是兩套不同步的資料 | `tag_id`, `is_active`, `domain`, `category`, `skill_name` |
| `contact` | 負責人聯絡資訊，`nda_work_station_apply.contact_id` 外鍵指向這裡，供「客戶表達興趣」通知信用 | `id`, `email`, `name` |
| `customer` | 客戶表達興趣時登記的聯絡方式 | `id`, `email`, `comment` |
| `sow_customer_interest` | `customer` × `sow_document` 多對多關聯，對應 `POST /api/cases/{id}/interest`（案例頁「我有興趣」按鈕） | `customer_id`(FK), `sow_id`(FK), `created_at` |

`sow_document.dri_status`／`manager_status` 是審核狀態機（原本是單一欄位 `review_status`，後來拆成兩欄，見下方的遷移腳本說明），跟原本就有、目前沒被用到的 `processing_status` 是兩個不相干的欄位，不要混用：

| `dri_status` | `manager_status` | 對應舊的 `review_status` | 意義 |
|---|---|---|---|
| `waiting` | `waiting` | `DRI_REVIEW` | 新文件的預設起點，等 DRI 編輯送審（既有 4 筆資料已在 migration 時回填成 `approve`/`approve`） |
| `approve` | `waiting` | `MANAGER_REVIEW` | DRI 已送出，等主管審核 |
| `waiting` | `reject` | `RETURNED_TO_DRI` | 主管退回，DRI 可繼續編輯（`sow_review_draft` 新一版） |
| `approve` | `approve` | `PUBLISHED` | 主管已核准發布，`GET /api/cases`／`GET /api/cases/{id}` 只回傳這個組合的案例 |

DRI 重新送出（`POST /submit`）時會把 `manager_status` 重置回 `waiting`，避免上一輪的 `reject` 殘留誤導。`backend/review.py` 的 `_derive_status()` 會把這兩欄組合推回上表第 3 欄那 4 種字串，放進 `/api/review/cases/{token}` 回應的 `status` 欄位，`review-frontend` 完全不用感知這個拆分。

⚠️ 對應的兩個遷移腳本——把 `review_status` 拆成 `dri_status`/`manager_status`，以及給 `sow_review_draft` 加 `version`——**從未 commit 進 git**（`git log --all` 查無 `migrate_dri_manager_status.py`/`migrate_review_draft_versioning.py` 任何記錄）。這兩項變更是直接查 RDS 現況反推已經執行過，不是從版控歷史確認的，之後如果要重建環境，這兩個腳本要重寫。

`sow_structured_content` 的三個 JSONB 欄位形狀（已對照 `backend/review.py` 的 Pydantic model 跟 `backend/app.py::build_case()` 的實際讀取方式校正，跟 `json.txt` 最初定義的 schema 不完全一樣）：

```
customer_context:  { industry_background, challenge, solution, kpis: [{value, label}] }
project_planning:  { owner, team_size, period, man_days, total_cost, deliverables: [string] }
technical_design:  { core_functions: [string], system_modules: [{module_name, responsibility}], underlying_architecture: { summary, data_flow, deployment_environment } }
```

`industry` 現在是 `sow_document` 的直接欄位（字串），不再正規化存在 tag 表裡。`service_domain`/`use_case`/`technology_platform` 這種「四分類標籤」模型已經不存在，技能改用上面的 `skill_list` + `sow_skill_relation`（分類＋技能兩層）。

## 人天／成本資料來源（`nda_work_station_apply` 對照）

`project_planning.man_days`/`total_cost` 是 AI 從 SOW 文件萃取的值，不一定準確。專案另外有一張跟上面這些案例知識庫資料表無關、給「NDA 工作站申請」流程用的表 `nda_work_station_apply`（`job_code`, `nda_check`, `dri_mail`, `dri_name`, `dri_fullname`, `dri_deptno`, `dri_deptname`, `manager_mail`, `manager_name`, `manager_fullname`, `manager_deptno`, `manager_deptname`, `estimated_mandays`, `total_cost`, `industry` 等），其中 `estimated_mandays`/`total_cost` 是用 `backend/enrich_jobcode_dri.py` 呼叫 Nebula API（`NEBULA_API_BASE`/`NEBULA_CLIENT_ID`/`NEBULA_CLIENT_SECRET`）回填的權威資料，`job_code` 對應的是 SOW 檔名裡的 JobCode。

`sow_document.job_code`（原本由 `backend/migrate_add_job_code.py` 新增，該腳本現在已不在 repo 裡，見下方開發指令章節）是兩邊的對照鍵。`app.py` 的 `build_case()`／`common.fetch_nda_cost()` 邏輯：

- 若 `sow_document.job_code` 有值，且 `nda_work_station_apply` 對得到該 `job_code`、且 `estimated_mandays`/`total_cost` 不是 `NULL` → 案例的「專案規劃與交付」人天／成本改用這個值（`common.format_number()` 格式化成千分位字串，**不含貨幣符號**，因為 `nda_work_station_apply` 沒存幣別）。
- 否則（`job_code` 是 `NULL`、或 `nda_work_station_apply` 查無此 `job_code`、或該筆 `estimated_mandays`/`total_cost` 還是 `NULL`）→ fallback 回 `sow_structured_content.project_planning.man_days`/`total_cost`（AI 萃取值，可能帶幣別字串如 `"NT$ 1,920,000"`）。
- **目前既有的 `sow_document` 都還沒有 `job_code`**（除了手動填過的 `id=1`），要靠人工比對 `nda_work_station_apply.job_code`（對照 SOW 檔名）手動填入才會生效，這個 repo 目前沒有自動比對邏輯。**這欄現在不只影響人天/成本，還是審核連結能不能打開的必要條件（見下方審核 API 說明）。**

`backend/common.py::ensure_nda_enriched()` 不是只有一次性腳本會回填：**每次打開審核頁（`GET /api/review/cases/{token}`）都會檢查** `nda_work_station_apply` 這列是否還缺 DRI/主管/人天/成本欄位，缺的話當場呼叫 Nebula API 回填（Nebula 打不通或認證沒設都只記 log、不拋例外，照樣 fallback 回 AI 萃取值）。另外 `nda_work_station_apply.dri_deptname` 現在也是 `owner`／前端 `driDepartment` 欄位的固定來源（優先於 AI 萃取值），供案例庫 PM/SA 角色的部門篩選使用。

## 審核 API（`backend/review.py`，prefix `/api/review`）

⚠️ 路由的路徑參數已經從 `job_code` 改成不透光的 **`token`**：`sow_document.review_token` 存著 `HMAC-SHA256(REVIEW_LINK_SECRET, job_code)`（`backend/common.py::compute_review_token()`），`_resolve_sow_id()` 改成 `SELECT id FROM sow_document WHERE review_token = :token AND is_latest = true` 解析出內部 `sow_id`，查不到就回 404。**連結格式也從 `?jobcode=` 改成 `?token=`**（`review-frontend/js/app.js` 讀的是 `URLSearchParams(...).get('token')`），URL 上不再直接暴露 `job_code`。`sow_document`/`sow_structured_content`/`sow_review_draft`/`sow_review_comment` 之間的關聯依然全部用內部 `sow_id`。

同時，**`reviewerName` 手動輸入姓名的設計已經整個移除**，`review-frontend` 不再有姓名輸入框。送審人/核准人改由後端 `_resolve_reviewer_email()` 依 `sow_document.job_code → nda_work_station_apply.dri_mail`/`manager_mail` 自動解析 email，寫進 `author_name`/`edited_by`/`approved_by`。

| 路由 | 用途 |
|---|---|
| `GET /cases/{token}` | 回傳審核頁要的完整案例（不過濾 `dri_status`/`manager_status`，審核中的案例也要能打開）。第一次呼叫時若還沒有暫存，會自動從 `sow_structured_content version=1` 建一份，並呼叫 `ensure_nda_enriched()` 即時回填人天/成本/部門。每個可編輯欄位回傳 `{original, current, savedAt}` |
| `PUT /cases/{token}/draft` | DRI 儲存。body 帶 `customerContext`/`projectPlanning`/`technicalDesign`（camelCase，對齊 `review-frontend` 的 `FIELD_DEFS`，不再需要 `reviewerName`）。`dri_status` 需為 `waiting`，否則 409 |
| `POST /cases/{token}/submit` | DRI 送出審查，`dri_status → approve`、`manager_status → waiting`（重置），寫入 `edited_by`/`dri_submitted_at` |
| `POST /cases/{token}/comments` | 新增一筆留言，body 帶 `authorRole`/`body`/`sectionKey`（可選）。**同一角色對同一個 `sectionKey` 只能留一筆**，重複會回 409（請改走下面的編輯端點） |
| `PUT /cases/{token}/comments/{comment_id}` | 編輯自己（`authorRole` 要吻合）留的那筆留言 |
| `DELETE /cases/{token}/comments/{comment_id}` | 刪除自己（`authorRole` 要吻合）留的那筆留言 |
| `POST /cases/{token}/return` | 主管退回，`dri_status → waiting`、`manager_status → reject`，可選填 `comment` 一併存成留言，並幫 `sow_review_draft` 新增下一版 |
| `POST /cases/{token}/approve` | 主管核准發布：把暫存最新版本升版成 `sow_structured_content` 新版本、`manager_status → approve` |

欄位命名對照（JSONB snake_case ⇄ `review-frontend` FIELD_DEFS）：`industry_background`→`industryBackground`、`team_size`→`teamSize`、`man_days`→`manDays`、`total_cost`→`totalCost`、`core_functions`→`coreFunctions`、`system_modules`→`systemModules`（元素 `module_name`→`moduleName`）、`underlying_architecture`→`underlyingArchitecture`（`data_flow`→`dataFlow`、`deployment_environment`→`deploymentEnvironment`）。

## 前端 ⇄ 資料庫欄位對應

| 前端欄位 | 來源 | 備註 |
|---|---|---|
| `id` | `sow_document.id` | |
| `title` | ⚠️ 無對應欄位，由 `file_name` 去掉副檔名/底線衍生 | 非精確標題 |
| `description` | ⚠️ 無對應欄位，由 `customer_context.challenge` 前 60 字截斷衍生 | |
| `icon` | ⚠️ 無對應欄位，後端依 `industry` 字串做靜態對照（見 `app.py` 的 `INDUSTRY_ICON`） | |
| `date` | `sow_document.created_at` | |
| `creator` | `sow_document.edited_by`（無則 `approved_by`，都無則 `—`） | |
| `industry` | `sow_document.industry` 直接欄位 | ⚠️ 已不是透過 tag 查表取得 |
| `serviceCategory` | ⚠️ 無對應欄位，`build_case()` 固定回傳 `[]` | 死欄位：原本的 `tag_category='SERVICE_DOMAIN'` 模型已不存在，`frontend/js/app.js` 篩選也已不用這個鍵 |
| `useCase` | ⚠️ 無對應欄位，`build_case()` 固定回傳 `[]` | 死欄位，理由同上（原 `USE_CASE`） |
| `skills` | `sow_skill_relation` JOIN `skill_list`，取 `skill` 欄位陣列 | 取代原本 `tag_category='TECH_PLATFORM'` 的模型 |
| `techCategory` | 同上，取不重複的 `skill_list.category` 陣列 | 前端篩選鍵 `category` 用這個 |
| `skillsByCategory` | 同上，依 `category` 分組的 `{category: [skill, ...]}` | |
| `driDepartment` | `nda_work_station_apply.dri_deptname`（依 `job_code` 對照） | 前端篩選鍵 `driDepartment`，PM/SA 角色可見 |
| `contactItemName` | ⚠️ 無對應欄位，由 `file_name` 去掉前 12 碼 job code 前綴後衍生 | 「我有興趣」彈窗顯示用 |
| `detail.A.*` | `customer_context.*`，字串包成 `{zh, en}`（見下方注意事項） | |
| `detail.B.owner/period/teamSize/cost/deliverables` | `project_planning.*`（`owner`/`cost` 可能被 `nda_work_station_apply` 覆蓋，見上方「人天／成本資料來源」） | 沒有 `team`/`wbs` 明細，前端已 guard |
| `detail.C.coreFunctions/modules/underlyingArchitecture` | `technical_design.core_functions`/`system_modules`/`underlying_architecture` | ⚠️ 欄位名稱跟最初 `json.txt` 定義的 `architecture_nodes`/`tech_stack` 不同，已依 `app.py::build_case()` 實際讀法校正 |

## 已知落差 / 注意事項（給未來維護者）

1. **`title`/`description`/`icon` 不是真實欄位**，是後端用其他欄位衍生出來的替代值（見 `backend/app.py` 的 `derive_title()`、`derive_description()`、`INDUSTRY_ICON`）。如果之後要精確，需要在 `sow_structured_content` 或新表補上真正的標題欄位。
2. **沒有團隊角色明細（team）與 WBS 時程資料**。`project_planning` 只有 `team_size`（總人數）。`frontend/js/app.js` 的 `sectionsTabB()` 已加 guard：`b.team`/`b.wbs` 沒資料時就不渲染對應區塊 —— **不要為了「補滿畫面」重新塞假的 team/wbs 資料進去**，那會誤導使用者。
3. ⚠️ **`serviceCategory`/`useCase` 現在是死欄位**：`build_case()` 固定回傳 `[]`，`frontend/js/app.js` 的篩選鍵也已經改成 `industry`/`driDepartment`/`category`/`skill`，不再用 `serviceCategory`/`useCase`。原本這條注意事項講的「是陣列、篩選用 `some()`+`includes()`」邏輯仍然適用於現在的 `skills`/`techCategory`（取代舊的 `TECH_PLATFORM` 標籤），但 `serviceCategory`/`useCase` 本身已經名存實亡——如果之後要恢復這兩個維度，資料來源要重新設計（原本依賴的 `tag_definition` 四分類模型已經不在了）。
4. **真實 tag_name / kpis.label / deliverables 都是「人類可讀原文」**（例如 `"AI / GenAI"`、`"n8n workflow 樣板"`），不是 mock 資料的 code（例如 `'ai_genai'`）。`app.js` 的 `L(dict, code, lang)` 函式查不到 code 時會 fallback 直接回傳原字串，`tagColorFor(dict, code, fallback)` 查不到顏色時會用固定的 fallback 色——**這是刻意設計來相容真實資料，不是 bug**，不要「修好」讓它強制走 code 查表。
5. **AI 產出內容目前只有中文**。後端 `bi()`（`backend/app.py`）把單語字串包成 `{zh: text, en: text}`（兩邊值相同）以相容前端既有的雙語 render 邏輯。切換到英文介面時，案例內容本身仍會顯示中文，這是預期行為，不是翻譯漏了。
6. **`backend/requirements.txt` 一度是 UTF-16 編碼**（Windows 記事本另存造成），已改回 UTF-8。之後編輯這個檔案務必確認編碼，不要用會存成 UTF-16 的工具，否則 pip 會解析出亂碼套件名。
7. **`sow_structured_content` 最初的測試資料是用 `backend/seed_structured_content.py` 手動灌的**（該腳本現在已不在 repo 裡），內容依照真實 SOW markdown 內容改寫（不是憑空捏造，但也不是正式 Bedrock 呼叫產出）。之後如果做出真正的 `bedrock_service.py`（呼叫 Bedrock + `SOW_ANALYSIS_TOOL`），要整批換掉這份 seed 資料，而不是疊加。
8. **`app.py` 裡 `app.mount("/", StaticFiles(...))` 必須放在所有 `/api/*` route 定義之後**，否則靜態檔案的萬用 mount 會蓋掉 API 路由，導致 `/api/cases` 404。
9. 資料量現況（直接查 RDS，之後文件量變大要留意 `GET /api/cases` 沒有分頁的效能問題）：`sow_document` 6 筆、`sow_structured_content` 20 筆（含審核歷史版本）、`sow_review_draft` 8 筆、`sow_review_comment` 2 筆、`tag_definition` 82 筆（跟案例標籤脫鉤，見下方 #12）、`skill_list` 414 筆、`sow_skill_relation` 47 筆、`customer` 41 筆、`contact` 6 筆、`nda_work_station_apply` 10 筆。
10. **`review-frontend` 仍然沒有登入驗證**，但風險比最初設計時低一些：連結已經改成不透光的 `?token=`（`HMAC-SHA256(REVIEW_LINK_SECRET, job_code)`）而不是直接暴露 `?jobcode=`，而且手動輸入姓名的欄位已經整個移除——送審人/核准人改由後端自動查 `nda_work_station_apply.dri_mail`/`manager_mail` 解析，不能再隨便填假名字。但只要拿到連結本身，還是任何人都能操作（沒有帳號登入），串接 Power Automate 時這個連結會被貼進 Teams 卡片，等於半公開；上線前仍要評估風險。
11. **`sow_review_draft` 已支援審核輪次的版本歷史**：`(sow_id, version)` 複合唯一（已在 RDS 確認存在），DRI 存檔是 in-place 更新最新版本；送出審查不新增版本（靠 `dri_status`/`manager_status` 狀態機擋掉後續編輯，天然凍結）；**只有主管退回才會新增下一版**（複製剛審過的內容），如此每一輪的內容都會被保留下來。⚠️ 這個改動（連同 `review_status` 拆成 `dri_status`/`manager_status`）對應的遷移腳本 `migrate_review_draft_versioning.py`/`migrate_dri_manager_status.py` **從未 commit 進 git**（`git log --all` 查無），只能從 RDS 現況反推已經執行過，不要假設 repo 裡找得到。目前這個版本歷史只在資料庫層存在，**沒有在任何 API 回應或前端畫面暴露版本號**，DRI／主管畫面看不到「第幾輪」；主管畫面的 diff 比對基準也還是固定比 `sow_structured_content version=1`（最初的 AI 萃取），不是比上一輪版本。
12. **`tag_definition` 跟實際案例標籤已經脫鉤**：案例的 `skills`/`techCategory` 現在全部來自 `sow_skill_relation` JOIN `skill_list`，`tag_definition` 只剩 `GET /api/skill-taxonomy` 一個用途（提供技能分類下拉選單參考），兩邊資料互不同步。如果之後要讓「可選的技能清單」跟「案例實際掛的技能」對齊，要嘛把 `/api/skill-taxonomy` 也改查 `skill_list`，要嘛明確決定 `tag_definition` 要退場。
13. **`app.py` 裡 `handler = Mangum(app)`**（`from mangum import Mangum`）：這個 FastAPI app 同時可以用 AWS Lambda 部署（`backend/package/lambda_layer/` 有對應的打包依賴），不是只有 `infra/` 描述的 EC2 + uvicorn 這一條路徑。`infra/README.md`/`infra/terraform` 目前只涵蓋 EC2 部署，Lambda 那條部署路徑的設定（API Gateway、Lambda 本身）不在這個 repo 的 `infra/` 裡，之後如果要釐清實際線上用的是哪一種部署，要另外確認。

## 開發 / 驗證指令

```powershell
# 安裝套件（在專案根目錄的 myenv 虛擬環境）
myenv\Scripts\python.exe -m pip install -r backend\requirements.txt

# ⚠️ seed_structured_content.py / migrate_review_workflow.py / migrate_add_job_code.py /
# migrate_dri_manager_status.py / migrate_review_draft_versioning.py 這幾支一次性腳本
# 目前都不在 repo 裡（git log 查無，應該是本機跑過一次就刪了，沒 commit）。
# RDS 現況已經反映這些腳本跑過的結果，不需要也無法重跑；之後若要重建環境，這些腳本要重寫。

cd backend

# 啟動服務（前端 + 審核頁 + API 同一個 server）
uvicorn app:app --reload
# 案例庫（對外）：http://127.0.0.1:8000/
# DRI 審核頁：http://127.0.0.1:8000/review/dri.html?token={review_token}
# 主管審核頁：http://127.0.0.1:8000/review/manager.html?token={review_token}
# review_token 要從 sow_document 表查（SELECT review_token FROM sow_document WHERE job_code = '...'），
# 連結已經不再用 ?jobcode= 格式，網址上也看不到 job_code 本身

# 手動檢查 API（PowerShell 請用 curl.exe，不要用內建 alias；<TOKEN> 換成實際 review_token）
curl.exe http://127.0.0.1:8000/api/cases
curl.exe http://127.0.0.1:8000/api/cases/1
curl.exe http://127.0.0.1:8000/api/review/cases/<TOKEN>
curl.exe -X PUT http://127.0.0.1:8000/api/review/cases/<TOKEN>/draft -H "Content-Type: application/json" -d '{"customerContext":{...},"projectPlanning":{...},"technicalDesign":{...}}'
curl.exe -X POST http://127.0.0.1:8000/api/review/cases/<TOKEN>/submit
curl.exe -X POST http://127.0.0.1:8000/api/review/cases/<TOKEN>/approve
```
