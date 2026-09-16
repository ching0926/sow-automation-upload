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
  - `js/app.js`：狀態管理、渲染、事件處理；案例 `job_code` 從網址 `?jobcode=` 讀取，資料一律來自 API（無 mock、無 localStorage 案例資料）
  - 連結格式：`/review/dri.html?jobcode={job_code}`、`/review/manager.html?jobcode={job_code}`（Power Automate 在 Teams 卡片放的連結）。**`sow_document.job_code` 沒填就無法打開審核頁（API 404）**，`job_code` 已從「加分欄位」變成審核流程的必要前置條件
  - **目前完全沒有身分驗證**——任何拿到連結的人都能以任意姓名操作，姓名輸入框只是 UX 用（見「已知落差」）
- **後端**：`backend/app.py`（FastAPI），共用邏輯拆在 `backend/common.py`，審核相關路由拆在 `backend/review.py`
  - `GET /api/cases`：回傳所有 `dri_status='approve'` 且 `manager_status='approve'` 的案例（含 detail），供卡片列表 + 篩選使用
  - `GET /api/cases/{sow_id}`：回傳單一已發布案例
  - `/api/review/*`：DRI / 主管審核流程用的路由，見下方「審核流程」章節
  - 用 `StaticFiles` 把 `review-frontend/` 掛載在 `/review`、`frontend/` 掛載在 `/`，同一個 server 同時服務頁面與 API（不用處理 CORS）；**掛載順序固定是 `include_router(review_router)` → `/review` mount → `/` mount**，`/` 是萬用 catch-all 必須放最後
  - 沿用 `backend/db.py` 既有的 `get_db()` / `SessionLocal`（SQLAlchemy）
- **資料庫**：AWS RDS PostgreSQL，DB 名稱 `SDXINTERN`。連線資訊在根目錄 `.env`（`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`）。**`.env` 含真實密碼，絕不能提交進版控、絕不能貼到聊天或文件裡。**
- **AI 產出格式**：`backend/json.txt` 定義的 `SOW_ANALYSIS_TOOL`（Bedrock tool-use 的 `input_schema`），描述 AI 應該產出的結構。裡面提到的 `bedrock_service.py` 目前還不存在，是規劃中、尚未實作的呼叫邏輯。
- **審核流程（Power Automate + Teams，外部串接）**：AWS 處理完成 → Power Automate 收到通知 → 發 Teams 卡片給 DRI（帶 `/review/dri.html?jobcode=` 連結）→ DRI 編輯送出 → 回 Teams 卡片留言 → Power Automate 呼叫 `POST /api/review/cases/{job_code}/comments` 寫入留言、通知主管（帶 `/review/manager.html?jobcode=` 連結）→ 主管核准或退回。**Power Automate 流程本身（觸發條件、Adaptive Card、Teams connector）不在這個 repo 裡，是在 Power Automate 網站另外設定**；這個 repo 只負責提供 `/api/review/*` 這組 API 與兩個審核頁面。

## 六張資料表

