# SOW 案例知識庫（SOW Solution Knowledge Base）

把過往的 SOW（Statement of Work）文件，透過 AI 萃取成結構化案例資料，並提供內部審核流程與對外案例庫瀏覽。

## 專案簡介

- **案例庫（對外）**：業務／PM／SA 可依角色瀏覽案例，Customer 只看客戶脈絡、PM 多看專案規劃、SA 再多看技術架構（角色累加式揭露）。
- **審核流程（內部）**：SOW PDF 經 AI 萃取後不會直接上架，需經過 DRI 編輯確認、主管核准，才會出現在對外案例庫。
- **通知串接**：AWS 處理完成後透過 Power Automate 發 Teams 卡片通知 DRI／主管，卡片內連結會直接開啟本專案的審核頁面。

## 系統架構

```
SOW PDF ──▶ S3 ──▶ Bedrock（AI 萃取，規劃中）──▶ RDS PostgreSQL（SDXINTERN）
                                                        │
                       ┌────────────────────────────────┼────────────────────────────┐
                       ▼                                ▼                            ▼
              GET /api/cases                  /api/review/*（審核 API）      Power Automate + Teams
              （只回傳已發布案例）                （DRI／主管操作）              （外部串接，不在本repo）
                       │                                │
                       ▼                                ▼
            frontend/（對外案例庫，唯讀）      review-frontend/（DRI／主管審核頁）
```

- **`frontend/`**：對外案例庫，純 Vanilla JS 靜態頁面，無建置工具。`index.html` + `css/style.css` + `js/i18n.js`（中英文字典）+ `js/data.js`（`fetch` 案例資料）+ `js/app.js`（渲染與互動）。
- **`review-frontend/`**：DRI／主管審核頁，同樣是純 Vanilla JS。`dri.html`／`manager.html` 共用同一份 `js/app.js`，靠 `window.REVIEW_MODE` 區分行為；案例 id 從網址 `?id=` 讀取，資料一律來自 `/api/review/*`。
- **`backend/app.py`**（FastAPI）：對外案例庫 API（`GET /api/cases`、`GET /api/cases/{id}`），並用 `StaticFiles` 把 `frontend/` 掛在 `/`、`review-frontend/` 掛在 `/review`。
- **`backend/review.py`**：DRI／主管審核流程 API（`/api/review/*`）。
- **`backend/common.py`**：`app.py` 與 `review.py` 共用的輔助函式（標籤查詢、結構化內容查詢、標題衍生、`fetch_nda_cost()` 查 NDA 人天/成本權威值等）。
- **`backend/db.py`**：SQLAlchemy 連線設定，讀根目錄 `.env`。
- **`backend/migrate_add_job_code.py`**：一次性腳本，幫 `sow_document` 加上 `job_code` 欄位（對照 `nda_work_station_apply.job_code` 用）。
- **`backend/enrich_jobcode_dri.py`**：批次腳本，呼叫 Nebula API 幫 `nda_work_station_apply` 回填 `dri_mail`/`manager_mail`（email）及部門/姓名明細/`estimated_mandays`/`total_cost` 還是 `NULL` 的資料列。
- **資料庫**：AWS RDS PostgreSQL，DB 名稱 `SDXINTERN`。

## 開發環境設定

```powershell
# 安裝套件（專案根目錄的 myenv 虛擬環境）
myenv\Scripts\python.exe -m pip install -r backend\requirements.txt

cd backend

# 第一次建置／或需要重灌測試資料時執行（可重複執行）
python seed_structured_content.py          # 灌 4 筆結構化內容測試資料
python migrate_review_workflow.py          # 建立審核流程欄位/資料表，並把既有文件回填為 PUBLISHED

# 啟動服務（案例庫 + 審核頁 + API 同一個 server，不用處理 CORS）
uvicorn app:app --reload
```

| 頁面 | 網址 |
|---|---|
| 對外案例庫 | `http://127.0.0.1:8000/` |
| DRI 審核頁 | `http://127.0.0.1:8000/review/dri.html?jobcode={job_code}` |
| 主管審核頁 | `http://127.0.0.1:8000/review/manager.html?jobcode={job_code}` |
| API 文件（FastAPI 自動產生） | `http://127.0.0.1:8000/docs` |

