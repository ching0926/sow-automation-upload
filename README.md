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
- **`backend/enrich_jobcode_dri.py`**：批次腳本，呼叫 Nebula API 幫 `nda_work_station_apply` 回填 `dri`/`dri_manager`（email）/`estimated_mandays`/`total_cost` 還是 `NULL` 的資料列。
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
| DRI 審核頁 | `http://127.0.0.1:8000/review/dri.html?id={sow_id}` |
| 主管審核頁 | `http://127.0.0.1:8000/review/manager.html?id={sow_id}` |
| API 文件（FastAPI 自動產生） | `http://127.0.0.1:8000/docs` |

`.env` 需放在專案根目錄，定義 `DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`。**`.env` 含真實密碼，不可提交進版控。**

---

## 資料庫 Schema

資料庫為 **PostgreSQL**（AWS RDS，DB 名稱 `SDXINTERN`），共 6 張核心表，外加透過 `job_code` 對照的 1 張外部表 `nda_work_station_apply`。以下欄位、型態、鍵值皆為實際連線資料庫直接查詢 `information_schema` 得到的即時結果，不是憑印象整理。

### ER 關聯總覽

```
tag_definition ──┐
                  │ (N:N，透過 sow_tag_relation)
sow_document ─────┼───────────────────────────────▶ sow_tag_relation
     │            
     ├──(1:N，依 version 累積多筆)────────────────▶ sow_structured_content
     ├──(1:0..1，UNIQUE sow_id)───────────────────▶ sow_review_draft
     ├──(1:N)───────────────────────────────────────▶ sow_review_comment
     └╌╌(非 FK，依 job_code 字串對照)╌╌╌╌╌╌╌╌╌╌╌╌╌╌▶ nda_work_station_apply（外部表）
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
| `processing_status` | `VARCHAR(50)` | `NOT NULL`，預設 `'PENDING'` | AWS/Bedrock 處理管線狀態（目前 4 筆實際值皆為 `COMPLETED`）。⚠️ 跟下面的 `review_status` 是**完全不同的兩條流程**，不要混用：這個管的是「AI 有沒有處理完」，`review_status` 管的是「人有沒有審完」 |
| `version` | `INTEGER` | `NOT NULL`，預設 `1` | 文件版本號（同一份 SOW 重新上傳修訂版時遞增），配合 `is_latest` 篩選「這份 SOW 目前的最新文件版本」 |
| `is_latest` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否為該 SOW 的最新版本文件；`GET /api/cases` 只抓 `is_latest = true` |
| `edited_by` | `VARCHAR(100)` | 可為 `NULL` | DRI 送審時的身分標記。**不再是手動輸入**——`review.py` 的 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.dri`（email）自動帶入；查不到 `job_code` 或該筆 `dri` 是 `NULL` 時存空字串。公開 API 的 `creator` 欄位第一順位來源 |
| `approved_by` | `VARCHAR(100)` | 可為 `NULL` | 主管退回／核准時的身分標記，同樣改由 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.dri_manager` 自動帶入；`creator` 欄位第二順位（`edited_by` 為空時使用） |
| `reject_reason` | `TEXT` | 可為 `NULL` | 預留欄位，**目前程式碼未使用**——主管退回理由實際上是寫進 `sow_review_comment`，不是這欄 |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 文件建立時間；前端「上傳時間」來源 |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 最後更新時間。⚠️ 目前 `review.py` 更新 `review_status` 等欄位時**不會連動更新這欄**，之後若需要要另外處理 |
| `review_status` | `VARCHAR(20)` | `NOT NULL`，預設 `'DRI_REVIEW'` | 審核狀態機（見下方狀態說明）。**只有 `PUBLISHED` 的文件會出現在對外案例庫** |
| `dri_submitted_at` | `TIMESTAMP` | 可為 `NULL` | DRI 送出審查的時間戳記 |
| `manager_reviewed_at` | `TIMESTAMP` | 可為 `NULL` | 主管最近一次做出決定（退回或核准）的時間戳記 |
| `job_code` | `VARCHAR(100)` | 可為 `NULL`，有索引 `idx_sow_document_job_code`（`migrate_add_job_code.py` 建立） | 對照外部表 `nda_work_station_apply.job_code` 的關聯鍵（不是資料庫層 FK，兩張表分屬不同系統）；對應 SOW 檔名裡的 JobCode，目前需人工比對填入。用途見下方「`nda_work_station_apply`」說明 |

`review_status` 狀態機：

| 值 | 意義 | 觸發動作 |
|---|---|---|
| `DRI_REVIEW` | 等 DRI 編輯／送審（新文件預設起點） | — |
| `MANAGER_REVIEW` | DRI 已送出，等主管審核 | `POST /api/review/cases/{id}/submit` |
| `RETURNED_TO_DRI` | 主管退回，DRI 可繼續編輯同一份暫存 | `POST /api/review/cases/{id}/return` |
| `PUBLISHED` | 主管已核准，正式對外發布 | `POST /api/review/cases/{id}/approve` |

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
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id`，**UNIQUE** | 一個 `sow_id` 只能有一筆暫存（審核中的編輯內容），`UNIQUE` 在資料庫層保證這件事 |
| `customer_context` / `project_planning` / `technical_design` | `JSONB` | `NOT NULL`，預設 `'{}'` | DRI 編輯中的暫存內容，形狀與 `sow_structured_content` 完全相同。主管畫面的「修改後」讀這裡；「原內容」讀 `sow_structured_content WHERE version=1`。第一次打開審核頁時，若暫存不存在會自動從 `version=1` 複製建立一份 |
| `updated_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 每次 `PUT /api/review/cases/{id}/draft` 都會更新。同時也是 API 回應中每個欄位 `savedAt` 的來源——**是整份暫存共用同一個時間戳，不是逐欄位記錄**（相較 mock 版本的簡化） |
| `updated_by` | `TEXT` | 可為 `NULL` | 最後編輯這份暫存的 DRI 身分標記，同樣由 `_resolve_reviewer_email()` 依 `job_code` 自動帶入 `nda_work_station_apply.dri`（不再手動輸入） |

核准（`approve`）時，這張表的三個 JSONB 欄位會被整份 `INSERT ... SELECT` 進 `sow_structured_content` 成為新版本；退回（`return`）時這張表**維持不變**，DRI 下一輪繼續編輯同一份暫存。

---

### 4. `sow_review_comment` — 審核留言記錄（append-only）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id` | 對應哪一份 SOW 文件 |
| `author_role` | `VARCHAR(20)` | `NOT NULL`，**CHECK** `IN ('DRI', 'MANAGER')` | 留言者角色 |
| `author_name` | `TEXT` | 可為 `NULL` | 留言者身分標記。**不再是手動輸入**——依留言的 `author_role` 由 `_resolve_reviewer_email()` 查 `nda_work_station_apply.dri`（`DRI`）/`dri_manager`（`MANAGER`）自動帶入 |
| `body` | `TEXT` | `NOT NULL` | 留言內容。DRI 在 Teams 卡片輸入的留言，由 Power Automate 呼叫 `POST /api/review/cases/{id}/comments` 寫入；主管退回時的理由也是寫在這裡（`author_role='MANAGER'`） |
| `created_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 留言時間，前端依此由舊到新排序顯示 |

無唯一約束，單純累加記錄，是整個審核流程唯一會保留「歷史紀錄」的地方（`sow_review_draft` 只有目前這一份，沒有逐輪歷史）。

---

### 5. `sow_tag_relation` — 文件 × 標籤 多對多關聯

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `BIGINT` | **PK**，自動遞增 | 內部代理鍵 |
| `sow_id` | `BIGINT` | `NOT NULL`，**FK** → `sow_document.id`；屬於複合 **UNIQUE** `(sow_id, tag_id)` | 對應哪一份 SOW 文件 |
| `tag_id` | `BIGINT` | `NOT NULL`，**FK** → `tag_definition.id`；屬於複合 **UNIQUE** `(sow_id, tag_id)` | 對應哪一個標籤；複合唯一保證同一文件不會重複掛同一個標籤 |
| `tag_source` | `VARCHAR(50)` | `NOT NULL`，預設 `'AUTO_LLM'` | 標籤來源（目前 66 筆全部是 `AUTO_LLM`，代表由 AI 自動判斷；欄位保留供未來人工修正標籤時記錄為其他來源） |
| `reviewed_by` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，**目前程式碼未使用**（標籤的人工審核者） |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 建立時間 |

---

### 6. `tag_definition` — 標籤字典

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 |
|---|---|---|---|
| `id` | `BIGINT` | **PK**，自動遞增 | 內部代理鍵 |
| `category` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(category, tag_name)` | 標籤分類，目前 4 種：`INDUSTRY`（產業）、`SERVICE_DOMAIN`（服務領域）、`USE_CASE`（使用情境）、`TECH_PLATFORM`（技術平台） |
| `tag_name` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(category, tag_name)` | 標籤實際文字，**是人類可讀原文**（例如 `"AI / GenAI"`），不是 code |
| `is_active` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否啟用；查詢標籤時有 `WHERE is_active = true` 過濾，停用的標籤不會出現在前端 |

---

### 7. `nda_work_station_apply` — 外部系統表（非本專案 6 張核心表之一）

這張表屬於「NDA 工作站申請」流程（欄位對照見根目錄 [`NDA Work Station Apply .md`](./NDA%20Work%20Station%20Apply%20.md)），不是本專案建的表，本專案只透過 `sow_document.job_code` 查詢，讀取以下欄位：

| 欄位 | 說明 |
|---|---|
| `job_code` | 對照 `sow_document.job_code` 的關聯鍵 |
| `dri` / `dri_manager` | DRI／主管的 email，由 `backend/enrich_jobcode_dri.py` 呼叫 Nebula API 回填。`backend/review.py` 的 `_resolve_reviewer_email()` 用這兩欄取代審核頁原本手動輸入的姓名 |
| `estimated_mandays` / `total_cost` | Nebula API 回填的權威人天／成本。`backend/common.py` 的 `fetch_nda_cost()` 用這兩欄，在兩者皆非 `NULL` 時覆蓋 `sow_structured_content.project_planning` 的 AI 萃取值 |

`nda`/`nda_check`（保密條款約束名單）等其他欄位跟本專案案例知識庫無關，不在這裡列出。

---

## 資料流向說明（Data Flow）

### A. 案例建立流程（AI 萃取，`bedrock_service.py` 規劃中、尚未實作）

1. SOW PDF 上傳至 S3 → 寫入一筆 `sow_document`（`processing_status`/`dedup_status` 預設 `PENDING`，`review_status` 預設 `DRI_REVIEW`）。
2. Bedrock 依 `backend/json.txt` 定義的 `SOW_ANALYSIS_TOOL` schema 萃取結構化內容：
   - `metadata`（`industry`/`service_domain`/`use_case`/`technology_platform`）→ 正規化寫入 `tag_definition`（不存在則新建）+ `sow_tag_relation`（`tag_source='AUTO_LLM'`）。
   - `customer_context`/`project_planning`/`technical_design` → 寫入 `sow_structured_content`（`version=1`）。
3. `sow_document.processing_status`/`dedup_status` 更新為 `COMPLETED`。此時案例還**不會**出現在對外案例庫（`review_status` 仍是 `DRI_REVIEW`）。

### B. 審核發布流程（DRI → 主管，透過 Power Automate + Teams）

1. AWS 處理完成 → Power Automate 收到通知（**此節點在本 repo 之外**，於 Power Automate 網站設定）→ 發 Teams 卡片給 DRI，帶 `/review/dri.html?id={sow_id}` 連結。
2. DRI 開啟頁面：`GET /api/review/cases/{id}`，若 `sow_review_draft` 還沒有這個 `sow_id` 的暫存，自動從 `sow_structured_content version=1` 複製建立一份。回應的 `manDays`/`totalCost` 額外帶一個 `source: 'nda' | 'ai'`：`job_code` 對得到 `nda_work_station_apply` 且該筆人天/成本非 `NULL` 時是 `'nda'`，這兩個欄位會在頁面上鎖定顯示、不可編輯（跟公開案例庫「所見即所得」）；否則是 `'ai'`，維持可編輯。
3. DRI 編輯內容 → `PUT /api/review/cases/{id}/draft` 更新 `sow_review_draft`（`review_status` 需為 `DRI_REVIEW`/`RETURNED_TO_DRI`，否則 409）。**不用也不能**帶姓名——`updated_by` 由後端依 `job_code` 自動查 `nda_work_station_apply.dri`。
4. DRI 送出審查 → `POST /api/review/cases/{id}/submit`（不需 body）：`sow_document.review_status → MANAGER_REVIEW`，寫入 `dri_submitted_at`/`edited_by`（同樣自動帶入 email）。
5. 留言有兩個管道，都寫進同一張 `sow_review_comment`：① DRI/主管審核頁本身現在就有留言輸入框，前端直接呼叫 `POST /api/review/cases/{id}/comments`；② Power Automate 收到 Teams 卡片上的 DRI 留言後也會呼叫同一支 API。兩種情況 `author_name` 都是後端依 `authorRole` 自動查 `nda_work_station_apply.dri`/`dri_manager` 帶入，前端不用（也無法）指定。DRI 留言完成後 Power Automate 通知主管，帶 `/review/manager.html?id={sow_id}` 連結。
6. 主管開啟頁面：`GET /api/review/cases/{id}` 顯示「原內容（`sow_structured_content version=1`）vs 修改後（`sow_review_draft`）」逐欄位 diff，以及留言記錄；`manDays`/`totalCost` 一樣依 `source` 鎖定或可編輯。
7. 主管做出決定（皆不需帶姓名，`approved_by`/留言 `author_name` 自動查 `nda_work_station_apply.dri_manager`）：
   - **核准** → `POST /api/review/cases/{id}/approve`：把 `sow_review_draft` 的三個 JSONB 欄位 `INSERT ... SELECT` 成 `sow_structured_content` 新版本（`version = MAX(version)+1`），`sow_document.review_status → PUBLISHED`，寫入 `manager_reviewed_at`/`approved_by`。**案例自此出現在對外案例庫**。
   - **退回** → `POST /api/review/cases/{id}/return`（可選填 `comment`，一併寫入 `sow_review_comment`，`author_role='MANAGER'`）：`sow_document.review_status → RETURNED_TO_DRI`，`sow_review_draft` 維持不動，DRI 回到步驟 3 繼續編輯同一份暫存。

### C. 案例庫展示流程（對外，`frontend/`）

1. 使用者開啟 `frontend/index.html` → `loadCases()` → `GET /api/cases`。
2. 後端查詢 `sow_document WHERE is_latest = true AND review_status = 'PUBLISHED'`。
3. 對每一筆文件：`fetch_tags()` 取 `INDUSTRY`/`SERVICE_DOMAIN`/`USE_CASE`/`TECH_PLATFORM` 標籤、`fetch_structured_content()` 取最新 `version` 的 JSONB 內容、`fetch_nda_cost(job_code)` 查 `nda_work_station_apply` 的權威人天/成本，組成回應格式（`build_case()`）。`estimated_mandays`/`total_cost` 兩者皆非 `NULL` 時用 `format_number()` 格式化後覆蓋 `project_planning.man_days`/`total_cost`（NDA 值不含幣別符號），否則 fallback 回 AI 萃取值。
4. 前端依角色（Customer / PM / SA，角色累加）呈現 `detail.A`/`B`/`C` 不同深度的內容。

---

## 已知限制

- 審核流程的資料庫變更是用一次性 raw SQL 腳本（`backend/migrate_review_workflow.py`）管理，沒有 Alembic 之類的 migration 工具，schema 異動要手動追蹤。
- `sow_structured_content` 沒有 `(sow_id, version)` 複合唯一約束，版本號唯一性目前靠應用層邏輯保證，非資料庫強制。
- `sow_document.reject_reason`、`sow_tag_relation.reviewed_by` 是預留欄位，目前程式碼完全沒有讀寫。
- `review-frontend/` 連結目前**沒有任何身分驗證**。`author_name`/`edited_by`/`approved_by` 已經從手動輸入姓名改成自動依 `sow_document.job_code` 查 `nda_work_station_apply.dri`/`dri_manager`，但這**仍然不是身分驗證**——任何拿到 Teams 卡片連結的人都能以該 `job_code` 對應的 DRI／主管身分操作，只是不用自己打字；且 `job_code` 沒串接、或 `nda_work_station_apply` 查無資料時會退化成空字串，完全沒有歸屬記錄。
- `sow_review_draft` 是「每個 `sow_id` 一份」的暫存，沒有逐輪審核的版本歷史；`sow_review_comment` 才是唯一會累積歷史的地方。

更多實作細節（前後端欄位對應、給接手工程師的踩雷筆記）見 [`CLAUDE.md`](./CLAUDE.md)。