| 表 | 用途 | 關鍵欄位 |
|---|---|---|
| `sow_document` | 一份 SOW 文件 = 一筆 | `id`, `file_name`, `s3_key`, `processing_status`, `is_latest`, `version`, `edited_by`, `approved_by`, `created_at`, `updated_at`, `dri_status`, `manager_status`（取代原本單一欄位 `review_status`）, `dri_submitted_at`, `manager_reviewed_at`, `job_code`（見下方「人天／成本資料來源」） |
| `sow_structured_content` | AI 萃取出的結構化內容，`sow_id` 外鍵指向 `sow_document.id`。`version=1` 是 AI 原始萃取、不可變；主管核准審核後才會新增 `version=2`（用 `MAX(version)+1`），案例展示一律讀最新版本 | `sow_id`, `version`, `customer_context`(JSONB), `project_planning`(JSONB), `technical_design`(JSONB) |
| `sow_review_draft` | DRI 審核中的暫存內容，有版本歷史：`(sow_id, version)` 複合唯一，一個案例可以有多筆（多輪審核）。DRI 存檔都是 in-place 更新目前最新版本；送出審查不新增版本（`dri_status`/`manager_status` 狀態機自然凍結）；**主管退回時才新增下一版**（複製剛審過的內容）給 DRI 繼續編輯。主管畫面比對的是「`sow_structured_content version=1`（original）vs 這張表最新版本（current）」；核准時讀最新版本升版成 `sow_structured_content` 新版本 | `sow_id`(FK), `version`, `customer_context`(JSONB), `project_planning`(JSONB), `technical_design`(JSONB), `updated_at`, `updated_by` |
| `sow_review_comment` | 審核留言記錄（append-only），DRI 在 Teams 卡片輸入的留言（由 Power Automate 呼叫 API 寫入）跟主管退回時的理由都存這裡 | `id`, `sow_id`(FK), `author_role`（`DRI`/`MANAGER`）, `author_name`, `body`, `created_at` |
| `sow_tag_relation` | `sow_document` × `tag_definition` 多對多關聯 | `sow_id`(FK), `tag_id`(FK), `tag_source`（目前都是 `AUTO_LLM`） |
| `tag_definition` | 標籤字典 | `tag_id`（原 `id`）, `tag_category`（原 `category`；`INDUSTRY`/`SERVICE_DOMAIN`/`USE_CASE`/`TECH_PLATFORM`）, `tag_name`, `is_active`, `domain`/`category`/`skill_name`（新增，對應 `industry_category_skills.md` 技能分類表，目前未使用、值為空） |

`sow_document.dri_status`／`manager_status` 是審核狀態機（原本是單一欄位 `review_status`，`backend/migrate_dri_manager_status.py` 拆成兩欄），跟原本就有、目前沒被用到的 `processing_status` 是兩個不相干的欄位，不要混用：

| `dri_status` | `manager_status` | 對應舊的 `review_status` | 意義 |
|---|---|---|---|
| `waiting` | `waiting` | `DRI_REVIEW` | 新文件的預設起點，等 DRI 編輯送審（既有 4 筆資料已在 migration 時回填成 `approve`/`approve`） |
| `approve` | `waiting` | `MANAGER_REVIEW` | DRI 已送出，等主管審核 |
| `waiting` | `reject` | `RETURNED_TO_DRI` | 主管退回，DRI 可繼續編輯（`sow_review_draft` 新一版） |
| `approve` | `approve` | `PUBLISHED` | 主管已核准發布，`GET /api/cases`／`GET /api/cases/{id}` 只回傳這個組合的案例 |

DRI 重新送出（`POST /submit`）時會把 `manager_status` 重置回 `waiting`，避免上一輪的 `reject` 殘留誤導。`backend/review.py` 的 `_derive_status()` 會把這兩欄組合推回上表第 3 欄那 4 種字串，放進 `/api/review/cases/{job_code}` 回應的 `status` 欄位，`review-frontend` 完全不用感知這個拆分。

`sow_structured_content` 的三個 JSONB 欄位形狀對應 `json.txt` schema：

```
customer_context:  { industry_background, challenge, solution, kpis: [{icon, value, label}] }
project_planning:  { owner, team_size, period, man_days, total_cost, deliverables: [string] }
technical_design:  { core_functions: [string], architecture_nodes: [string], tech_stack: [string] }
```

`metadata`（industry / service_domain / use_case / technology_platform）**不放在 JSONB 裡**，而是正規化存在 `tag_definition` + `sow_tag_relation`。

## 人天／成本資料來源（`nda_work_station_apply` 對照）

`project_planning.man_days`/`total_cost` 是 AI 從 SOW 文件萃取的值，不一定準確。專案另外有一張跟案例知識庫六張表無關、給「NDA 工作站申請」流程用的表 `nda_work_station_apply`（`job_code`, `nda_check`, `dri_mail`, `dri_name`, `dri_fullname`, `dri_deptno`, `dri_deptname`, `manager_mail`, `manager_name`, `manager_fullname`, `manager_deptno`, `manager_deptname`, `estimated_mandays`, `total_cost`, `industry` 等），其中 `estimated_mandays`/`total_cost` 是用 `backend/enrich_jobcode_dri.py` 呼叫 Nebula API（`NEBULA_API_BASE`/`NEBULA_CLIENT_ID`/`NEBULA_CLIENT_SECRET`）回填的權威資料，`job_code` 對應的是 SOW 檔名裡的 JobCode。