⚠️ 審核連結改用 `job_code` 之後，`sow_document.job_code` 變成進入審核流程的**必要欄位**——沒填 `job_code` 的文件，審核連結會直接 404，不會 fallback 回內部 `id`。

`.env` 需放在專案根目錄，定義 `DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`。**`.env` 含真實密碼，不可提交進版控。**

---

## 資料庫 Schema

資料庫為 **PostgreSQL**（AWS RDS，DB 名稱 `SDXINTERN`），共 7 張表（含 `nda_work_station_apply`）。以下欄位、型態、鍵值皆為實際連線資料庫直接查詢 `information_schema` 得到的即時結果，不是憑印象整理。其中 `nda_work_station_apply` 不是本專案 migration script 建立的表——它由「NDA 工作站申請」流程／SharePoint 同步寫入，但存在同一個 `SDXINTERN` 資料庫裡，本專案的審核流程與 `GET /api/jobcode/{job_code}/nda-check` 都會查詢它，所以列為本專案的第 7 張表。

### ER 關聯總覽

```
tag_definition ──┐
                  │ (N:N，透過 sow_tag_relation)
sow_document ─────┼───────────────────────────────▶ sow_tag_relation
     │            
     ├──(1:N，依 version 累積多筆)────────────────▶ sow_structured_content
     ├──(1:0..1，UNIQUE sow_id)───────────────────▶ sow_review_draft
     ├──(1:N)───────────────────────────────────────▶ sow_review_comment
     └╌╌(非 FK，依 job_code 字串對照)╌╌╌╌╌╌╌╌╌╌╌╌╌╌▶ nda_work_station_apply
```

---