`sow_document.job_code`（`backend/migrate_add_job_code.py` 新增的欄位）是兩邊的對照鍵。`app.py` 的 `build_case()`／`common.fetch_nda_cost()` 邏輯：

- 若 `sow_document.job_code` 有值，且 `nda_work_station_apply` 對得到該 `job_code`、且 `estimated_mandays`/`total_cost` 不是 `NULL` → 案例的「專案規劃與交付」人天／成本改用這個值（`common.format_number()` 格式化成千分位字串，**不含貨幣符號**，因為 `nda_work_station_apply` 沒存幣別）。
- 否則（`job_code` 是 `NULL`、或 `nda_work_station_apply` 查無此 `job_code`、或該筆 `estimated_mandays`/`total_cost` 還是 `NULL`）→ fallback 回 `sow_structured_content.project_planning.man_days`/`total_cost`（AI 萃取值，可能帶幣別字串如 `"NT$ 1,920,000"`）。
- **目前既有的 `sow_document` 都還沒有 `job_code`**（除了手動填過的 `id=1`），要靠人工比對 `nda_work_station_apply.job_code`（對照 SOW 檔名）手動填入才會生效，這個 repo 目前沒有自動比對邏輯。**這欄現在不只影響人天/成本，還是審核連結能不能打開的必要條件（見下方審核 API 說明）。**

## 審核 API（`backend/review.py`，prefix `/api/review`）

所有路由的路徑參數都是 `job_code`（不是 `sow_document.id`）。每個路由一進來會先用 `_resolve_sow_id()` 以 `SELECT id FROM sow_document WHERE job_code = :job_code AND is_latest = true` 解析出內部 `sow_id`，查不到就回 404；`sow_document`/`sow_structured_content`/`sow_review_draft`/`sow_review_comment` 之間的關聯依然全部用 `sow_id`，只有「URL 上帶的 key」換成 `job_code`。

| 路由 | 用途 |
|---|---|
| `GET /cases/{job_code}` | 回傳審核頁要的完整案例（不過濾 `dri_status`/`manager_status`，審核中的案例也要能打開）。第一次呼叫時若還沒有暫存，會自動從 `sow_structured_content version=1` 建一份。每個可編輯欄位回傳 `{original, current, savedAt}` |
| `PUT /cases/{job_code}/draft` | DRI 儲存。body 帶 `reviewerName` + `customerContext`/`projectPlanning`/`technicalDesign`（camelCase，對齊 `review-frontend` 的 `FIELD_DEFS`）。`dri_status` 需為 `waiting`，否則 409 |
| `POST /cases/{job_code}/submit` | DRI 送出審查，`dri_status → approve`、`manager_status → waiting`（重置），寫入 `edited_by`/`dri_submitted_at` |
| `POST /cases/{job_code}/comments` | 新增一筆留言（不檢查狀態）。Power Automate 在 Teams 卡片收到 DRI 留言後會呼叫這個端點 |
| `POST /cases/{job_code}/return` | 主管退回，`dri_status → waiting`、`manager_status → reject`，可選填 `comment` 一併存成留言，並幫 `sow_review_draft` 新增下一版 |
| `POST /cases/{job_code}/approve` | 主管核准發布：把暫存最新版本升版成 `sow_structured_content` 新版本、`manager_status → approve` |

欄位命名對照（JSONB snake_case ⇄ `review-frontend` FIELD_DEFS）：`industry_background`→`industryBackground`、`team_size`→`teamSize`、`man_days`→`manDays`、`total_cost`→`totalCost`、`core_functions`→`coreFunctions`、`architecture_nodes`→`architecture`（⚠️少了 `_nodes`）、`tech_stack`→`techStack`。

## 前端 ⇄ 資料庫欄位對應

| 前端欄位 | 來源 | 備註 |
|---|---|---|
| `id` | `sow_document.id` | |
| `title` | ⚠️ 無對應欄位，由 `file_name` 去掉副檔名/底線衍生 | 非精確標題 |
| `description` | ⚠️ 無對應欄位，由 `customer_context.challenge` 前 60 字截斷衍生 | |
| `icon` | ⚠️ 無對應欄位，後端依 `industry` 字串做靜態對照（見 `app.py` 的 `INDUSTRY_ICON`） | |
| `date` | `sow_document.created_at` | |
| `creator` | `sow_document.edited_by`（無則 `approved_by`，都無則 `—`） | |
| `industry` | `tag_definition` where `tag_category='INDUSTRY'`，取第一筆 | 目前每份文件恰好 1 筆 |
| `serviceCategory` | `category='SERVICE_DOMAIN'` 的 tag_name **陣列** | 一份文件可能有多個 |
| `useCase` | `category='USE_CASE'` 的 tag_name **陣列** | 同上 |
| `skills` | `category='TECH_PLATFORM'` 的 tag_name 陣列 | |
| `detail.A.*` | `customer_context.*`，字串包成 `{zh, en}`（見下方注意事項） | |
| `detail.B.owner/period/teamSize/cost/deliverables` | `project_planning.*` | 沒有 `team`/`wbs` 明細，前端已 guard |
| `detail.C.coreFunctions/architecture/techStack` | `technical_design.core_functions/architecture_nodes/tech_stack` | 純字串陣列，非 mock 的 code |

## 已知落差 / 注意事項（給未來維護者）

1. **`title`/`description`/`icon` 不是真實欄位**，是後端用其他欄位衍生出來的替代值（見 `backend/app.py` 的 `derive_title()`、`derive_description()`、`INDUSTRY_ICON`）。如果之後要精確，需要在 `sow_structured_content` 或新表補上真正的標題欄位。
2. **沒有團隊角色明細（team）與 WBS 時程資料**。`project_planning` 只有 `team_size`（總人數）。`frontend/js/app.js` 的 `sectionsTabB()` 已加 guard：`b.team`/`b.wbs` 沒資料時就不渲染對應區塊 —— **不要為了「補滿畫面」重新塞假的 team/wbs 資料進去**，那會誤導使用者。
3. **`serviceCategory`/`useCase` 是陣列**，不是最初 mock 資料的單一 code 值。篩選邏輯（`matchesFilters()`）用 `some()` + `includes()` 判斷；`getFilterOptions()` 用 `flatMap()` 取不重複選項。如果之後改動篩選邏輯，記得維持陣列語意。
4. **真實 tag_name / kpis.label / deliverables 都是「人類可讀原文」**（例如 `"AI / GenAI"`、`"n8n workflow 樣板"`），不是 mock 資料的 code（例如 `'ai_genai'`）。`app.js` 的 `L(dict, code, lang)` 函式查不到 code 時會 fallback 直接回傳原字串，`tagColorFor(dict, code, fallback)` 查不到顏色時會用固定的 fallback 色——**這是刻意設計來相容真實資料，不是 bug**，不要「修好」讓它強制走 code 查表。
5. **AI 產出內容目前只有中文**。後端 `bi()`（`backend/app.py`）把單語字串包成 `{zh: text, en: text}`（兩邊值相同）以相容前端既有的雙語 render 邏輯。切換到英文介面時，案例內容本身仍會顯示中文，這是預期行為，不是翻譯漏了。
6. **`backend/requirements.txt` 一度是 UTF-16 編碼**（Windows 記事本另存造成），已改回 UTF-8。之後編輯這個檔案務必確認編碼，不要用會存成 UTF-16 的工具，否則 pip 會解析出亂碼套件名。
7. **`sow_structured_content` 目前的 4 筆資料是用 `backend/seed_structured_content.py` 手動灌的**，內容依照真實 SOW markdown 內容改寫（不是憑空捏造，但也不是正式 Bedrock 呼叫產出）。之後如果做出真正的 `bedrock_service.py`（呼叫 Bedrock + `SOW_ANALYSIS_TOOL`），要整批換掉這份 seed 資料，而不是疊加。
8. **`app.py` 裡 `app.mount("/", StaticFiles(...))` 必須放在所有 `/api/*` route 定義之後**，否則靜態檔案的萬用 mount 會蓋掉 API 路由，導致 `/api/cases` 404。
9. **`sow_document`/`sow_structured_content`/`sow_tag_relation`/`tag_definition` 目前只有 4 份文件、66 筆標籤關聯、49 筆標籤字典**，資料量很小，`GET /api/cases` 直接回傳全部（含 detail），沒有做分頁，之後文件量變大要留意效能。
10. **`review-frontend` 目前沒有任何身分驗證**（刻意先不做，之後有需要再補 token/登入機制）——`/review/dri.html?jobcode=` 跟 `/review/manager.html?jobcode=` 這兩個連結任何人拿到都能以任意姓名編輯/送審/核准，姓名輸入框只是方便記錄是誰做的（純 UX、寫進 `edited_by`/`approved_by`），不是權限控管。串接 Power Automate 時這個連結會被貼進 Teams 卡片，等於半公開；上線前要評估風險。
11. **`sow_review_draft` 已支援審核輪次的版本歷史**（`backend/migrate_review_draft_versioning.py`）：`(sow_id, version)` 複合唯一，DRI 存檔是 in-place 更新最新版本；送出審查不新增版本（靠 `dri_status`/`manager_status` 狀態機擋掉後續編輯，天然凍結）；**只有主管退回才會新增下一版**（複製剛審過的內容），如此每一輪的內容都會被保留下來。目前這個版本歷史只在資料庫層存在，**沒有在任何 API 回應或前端畫面暴露版本號**，DRI／主管畫面看不到「第幾輪」；主管畫面的 diff 比對基準也還是固定比 `sow_structured_content version=1`（最初的 AI 萃取），不是比上一輪版本。