### 1. `sow_document` — 一份 SOW 文件 = 一筆

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `BIGINT` | **PK**，`NOT NULL`，自動遞增（sequence） | SOW 文件唯一識別碼；`sow_structured_content`/`sow_review_draft`/`sow_review_comment`/`sow_tag_relation` 都以此為外鍵關聯起點 |
| `file_name` | `VARCHAR(255)` | `NOT NULL` | 上傳的 PDF 檔名；前端「案件名稱」由此衍生（`common.py` 的 `derive_title()` 去掉底線/副檔名），**不是真正的標題欄位** |
| `s3_key` | `VARCHAR(1024)` | `NOT NULL` | 檔案在 S3 的儲存路徑 |
| `file_hash` | `VARCHAR(64)` | `NOT NULL`，**UNIQUE** | 檔案內容雜湊值，判斷是否為重複上傳的同一份文件，避免對同一份 PDF 重複跑一次 AI 萃取 |
| `page_count` | `INTEGER` | 可為 `NULL`，預設 `0` | PDF 頁數（處理量追蹤用） |
| `char_count` | `INTEGER` | 可為 `NULL`，預設 `0` | 萃取出的文字字元數（處理量追蹤用） |
| `model_version` | `VARCHAR(100)` | 可為 `NULL` | 呼叫 Bedrock 時使用的模型版本，供追溯是哪個模型產出的內容 |
| `dedup_status` | `VARCHAR(50)` | `NOT NULL`，預設 `'PENDING'` | 去重複檢查流程狀態（目前 4 筆實際值皆為 `COMPLETED`），對應 `file_hash` 比對是否完成 |
| `processing_status` | `VARCHAR(50)` | `NOT NULL`，預設 `'PENDING'` | AWS/Bedrock 處理管線狀態（目前 4 筆實際值皆為 `COMPLETED`）。⚠️ 跟下面的 `dri_status`/`manager_status` 是**完全不同的兩條流程**，不要混用：這個管的是「AI 有沒有處理完」，`dri_status`/`manager_status` 管的是「人有沒有審完」 |
| `version` | `INTEGER` | `NOT NULL`，預設 `1` | 文件版本號（同一份 SOW 重新上傳修訂版時遞增），配合 `is_latest` 篩選「這份 SOW 目前的最新文件版本」 |
| `is_latest` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否為該 SOW 的最新版本文件；`GET /api/cases` 只抓 `is_latest = true` |
| `edited_by` | `VARCHAR(100)` | 可為 `NULL` | DRI 送審時的身分標記。**不再是手動輸入**——`review.py` 的 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.dri_mail`（email）自動帶入；查不到 `job_code` 或該筆 `dri_mail` 是 `NULL` 時存空字串。公開 API 的 `creator` 欄位第一順位來源 |
| `approved_by` | `VARCHAR(100)` | 可為 `NULL` | 主管退回／核准時的身分標記，同樣改由 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.manager_mail` 自動帶入；`creator` 欄位第二順位（`edited_by` 為空時使用） |
| `reject_reason` | `TEXT` | 可為 `NULL` | 預留欄位，**目前程式碼未使用**——主管退回理由實際上是寫進 `sow_review_comment`，不是這欄 |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 文件建立時間；前端「上傳時間」來源 |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 最後更新時間。⚠️ 目前 `review.py` 更新 `dri_status`/`manager_status` 等欄位時**不會連動更新這欄**，之後若需要要另外處理 |
| `dri_status` | `VARCHAR(20)` | `NOT NULL`，預設 `'waiting'`，**CHECK** `IN ('waiting','approve')` | DRI 這一側的審核狀態：`waiting`（編輯中，尚未送出／被退回後還沒重新送出）、`approve`（已送出審查，等主管決定）。搭配 `manager_status` 才能還原完整流程階段，見下方狀態對應表 |
| `manager_status` | `VARCHAR(20)` | `NOT NULL`，預設 `'waiting'`，**CHECK** `IN ('waiting','approve','reject')` | 主管這一側的審核狀態：`waiting`（尚未決定）、`reject`（已退回，DRI 重新送出時會自動重置回 `waiting`）、`approve`（已核准發布）。**只有 `dri_status='approve'` 且 `manager_status='approve'` 的文件會出現在對外案例庫** |
| `dri_submitted_at` | `TIMESTAMP` | 可為 `NULL` | DRI 送出審查的時間戳記 |
| `manager_reviewed_at` | `TIMESTAMP` | 可為 `NULL` | 主管最近一次做出決定（退回或核准）的時間戳記 |
| `job_code` | `VARCHAR(100)` | 可為 `NULL`，有索引 `idx_sow_document_job_code`（`migrate_add_job_code.py` 建立），**無唯一約束** | 對照 `nda_work_station_apply.job_code` 的關聯鍵（不是資料庫層 FK，兩張表分屬不同系統）；對應 SOW 檔名裡的 JobCode，目前需人工比對填入。除了決定人天/成本是否用 NDA 權威值，現在也是 `/api/review/cases/{job_code}` 系列路由解析文件的 key——**沒填 `job_code` 就無法進入審核流程**。用途見下方「`nda_work_station_apply`」說明 |

`dri_status` × `manager_status` 狀態對應表（`backend/migrate_dri_manager_status.py` 之前這是單一欄位 `review_status`，四個值分別對應下表四種組合；`backend/review.py` 的 `_derive_status()` 會把兩欄組合推導回這 4 種字串放進 API 回應的 `status` 欄位，`review-frontend` 完全無感知這個拆分）：

| `dri_status` | `manager_status` | 對應舊的 `review_status` | 意義 | 觸發動作 |
|---|---|---|---|---|
| `waiting` | `waiting` | `DRI_REVIEW` | 等 DRI 編輯／送審（新文件預設起點，或退回後 DRI 還沒重新送出） | — |
| `approve` | `waiting` | `MANAGER_REVIEW` | DRI 已送出，等主管審核 | `POST /api/review/cases/{job_code}/submit`（同時把 `manager_status` 重置成 `waiting`） |
| `waiting` | `reject` | `RETURNED_TO_DRI` | 主管退回，`sow_review_draft` 會新增下一版給 DRI 編輯 | `POST /api/review/cases/{job_code}/return` |
| `approve` | `approve` | `PUBLISHED` | 主管已核准，正式對外發布 | `POST /api/review/cases/{job_code}/approve` |

---

### 2. `sow_structured_content` — AI／DRI 編輯後的結構化內容（正式版本）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `BIGINT` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `BIGINT` | `NOT NULL`，**FK** → `sow_document.id` | 對應哪一份 SOW 文件 |
| `version` | `INTEGER` | `NOT NULL` | 內容版本號。`version = 1` 是 AI 原始萃取結果（**不可變**，作為主管審核時的比對基準）；主管核准審核後才會新增 `version = MAX(version)+1` 的新一筆。讀取一律 `ORDER BY version DESC LIMIT 1` 取最新版 |
| `customer_context` | `JSONB` | `NOT NULL` | `{industry_background, challenge, solution, kpis:[{icon,value,label}]}`，對應前端「客戶脈絡與價值」（A 頁籤）。Schema 定義於 `backend/json.txt` 的 `SOW_ANALYSIS_TOOL.customer_context` |
| `project_planning` | `JSONB` | `NOT NULL` | `{owner, team_size, period, man_days, total_cost, deliverables:[string]}`，對應「專案規劃與交付」（B 頁籤）。`man_days`/`total_cost` 是 AI 萃取值；**顯示時**（`build_case()`/`build_review_case()`）若 `sow_document.job_code` 對得到 `nda_work_station_apply` 且該筆 `estimated_mandays`/`total_cost` 非 `NULL`，會被覆蓋成 NDA 權威值——只在讀取當下覆蓋，不會改寫這欄存的內容 |
| `technical_design` | `JSONB` | `NOT NULL` | `{core_functions:[string], architecture_nodes:[string], tech_stack:[string]}`，對應「技術設計與架構」（C 頁籤） |
| `created_at` | `TIMESTAMP` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 這個版本寫入的時間 |

⚠️ 資料庫層**沒有** `(sow_id, version)` 複合唯一約束——同一 `sow_id` 同一 `version` 理論上可以重複插入兩筆。目前靠應用層邏輯維持唯一性（`seed_structured_content.py` 先 `DELETE` 再 `INSERT`；`review.py` 的 `approve` 用 `MAX(version)+1` 計算下一版），若未來有並行寫入（例如兩個人同時核准）要另外加鎖或約束。

---