## 開發 / 驗證指令

```powershell
# 安裝套件（在專案根目錄的 myenv 虛擬環境）
myenv\Scripts\python.exe -m pip install -r backend\requirements.txt

# （重新）灌測試用結構化資料，可重複執行（會先刪除同 sow_id 的舊資料再插入）
cd backend
python seed_structured_content.py

# 建立審核流程需要的欄位/資料表，並把既有文件回填為 PUBLISHED，可重複執行
python migrate_review_workflow.py

# 在 sow_document 新增 job_code 欄位（對照 nda_work_station_apply.job_code 用），可重複執行
python migrate_add_job_code.py

# 啟動服務（前端 + 審核頁 + API 同一個 server）
uvicorn app:app --reload
# 案例庫（對外）：http://127.0.0.1:8000/
# DRI 審核頁：http://127.0.0.1:8000/review/dri.html?jobcode=E1122345678
# 主管審核頁：http://127.0.0.1:8000/review/manager.html?jobcode=E1122345678
# （E1122345678 是目前唯一有填 job_code 的 sow_document，id=1；審核連結現在以 job_code 為 key，沒填 job_code 的文件打不開審核頁）

# 手動檢查 API（PowerShell 請用 curl.exe，不要用內建 alias）
curl.exe http://127.0.0.1:8000/api/cases
curl.exe http://127.0.0.1:8000/api/cases/1
curl.exe http://127.0.0.1:8000/api/review/cases/E1122345678
curl.exe -X PUT http://127.0.0.1:8000/api/review/cases/E1122345678/draft -H "Content-Type: application/json" -d '{"reviewerName":"Chanel","customerContext":{...},"projectPlanning":{...},"technicalDesign":{...}}'
curl.exe -X POST http://127.0.0.1:8000/api/review/cases/E1122345678/submit -H "Content-Type: application/json" -d '{"reviewerName":"Chanel"}'
curl.exe -X POST http://127.0.0.1:8000/api/review/cases/E1122345678/approve -H "Content-Type: application/json" -d '{"reviewerName":"Manager Wang"}'
```