### 3. `sow_review_draft` — DRI 審核中的暫存內容（新增於審核流程）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id`；屬於複合 **UNIQUE** `(sow_id, version)` | 對應哪一份 SOW 文件；一個 `sow_id` 可以有多筆（多個審核輪次的版本），不再是單一暫存 |
| `version` | `INTEGER` | `NOT NULL`；屬於複合 **UNIQUE** `(sow_id, version)` | 審核輪次版本號，從 `1` 開始（第一次打開審核頁時從 `sow_structured_content version=1` 複製建立）。DRI 在同一版內可以存檔多次（`PUT` 皆為 in-place 更新目前最新版本），**送出審查不會新增版本**——`dri_status` 轉成 `approve` 後，`PUT /draft` 的狀態守門會自動擋掉編輯，等同凍結目前這版；**只有主管退回時才會新增下一版**（複製主管剛審過的內容給 DRI 繼續編輯），如此重複 |
| `customer_context` / `project_planning` / `technical_design` | `JSONB` | `NOT NULL`，預設 `'{}'` | DRI 編輯中的暫存內容，形狀與 `sow_structured_content` 完全相同。主管畫面的「修改後」讀**最新版本**（`ORDER BY version DESC LIMIT 1`）；「原內容」讀 `sow_structured_content WHERE version=1`（固定比對最初的 AI 萃取結果，不隨審核輪次改變） |
| `updated_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 每次 `PUT /api/review/cases/{job_code}/draft` 都會更新目前最新版本這一列。同時也是 API 回應中每個欄位 `savedAt` 的來源——**是整份暫存共用同一個時間戳，不是逐欄位記錄**（相較 mock 版本的簡化） |
| `updated_by` | `TEXT` | 可為 `NULL` | 最後編輯這份暫存的 DRI 身分標記，同樣由 `_resolve_reviewer_email()` 依 `job_code` 自動帶入 `nda_work_station_apply.dri_mail`（不再手動輸入） |

核准（`approve`）時，一律讀**最新版本**（`MAX(version)`）的三個 JSONB 欄位 `INSERT ... SELECT` 進 `sow_structured_content` 成為新版本；退回（`return`）時會立刻 `INSERT` 一筆新版本（`version = MAX(version)+1`，複製主管剛審過那版的內容），DRI 下一輪編輯的是這個新版本，主管審過的舊版本永久保留、不再變動——這樣 `sow_review_draft` 本身就會累積每一輪審核的版本歷史，不用再依賴 `sow_review_comment` 才能回溯「第幾輪改了什麼」。

---

### 4. `sow_review_comment` — 審核留言記錄（append-only）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id` | 對應哪一份 SOW 文件 |
| `author_role` | `VARCHAR(20)` | `NOT NULL`，**CHECK** `IN ('DRI', 'MANAGER')` | 留言者角色 |
| `author_name` | `TEXT` | 可為 `NULL` | 留言者身分標記。**不再是手動輸入**——依留言的 `author_role` 由 `_resolve_reviewer_email()` 查 `nda_work_station_apply.dri_mail`（`DRI`）/`manager_mail`（`MANAGER`）自動帶入 |
| `body` | `TEXT` | `NOT NULL` | 留言內容。DRI 在 Teams 卡片輸入的留言，由 Power Automate 呼叫 `POST /api/review/cases/{job_code}/comments` 寫入；主管退回時的理由也是寫在這裡（`author_role='MANAGER'`） |
| `created_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 留言時間，前端依此由舊到新排序顯示 |

無唯一約束，單純累加記錄，是審核流程裡持續累加留言的歷史紀錄（`sow_review_draft` 現在也有逐輪版本歷史，見上方第 3 張表說明，但留言記錄仍然只存在這裡）。

---

### 5. `sow_tag_relation` — 文件 × 標籤 多對多關聯

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `BIGINT` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `BIGINT` | `NOT NULL`，**FK** → `sow_document.id`；屬於複合 **UNIQUE** `(sow_id, tag_id)` | 對應哪一份 SOW 文件 |
| `tag_id` | `BIGINT` | `NOT NULL`，**FK** → `tag_definition.tag_id`；屬於複合 **UNIQUE** `(sow_id, tag_id)` | 對應哪一個標籤；複合唯一保證同一文件不會重複掛同一個標籤 |
| `tag_source` | `VARCHAR(50)` | `NOT NULL`，預設 `'AUTO_LLM'` | 標籤來源（目前 66 筆全部是 `AUTO_LLM`，代表由 AI 自動判斷；欄位保留供未來人工修正標籤時記錄為其他來源） |
| `reviewed_by` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，**目前程式碼未使用**（標籤的人工審核者） |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 建立時間 |

---

### 6. `tag_definition` — 標籤字典

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `tag_id` | `BIGINT` | **PK**，自動遞增（原欄位名 `id`，已改名） | 內部代理鍵 |
| `tag_category` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(tag_category, tag_name)`（原欄位名 `category`，已改名） | 標籤分類，目前 4 種：`INDUSTRY`（產業）、`SERVICE_DOMAIN`（服務領域）、`USE_CASE`（使用情境）、`TECH_PLATFORM`（技術平台） |
| `tag_name` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(tag_category, tag_name)` | 標籤實際文字，**是人類可讀原文**（例如 `"AI / GenAI"`），不是 code |
| `is_active` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否啟用；查詢標籤時有 `WHERE is_active = true` 過濾，停用的標籤不會出現在前端 |
| `domain` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，對應根目錄 `industry_category_skills.md` 的「領域(Domain)」分類（例如「開發與實作 - 系統開發」）。**目前本專案程式碼未使用、值皆為空**，資料尚未從該檔案灌入 |
| `category` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，對應 `industry_category_skills.md` 的「分類(Category)」（例如「SAP」「後端開發」），跟上面的 `tag_category` 是不同語意的兩個欄位。**目前本專案程式碼未使用、值皆為空** |
| `skill_name` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，對應 `industry_category_skills.md` 的個別技能/工具（例如「Python」「SAP FI」）。**目前本專案程式碼未使用、值皆為空** |

---

### 7. `nda_work_station_apply` — NDA 工作站申請資料（本專案第 7 張表）

這張表源自「NDA 工作站申請」流程，由 SharePoint 同步寫入（欄位對照見根目錄 [`NDA Work Station Apply .md`](./NDA%20Work%20Station%20Apply%20.md)），不是本專案 migration script 建立的表，但存在同一個 `SDXINTERN` 資料庫裡，且本專案有多處程式碼會查詢它（`backend/common.py`、`backend/review.py`、`backend/enrich_jobcode_dri.py`、`backend/app.py` 的 `GET /api/jobcode/{job_code}/nda-check`），因此列為本專案的第 7 張表。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `INTEGER` | **PK**，`NOT NULL`，自動遞增（sequence） | 內部代理鍵 |
| `title` | `VARCHAR(255)` | 可為 `NULL` | 對應 SharePoint 的保密協定／合約名稱標題。**目前本專案程式碼未使用** |
| `job_code` | `VARCHAR(100)` | `NOT NULL`，**無唯一約束**（同一 `job_code` 理論上可重複） | 專案工作碼，對照 `sow_document.job_code` 的關聯鍵（非資料庫層 FK，兩張表分屬不同系統） |
| `send_mail` | `VARCHAR(50)` | 可為 `NULL` | 對應 SharePoint 的郵件通知狀態（如 `done`）。**目前本專案程式碼未使用** |
| `nda_check` | `TEXT` | 可為 `NULL` | 受保密條款約束之成員名單。由 `backend/app.py` 的 `GET /api/jobcode/{job_code}/nda-check`（需帶 `X-API-Key`）對外查詢回傳 |
| `dri_mail` | `VARCHAR(100)` | 可為 `NULL` | DRI 的 email（原欄位名 `dri`，已改名），由 `backend/enrich_jobcode_dri.py` 呼叫 Nebula API 回填。`backend/review.py` 的 `_resolve_reviewer_email()` 用這欄取代審核頁原本手動輸入的姓名，寫入 `sow_document.edited_by`／`sow_review_comment.author_name`（`author_role='DRI'`）／`sow_review_draft.updated_by` |
| `dri_name` | `VARCHAR(100)` | 可為 `NULL` | DRI 的帳號名稱（Nebula API `userJobInfo[0].userName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `dri_fullname` | `VARCHAR(100)` | 可為 `NULL` | DRI 的全名（`userJobInfo[0].userFullName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `dri_deptno` | `VARCHAR(100)` | 可為 `NULL` | DRI 的部門代碼（`userJobInfo[0].deptNo`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `dri_deptname` | `VARCHAR(200)` | 可為 `NULL` | DRI 的部門名稱（`userJobInfo[0].deptName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `manager_mail` | `VARCHAR(100)` | 可為 `NULL` | 主管的 email（原欄位名 `dri_manager`，已改名），同樣由 `enrich_jobcode_dri.py` 回填；`_resolve_reviewer_email()` 用這欄寫入 `sow_document.approved_by`／`sow_review_comment.author_name`（`author_role='MANAGER'`） |
| `manager_name` | `VARCHAR(100)` | 可為 `NULL` | 主管的帳號名稱（`userJobInfo[1].userName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `manager_fullname` | `VARCHAR(100)` | 可為 `NULL` | 主管的全名（`userJobInfo[1].userFullName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `manager_deptno` | `VARCHAR(100)` | 可為 `NULL` | 主管的部門代碼（`userJobInfo[1].deptNo`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `manager_deptname` | `VARCHAR(200)` | 可為 `NULL` | 主管的部門名稱（`userJobInfo[1].deptName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** |
| `estimated_mandays` | `NUMERIC` | 可為 `NULL` | Nebula API 回填的權威人天。`backend/common.py` 的 `fetch_nda_cost()` 在此欄與 `total_cost` 皆非 `NULL` 時，用來覆蓋 `sow_structured_content.project_planning.man_days` 的 AI 萃取值 |
| `total_cost` | `NUMERIC` | 可為 `NULL` | Nebula API 回填的權威成本，用途同上，覆蓋 `project_planning.total_cost` |
| `industry` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，先建欄位、不預先填值。**目前本專案程式碼未使用** |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `now()` | 資料列建立時間 |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `now()` | 最後更新時間；`enrich_jobcode_dri.py` 每次回填 `dri_mail`/`manager_mail`/部門姓名明細/`estimated_mandays`/`total_cost` 時會一併更新這欄 |

---

## 資料流向說明（Data Flow）

### A. 案例建立流程（AI 萃取，`bedrock_service.py` 規劃中、尚未實作）

1. SOW PDF 上傳至 S3 → 寫入一筆 `sow_document`（`processing_status`/`dedup_status` 預設 `PENDING`，`dri_status`/`manager_status` 預設皆為 `waiting`）。
2. Bedrock 依 `backend/json.txt` 定義的 `SOW_ANALYSIS_TOOL` schema 萃取結構化內容：
   - `metadata`（`industry`/`service_domain`/`use_case`/`technology_platform`）→ 正規化寫入 `tag_definition`（不存在則新建）+ `sow_tag_relation`（`tag_source='AUTO_LLM'`）。
   - `customer_context`/`project_planning`/`technical_design` → 寫入 `sow_structured_content`（`version=1`）。
3. `sow_document.processing_status`/`dedup_status` 更新為 `COMPLETED`。此時案例還**不會**出現在對外案例庫（`dri_status`/`manager_status` 仍是 `waiting`/`waiting`）。

### B. 審核發布流程（DRI → 主管，透過 Power Automate + Teams）

1. AWS 處理完成 → Power Automate 收到通知（**此節點在本 repo 之外**，於 Power Automate 網站設定）→ 發 Teams 卡片給 DRI，帶 `/review/dri.html?jobcode={job_code}` 連結。**前提是這份文件的 `sow_document.job_code` 必須已經人工比對填好**，否則連結會 404（審核 API 用 `job_code` 查不到對應文件）。
2. DRI 開啟頁面：`GET /api/review/cases/{job_code}`，後端先用 `job_code`（比對 `sow_document WHERE job_code = ... AND is_latest = true`）解析出內部 `sow_id`，查不到就回 404；解析成功後，若 `sow_review_draft` 還沒有這個 `sow_id` 的暫存，自動從 `sow_structured_content version=1` 複製建立一份。回應的 `manDays`/`totalCost` 額外帶一個 `source: 'nda' | 'ai'`：`job_code` 對得到 `nda_work_station_apply` 且該筆人天/成本非 `NULL` 時是 `'nda'`，這兩個欄位會在頁面上鎖定顯示、不可編輯（跟公開案例庫「所見即所得」）；否則是 `'ai'`，維持可編輯。
3. DRI 編輯內容 → `PUT /api/review/cases/{job_code}/draft` 更新 `sow_review_draft`（`dri_status` 需為 `waiting`，否則 409）。**不用也不能**帶姓名——`updated_by` 由後端依 `job_code` 自動查 `nda_work_station_apply.dri_mail`。
4. DRI 送出審查 → `POST /api/review/cases/{job_code}/submit`（不需 body）：`sow_document.dri_status → approve`、`manager_status → waiting`（重置，避免上一輪 `reject` 殘留），寫入 `dri_submitted_at`/`edited_by`（同樣自動帶入 email）。
5. 留言有兩個管道，都寫進同一張 `sow_review_comment`：① DRI/主管審核頁本身現在就有留言輸入框，前端直接呼叫 `POST /api/review/cases/{job_code}/comments`；② Power Automate 收到 Teams 卡片上的 DRI 留言後也會呼叫同一支 API。兩種情況 `author_name` 都是後端依 `authorRole` 自動查 `nda_work_station_apply.dri_mail`/`manager_mail` 帶入，前端不用（也無法）指定。DRI 留言完成後 Power Automate 通知主管，帶 `/review/manager.html?jobcode={job_code}` 連結。
6. 主管開啟頁面：`GET /api/review/cases/{job_code}` 顯示「原內容（`sow_structured_content version=1`）vs 修改後（`sow_review_draft` 最新版本）」逐欄位 diff，以及留言記錄；`manDays`/`totalCost` 一樣依 `source` 鎖定或可編輯。
7. 主管做出決定（皆不需帶姓名，`approved_by`/留言 `author_name` 自動查 `nda_work_station_apply.manager_mail`）：
   - **核准** → `POST /api/review/cases/{job_code}/approve`：把 `sow_review_draft` **最新版本**的三個 JSONB 欄位 `INSERT ... SELECT` 成 `sow_structured_content` 新版本（`version = MAX(version)+1`），`sow_document.manager_status → approve`（`dri_status` 維持 `approve` 不變），寫入 `manager_reviewed_at`/`approved_by`。**案例自此出現在對外案例庫**。
   - **退回** → `POST /api/review/cases/{job_code}/return`（可選填 `comment`，一併寫入 `sow_review_comment`，`author_role='MANAGER'`）：`sow_document.dri_status → waiting`、`manager_status → reject`，同時 `sow_review_draft` 會立刻新增一筆下一版（複製主管剛審過那版的內容），DRI 回到步驟 3 繼續編輯的是這個新版本，主管審過的舊版本永久保留不動。

### C. 案例庫展示流程（對外，`frontend/`）

1. 使用者開啟 `frontend/index.html` → `loadCases()` → `GET /api/cases`。
2. 後端查詢 `sow_document WHERE is_latest = true AND dri_status = 'approve' AND manager_status = 'approve'`。
3. 對每一筆文件：`fetch_tags()` 取 `INDUSTRY`/`SERVICE_DOMAIN`/`USE_CASE`/`TECH_PLATFORM` 標籤、`fetch_structured_content()` 取最新 `version` 的 JSONB 內容、`fetch_nda_cost(job_code)` 查 `nda_work_station_apply` 的權威人天/成本，組成回應格式（`build_case()`）。`estimated_mandays`/`total_cost` 兩者皆非 `NULL` 時用 `format_number()` 格式化後覆蓋 `project_planning.man_days`/`total_cost`（NDA 值不含幣別符號），否則 fallback 回 AI 萃取值。
4. 前端依角色（Customer / PM / SA，角色累加）呈現 `detail.A`/`B`/`C` 不同深度的內容。

---

## 已知限制

- 審核流程的資料庫變更是用一次性 raw SQL 腳本（`backend/migrate_review_workflow.py`）管理，沒有 Alembic 之類的 migration 工具，schema 異動要手動追蹤。
- `sow_structured_content` 沒有 `(sow_id, version)` 複合唯一約束，版本號唯一性目前靠應用層邏輯保證，非資料庫強制。
- `sow_document.reject_reason`、`sow_tag_relation.reviewed_by`、`nda_work_station_apply.title`/`send_mail` 是預留欄位，目前程式碼完全沒有讀寫。
- `nda_work_station_apply.job_code` 沒有唯一約束，理論上可能有重複列；目前 `common.fetch_nda_cost()`/`review._resolve_reviewer_email()` 都用 `.first()` 只取第一筆，若真的重複會有資料不一致風險。
- `review-frontend/` 連結目前**沒有任何身分驗證**。`author_name`/`edited_by`/`approved_by` 已經從手動輸入姓名改成自動依 `sow_document.job_code` 查 `nda_work_station_apply.dri_mail`/`manager_mail`，但這**仍然不是身分驗證**——任何拿到 Teams 卡片連結的人都能以該 `job_code` 對應的 DRI／主管身分操作，只是不用自己打字；且 `job_code` 沒串接、或 `nda_work_station_apply` 查無資料時會退化成空字串，完全沒有歸屬記錄。
- `sow_review_draft` 現在支援逐輪審核的版本歷史（`(sow_id, version)` 複合唯一）：送出審查不會新增版本（靠 `dri_status`/`manager_status` 狀態機凍結），只有主管退回才會新增下一版；核准一律發布最新版本。`sow_review_comment` 仍是唯一會累積「留言」歷史的地方（版本歷史存的是內容，不是留言）。
- 審核連結（`/review/dri.html?jobcode=`、`/review/manager.html?jobcode=`、`/api/review/cases/{job_code}` 系列路由）改用 `job_code` 當 key 之後，`job_code` 從「填了才有 NDA 權威人天/成本」的加分欄位，變成「不填就無法進入審核流程」的必要前置欄位——`sow_document.job_code` 仍是人工比對填入（見上方 `nda_work_station_apply` 章節），流程上必須先填好 `job_code` 才能讓 Power Automate 產生審核連結。`job_code` 沒有唯一約束，`_resolve_sow_id()` 用 `is_latest = true` + `ORDER BY id DESC LIMIT 1` 取第一筆，若同一 `job_code` 真的出現多筆 `is_latest = true` 的文件會取到不確定的一筆。

更多實作細節（前後端欄位對應、給接手工程師的踩雷筆記）見 [`CLAUDE.md`](./CLAUDE.md)。
