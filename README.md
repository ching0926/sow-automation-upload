# SOW 案例知識庫（SOW Solution Knowledge Base）

把過往的 SOW（Statement of Work）文件，透過 AI 萃取成結構化案例資料，並提供內部審核流程與對外案例庫瀏覽。

## 專案簡介

- **案例庫（對外）**：業務／PM／SA 可依角色瀏覽案例，Customer 只看客戶脈絡、PM 多看專案規劃、SA 再多看技術架構（角色累加式揭露）。
- **審核流程（內部）**：SOW PDF 經 AI 萃取後不會直接上架，需經過 DRI 編輯確認、主管核准，才會出現在對外案例庫。
- **通知串接**：AWS 處理完成後透過 Power Automate 發 Teams 卡片通知 DRI／主管，卡片內連結會直接開啟本專案的審核頁面。

## 系統架構

```
SOW PDF ──▶ S3 ──▶ Lambda（lambda_function.py + bedrock_service.py，AI 萃取）──▶ RDS PostgreSQL（SDXINTERN，db_service.py 寫入）
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
- **`review-frontend/`**：DRI／主管審核頁，同樣是純 Vanilla JS。`dri.html`／`manager.html` 共用同一份 `js/app.js`，靠 `window.REVIEW_MODE` 區分行為；案例 `job_code` 從網址 `?jobcode=` 讀取（不是內部的 `sow_document.id`），資料一律來自 `/api/review/*`。
- **`backend/app.py`**（FastAPI）：對外案例庫 API（`GET /api/cases`、`GET /api/cases/{id}`）、客戶「我有興趣」留資 API（`POST /api/cases/{sow_id}/interest`，寫入 `customer` + `sow_customer_interest`）、`GET /api/skill-taxonomy`（供案例平台技能篩選），並用 `StaticFiles` 把 `frontend/` 掛在 `/`、`review-frontend/` 掛在 `/review`。
- **`backend/review.py`**：DRI／主管審核流程 API（`/api/review/*`），含每個 block 的留言 CRUD（`POST`/`PUT`/`DELETE .../comments`）。
- **`backend/common.py`**：`app.py` 與 `review.py` 共用的輔助函式（`fetch_skills()` 查案例技能、結構化內容查詢、標題衍生、`fetch_nda_cost()`/`fetch_nda_department()` 查 NDA 人天/成本/部門權威值等）。
- **`backend/db.py`**：SQLAlchemy 連線設定，讀根目錄 `.env`。
- **`lambda_function.py`**（根目錄）：AWS Lambda 進入點，解析 S3/Power Automate 觸發事件、非同步分流、呼叫 `bedrock_service.py`／`db_service.py`，並把結果回傳給 Power Automate Webhook。
- **`bedrock_service.py`**（根目錄）：組 Prompt、呼叫 Bedrock（失敗時 fallback Gemini），用 `SOW_ANALYSIS_TOOL` schema 限制輸出格式（`metadata.industry` + `metadata.categories[].{category, skills}`、`customer_context`、`project_planning`、`technical_design`）。
- **`db_service.py`**（根目錄）：把 `bedrock_service.py` 的輸出寫進 RDS——`sow_document`（含 `industry`）、`sow_structured_content`（`version=1`）、`skill_list`/`sow_skill_relation`（技能標籤，`category='Other Skills'` 的新技能會一併補進 `tag_definition` 當參考分類）。
- **`backend/migrate_add_job_code.py`**：一次性腳本，幫 `sow_document` 加上 `job_code` 欄位（對照 `nda_work_station_apply.job_code` 用）。
- **`backend/migrate_review_comment_sections.py`**：一次性腳本，補 `sow_review_comment` 的 `(sow_id, author_role, section_key)` 唯一索引（`section_key`/`updated_at` 欄位本身是手動加在資料庫上，這支腳本只補索引，`ADD COLUMN IF NOT EXISTS` 是為了讓其他環境也能一次到位）。
- **`backend/migrate_skill_list.py`**：一次性腳本，把 `industry` backfill 進 `sow_document`、新增 `skill_list` 表並灌入既有技能資料、把 `sow_tag_relation` 改名/改欄位成 `sow_skill_relation`（指向 `skill_list` 而非 `tag_definition`）、砍掉 `tag_definition.tag_category`/`tag_name` 兩欄。
- **`backend/enrich_jobcode_dri.py`**：批次腳本，呼叫 Nebula API 幫 `nda_work_station_apply` 回填 `dri_mail`/`manager_mail`（email）及部門/姓名明細/`estimated_mandays`/`total_cost` 還是 `NULL` 的資料列。
- **`backend/seed_skill_taxonomy.py`**：一次性/可重複執行腳本，把根目錄 `industry_category_skills.md` 的技能分類表（領域 → 分類 → 技能）UPSERT 進 `tag_definition.domain`/`category`/`skill_name`，供 `GET /api/skill-taxonomy` 使用。
- **資料庫**：AWS RDS PostgreSQL，DB 名稱 `SDXINTERN`。

## 開發環境設定

```powershell
# 安裝套件（專案根目錄的 myenv 虛擬環境）
myenv\Scripts\python.exe -m pip install -r backend\requirements.txt

cd backend

# 第一次建置／或需要重灌測試資料時執行（可重複執行）
python seed_structured_content.py          # 灌測試用結構化內容
python migrate_review_workflow.py          # 建立審核流程欄位/資料表，並把既有文件回填為 PUBLISHED
python migrate_skill_list.py               # industry backfill 進 sow_document、建立 skill_list、sow_tag_relation 改名成 sow_skill_relation（破壞性，動正式資料庫前先備份）
python seed_skill_taxonomy.py              # 把 industry_category_skills.md 的技能分類表灌進 tag_definition

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

資料庫為 **PostgreSQL**（AWS RDS，DB 名稱 `SDXINTERN`），共 **11 張表**（含 `nda_work_station_apply`、`customer`、`sow_customer_interest`、`contact`）。以下欄位、型態、鍵值皆為實際連線資料庫直接查詢 `information_schema` 得到的即時結果，不是憑印象整理。其中 `nda_work_station_apply` 不是本專案 migration script 建立的表——它由「NDA 工作站申請」流程／SharePoint 同步寫入，但存在同一個 `SDXINTERN` 資料庫裡，本專案的審核流程與 `GET /api/jobcode/{job_code}/nda-check` 都會查詢它，所以列為本專案的表之一。`customer`／`sow_customer_interest`／`contact` 三張則是**直接在資料庫手動建立**（不是本 repo 任何 migration script 建立的），`backend/app.py` 的「我有興趣」留資功能只讀寫其中 `customer`/`sow_customer_interest` 兩張，`contact` 目前完全沒有本 repo 程式碼讀寫它（見下方第 11 張表說明）。

每張表的欄位表格都新增了「**填入時機**」這一欄，明確標註每個欄位是「一次性寫入後不再變」還是「會隨某個動作更新」，查不到任何寫入程式碼的一律標「目前沒有程式碼會填這個欄位」。**整體要注意**：AI 萃取管線（`lambda_function.py` + `bedrock_service.py` + `db_service.py`）現在**已經實作**，會寫入 `sow_document`（含 `industry`）、`sow_structured_content` 的 `version=1` 內容、`skill_list`/`sow_skill_relation`——但**資料庫裡目前既有的資料列大多是這條管線正式跑起來之前，外部手動灌入或測試腳本（`seed_structured_content.py`）產生的**，不是這條管線的真實產出，閱讀下面表格時「填入時機」欄位若寫「外部手動灌入」，指的是這些既有的舊資料，不代表管線本身不存在。

### ER 關聯總覽

```
skill_list ───────┐
                   │ (N:N，透過 sow_skill_relation)
sow_document ──────┼───────────────────────────────▶ sow_skill_relation
     │
     │  tag_definition（純參考分類表，domain/category/skill_name，
     │                  不透過任何關聯表跟 sow_document 連結，只被
     │                  GET /api/skill-taxonomy 整張查詢使用）
     │
     ├──(1:N，依 version 累積多筆，實務上偶有重複)──▶ sow_structured_content
     ├──(1:N，依 version 累積多筆審核輪次)──────────▶ sow_review_draft
     ├──(1:N，每個角色每個 block 最多一筆)──────────▶ sow_review_comment
     ├──(1:0..1，FK contact_id，目前無程式碼讀寫)───▶ contact
     ├╌╌(非 FK，經 sow_customer_interest 間接關聯)╌▶ customer
     └╌╌(非 FK，依 job_code 字串對照，且不保證唯一)╌▶ nda_work_station_apply

customer ─────────(1:N，複合 PK customer_id+sow_id)──▶ sow_customer_interest ──▶ sow_document
```

---

### 1. `sow_document` — 一份 SOW 文件 = 一筆

⚠️ `sow_document` 核心欄位（`file_name`/`s3_key`/`file_hash`/`page_count`/`char_count`/`model_version`/`dedup_status`/`processing_status`/`industry`）現在**由 `db_service.py::save_sow_analysis_to_db()` 寫入**（Lambda 端，`lambda_function.py` → `bedrock_service.py` → `db_service.py` 這條管線）。但資料庫裡目前既有的資料列大多是這條管線正式跑起來之前，外部手動灌入或測試腳本產生的——「填入時機」欄位寫「外部手動灌入」時，指的是這些既有舊資料，不代表對應欄位現在仍然沒有程式碼會寫。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `BIGINT` | **PK**，`NOT NULL`，自動遞增（sequence） | SOW 文件唯一識別碼；`sow_structured_content`/`sow_review_draft`/`sow_review_comment`/`sow_skill_relation` 都以此為外鍵關聯起點 | 資料庫 sequence 自動產生，一次性、不再變。`db_service.py` 的 `INSERT INTO sow_document ... RETURNING id` 拿到後續寫入用的 `sow_id`；既有列是外部手動灌入 |
| `file_name` | `VARCHAR(255)` | `NOT NULL` | 上傳的 PDF 檔名；前端「案件名稱」由此衍生（`common.py` 的 `derive_title()` 去掉底線/副檔名），**不是真正的標題欄位** | `db_service.py` 在 SOW 處理完成時寫入一次（來自 `payload["file_name"]`，即 S3 key 檔名部分）；既有舊列為外部手動灌入 |
| `s3_key` | `VARCHAR(1024)` | `NOT NULL` | 檔案在 S3 的儲存路徑 | 同上，`db_service.py` 寫入；既有舊列為外部手動灌入 |
| `file_hash` | `VARCHAR(64)` | `NOT NULL`，**UNIQUE** | 檔案內容雜湊值，判斷是否為重複上傳的同一份文件，避免對同一份 PDF 重複跑一次 AI 萃取；`db_service.py` 用它做 `ON CONFLICT (file_hash) DO UPDATE`，同一份檔案重跑會更新既有列而不是新增 | 同上，`db_service.py` 寫入；既有舊列為外部手動灌入 |
| `page_count` | `INTEGER` | 可為 `NULL`，預設 `0` | PDF 頁數（處理量追蹤用） | 同上，`db_service.py` 寫入（來自 `pdf_service.py` 萃取結果） |
| `char_count` | `INTEGER` | 可為 `NULL`，預設 `0` | 萃取出的文字字元數（處理量追蹤用） | 同上，`db_service.py` 寫入 |
| `model_version` | `VARCHAR(100)` | 可為 `NULL` | 呼叫 Bedrock 時使用的模型版本，供追溯是哪個模型產出的內容 | 同上，`db_service.py` 寫入（`payload["provider_used"]`，查無值時預設 `"Claude Haiku 4.5"`） |
| `dedup_status` | `VARCHAR(50)` | `NOT NULL`，預設 `'PENDING'` | 去重複檢查流程狀態，對應 `file_hash` 比對是否完成 | `db_service.py` 固定寫入 `'COMPLETED'`；既有舊列外部手動灌入時就已經是 `COMPLETED` |
| `processing_status` | `VARCHAR(50)` | `NOT NULL`，預設 `'PENDING'` | AWS/Bedrock 處理管線狀態。⚠️ 跟下面的 `dri_status`/`manager_status` 是**完全不同的兩條流程**，不要混用：這個管的是「AI 有沒有處理完」，`dri_status`/`manager_status` 管的是「人有沒有審完」 | `db_service.py` 固定寫入 `'COMPLETED'`；主管核准後 `update_sow_status_to_approved()` 會另外更新成 `'APPROVED'` |
| `version` | `INTEGER` | `NOT NULL`，預設 `1` | 文件版本號（同一份 SOW 重新上傳修訂版時遞增），配合 `is_latest` 篩選「這份 SOW 目前的最新文件版本」 | `db_service.py` 固定寫入 `1`；**目前沒有程式碼會遞增這欄**（重新上傳修訂版的流程尚未實作） |
| `is_latest` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否為該 SOW 的最新版本文件；`GET /api/cases` 只抓 `is_latest = true` | `db_service.py` 固定寫入 `true`；**目前沒有程式碼會更新這欄** |
| `industry` | `VARCHAR(100)` | 可為 `NULL` | 案例產業別，**直接存在這裡**，不再透過 `tag_definition`/標籤系統。案例平台的產業篩選（`getFilterOptions()`）、`build_case()`/`build_review_case()` 的 `industry` 欄位都直接讀這裡，查無值時前端顯示 `"Unknown"` | `db_service.py` 寫入（`payload["metadata"]["industry"]`）；既有舊列由 `migrate_skill_list.py` 一次性從舊的 `tag_definition(tag_category='INDUSTRY')` + `sow_tag_relation` backfill 回填 |
| `edited_by` | `VARCHAR(100)` | 可為 `NULL` | DRI 送審時的身分標記。**不再是手動輸入**——`review.py` 的 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.dri_mail`（email）自動帶入；查不到 `job_code` 或該筆 `dri_mail` 是 `NULL` 時存空字串。公開 API 的 `creator` 欄位第一順位來源 | DRI 第一次送出審查時寫入（`review.py` 的 `submit_for_review()`，`POST /api/review/cases/{job_code}/submit`）；**會隨流程更新**——之後每次重新送審（例如被退回後再送）都會覆寫成當時查到的 `dri_mail` |
| `approved_by` | `VARCHAR(100)` | 可為 `NULL` | 主管退回／核准時的身分標記，同樣改由 `_resolve_reviewer_email()` 依 `job_code` 查 `nda_work_station_apply.manager_mail` 自動帶入；`creator` 欄位第二順位（`edited_by` 為空時使用） | 主管第一次做出決定（退回或核准）時寫入；**會隨流程更新**——每次主管退回（`return_to_dri()`）或核准（`approve_and_publish()`）都會覆寫成當時查到的 `manager_mail` |
| `reject_reason` | `TEXT` | 可為 `NULL` | 預留欄位，**目前程式碼未使用**——主管退回理由實際上是寫進 `sow_review_comment`，不是這欄 | **目前沒有任何程式碼會填這個欄位**，維持預留 |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 文件建立時間；前端「上傳時間」來源 | DB 預設值，隨資料列建立寫入一次；一次性、不再變 |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 最後更新時間。⚠️ 目前 `review.py` 更新 `dri_status`/`manager_status` 等欄位時**不會連動更新這欄**，之後若需要要另外處理 | DB 預設值，隨資料列建立寫入一次；`db_service.py` 的 `ON CONFLICT DO UPDATE` 重跑同一份檔案時會更新成 `CURRENT_TIMESTAMP`；`review.py` 的三個審核 UPDATE 語句都沒有帶這欄 |
| `dri_status` | `VARCHAR(20)` | `NOT NULL`，預設 `'waiting'`，**CHECK** `IN ('waiting','approve')` | DRI 這一側的審核狀態：`waiting`（編輯中，尚未送出／被退回後還沒重新送出）、`approve`（已送出審查，等主管決定）。搭配 `manager_status` 才能還原完整流程階段，見下方狀態對應表 | 初始值 `waiting`（DB 預設）；`submit_for_review()` 送審時 `waiting→approve`；`return_to_dri()` 主管退回時 `approve→waiting` |
| `manager_status` | `VARCHAR(20)` | `NOT NULL`，預設 `'waiting'`，**CHECK** `IN ('waiting','approve','reject')` | 主管這一側的審核狀態：`waiting`（尚未決定）、`reject`（已退回，DRI 重新送出時會自動重置回 `waiting`）、`approve`（已核准發布）。**只有 `dri_status='approve'` 且 `manager_status='approve'` 的文件會出現在對外案例庫** | 初始值 `waiting`（DB 預設）；DRI 送審時同步重置為 `waiting`；主管退回時 `waiting→reject`；主管核准時 `waiting→approve` |
| `dri_submitted_at` | `TIMESTAMP` | 可為 `NULL` | DRI 送出審查的時間戳記 | DRI 第一次送出審查時寫入 `now()`；**會隨流程更新**——每次重新送審都覆寫成最新時間（不保留歷史） |
| `manager_reviewed_at` | `TIMESTAMP` | 可為 `NULL` | 主管最近一次做出決定（退回或核准）的時間戳記 | 主管第一次做決定時寫入 `now()`；**會隨流程更新**——每次退回或核准都覆寫成最新時間 |
| `job_code` | `VARCHAR(100)` | 可為 `NULL`，有索引 `idx_sow_document_job_code`（`migrate_add_job_code.py` 建立），**無唯一約束** | 對照 `nda_work_station_apply.job_code` 的關聯鍵（不是資料庫層 FK，兩張表分屬不同系統）；對應 SOW 檔名裡的 JobCode。除了決定人天/成本/DRI 部門是否用 NDA 權威值，現在也是 `/api/review/cases/{job_code}` 系列路由解析文件的 key——**沒填 `job_code` 就無法進入審核流程**。用途見下方「`nda_work_station_apply`」說明 | `lambda_function.py` 從 S3 key 檔名前 12 碼自動解析出 JobCode（`key.split("/")[-1][:12]`），`db_service.py` 寫入 `sow_document.job_code`；既有舊列是 `migrate_add_job_code.py` 建欄位後，人工比對 SOW 檔名手動填入的，填入後沒有程式碼會再更新它 |
| `contact_id` | `INTEGER` | 可為 `NULL`，**FK** → `contact.id` | 直接在資料庫手動加上的欄位（不是任何 migration script 建立），意圖是關聯到 `contact` 表；**本 repo 完全沒有任何程式碼會讀取或寫入這欄**，是純資料庫層的手動關聯 | 手動在資料庫建立欄位與 FK 後，由外部/手動方式直接 `UPDATE` 填值（現有 5 筆裡只有 1 筆有值）；**沒有程式碼會再更新它** |

`dri_status` × `manager_status` 狀態對應表（`backend/migrate_dri_manager_status.py` 之前這是單一欄位 `review_status`，四個值分別對應下表四種組合；`backend/review.py` 的 `_derive_status()` 會把兩欄組合推導回這 4 種字串放進 API 回應的 `status` 欄位，`review-frontend` 完全無感知這個拆分）：

| `dri_status` | `manager_status` | 對應舊的 `review_status` | 意義 | 觸發動作 |
|---|---|---|---|---|
| `waiting` | `waiting` | `DRI_REVIEW` | 等 DRI 編輯／送審（新文件預設起點，或退回後 DRI 還沒重新送出） | — |
| `approve` | `waiting` | `MANAGER_REVIEW` | DRI 已送出，等主管審核 | `POST /api/review/cases/{job_code}/submit`（同時把 `manager_status` 重置成 `waiting`） |
| `waiting` | `reject` | `RETURNED_TO_DRI` | 主管退回，`sow_review_draft` 會新增下一版給 DRI 編輯 | `POST /api/review/cases/{job_code}/return` |
| `approve` | `approve` | `PUBLISHED` | 主管已核准，正式對外發布 | `POST /api/review/cases/{job_code}/approve` |

⚠️ 這兩欄各自的 `CHECK` 約束只驗證單一欄位的合法值（`dri_status IN ('waiting','approve')`、`manager_status IN ('waiting','approve','reject')`），**資料庫層沒有任何約束禁止兩欄組成不在上表的組合**。目前資料庫裡就有一筆 `dri_status='approve'` + `manager_status='reject'` 的不合法組合（非本 repo 任何 API 路徑產生——三個狀態轉換路由都是同一條 UPDATE 語句一次改兩欄，不可能只改一欄——研判是外部手動改資料庫造成）。遇到不在上表的組合時，`_derive_status()` 目前會 fallback 判成 `"DRI_REVIEW"`，畫面會顯示「DRI 審查中」且欄位可編輯，但這是誤判，不是乾淨的狀態；之後如果要嚴謹一點，可以考慮加一個跨欄位的 `CHECK` 約束或應用層驗證擋掉這四種以外的組合。

---

### 2. `sow_structured_content` — AI／DRI 編輯後的結構化內容（正式版本）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `BIGINT` | **PK**，自動遞增 | 內部代理鍵 | 資料庫 sequence 自動產生，一次性、不再變 |
| `sow_id` | `BIGINT` | `NOT NULL`，**FK** → `sow_document.id` | 對應哪一份 SOW 文件 | 寫入時一次指定，不再變。`version=1` 由 `db_service.py`（正式管線）或 `seed_structured_content.py`（測試資料腳本）寫入；新版本由 `review.py` 的 `approve_and_publish()` 核准時寫入 |
| `version` | `INTEGER` | `NOT NULL` | 內容版本號。`version = 1` 是 AI 原始萃取結果（**不可變**，作為主管審核時的比對基準）；主管核准審核後才會新增 `version = MAX(version)+1` 的新一筆。讀取一律 `ORDER BY version DESC LIMIT 1` 取最新版 | `version=1`：`db_service.py::save_sow_analysis_to_db()` 處理完一份 SOW 時寫入（AI 萃取管線已實作）；既有舊資料是 `seed_structured_content.py` 測試資料腳本一次性灌入的。新版本：只有主管核准（`approve_and_publish()`）這個動作才會新增，`version = MAX(version)+1`；每一版寫入後**不會再被更新**（沒有對這張表的 UPDATE 語句） |
| `customer_context` | `JSONB` | `NOT NULL` | `{industry_background, challenge, solution, kpis:[{value,label}]}`，對應前端「客戶脈絡與價值」（A 頁籤）。Schema 定義於根目錄 `bedrock_service.py` 的 `SOW_ANALYSIS_TOOL.customer_context`（`backend/json.txt` 是同名但已過時的舊版 schema，實際跑的是 `bedrock_service.py` 這份）。⚠️ `kpis` 的形狀已經演進過：舊資料是 `{icon,value,label}`（`value` 是短數字如 `"50%"`），新資料拿掉了 `icon`、`value` 也變成完整句子；後端／前端都已經改成只讀 `value`/`label`，`icon` 就算還留在舊資料的 JSONB 裡也不會再被讀取或顯示，兩種形狀混著存在資料庫裡都能正常運作 | 同 `version` 欄——`version=1` 由 `db_service.py`（或種子腳本）寫入；之後每個新版本是核准時把 `sow_review_draft` 最新版本的內容原樣複製進來，寫入後即凍結 |
| `project_planning` | `JSONB` | `NOT NULL` | `{owner, team_size, period, man_days, total_cost, deliverables:[string]}`，對應「專案規劃與交付」（B 頁籤）。`team_size` 型別是 `integer`/`null`——文件沒提到乙方團隊人數時 AI 填 `null`，前端/審核頁「團隊配置」區塊此時整個不顯示（DRI 編輯模式除外，仍顯示空欄位讓 DRI 手動補上）。`owner`/`man_days`/`total_cost` 是 AI 萃取值；**顯示時**（`build_case()`/`build_review_case()`）若 `sow_document.job_code` 對得到 `nda_work_station_apply` 且對應的 `dri_deptname`/`estimated_mandays`/`total_cost` 非 `NULL`，會被覆蓋成 NDA 權威值當作起始值——審核頁這三個欄位仍然可以編輯（不會鎖定），DRI/主管調整後另外存進 `sow_review_draft`，不會改寫這個欄位存的原始內容 | 同上；`owner`/`man_days`/`total_cost` 存的一律是 AI（或種子腳本）寫入的原始值，`nda_work_station_apply` 的覆蓋只發生在讀取回應／建立審核草稿時，**不會回寫進這個欄位本身** |
| `technical_design` | `JSONB` | `NOT NULL` | `{core_functions:[string], system_modules:[{module_name,responsibility}], underlying_architecture:{summary,data_flow,deployment_environment}}`，對應「技術設計與架構」（C 頁籤）。⚠️ 這個形狀取代了更早期規劃過的 `{core_functions, architecture_nodes, tech_stack}`，如果看到舊文件/舊 commit 提過 `architecture_nodes`/`tech_stack`，那是已經廢棄的舊版 schema | 同上 |
| `created_at` | `TIMESTAMP` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 這個版本寫入的時間 | DB 預設值，隨每筆版本 INSERT 寫入一次，不再變 |

⚠️ 資料庫層**沒有** `(sow_id, version)` 複合唯一約束——同一 `sow_id` 同一 `version` 理論上可以重複插入兩筆。目前靠應用層邏輯維持唯一性（`seed_structured_content.py` 先 `DELETE` 再 `INSERT`；`review.py` 的 `approve` 用 `MAX(version)+1` 計算下一版），若未來有並行寫入（例如兩個人同時核准）要另外加鎖或約束。**這不是純理論風險**：實務上曾經因為手動 SQL 操作，同一個 `sow_id` 的 `version=1` 一度累積到 4 筆重複資料（其中還有兩筆內容真的不一樣、不是單純重複），後來手動清理只保留一筆才恢復正常；`fetch_structured_content()` 在有重複時用 `ORDER BY version DESC LIMIT 1`（沒有次要排序鍵）取值，遇到重複會拿到不確定的一筆。

---

### 3. `sow_review_draft` — DRI 審核中的暫存內容（新增於審核流程）

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵 | 資料庫 sequence 自動產生，一次性、不再變 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id`；屬於複合 **UNIQUE** `(sow_id, version)` | 對應哪一份 SOW 文件；一個 `sow_id` 可以有多筆（多個審核輪次的版本），不再是單一暫存 | 第一次打開審核頁（`GET /api/review/cases/{job_code}` 內部的 `_ensure_draft()`）時自動建立第一筆；一次性、不再變 |
| `version` | `INTEGER` | `NOT NULL`；屬於複合 **UNIQUE** `(sow_id, version)` | 審核輪次版本號，從 `1` 開始（第一次打開審核頁時從 `sow_structured_content version=1` 複製建立）。DRI 在同一版內可以存檔多次（`PUT` 皆為 in-place 更新目前最新版本），**送出審查不會新增版本**——`dri_status` 轉成 `approve` 後，`PUT /draft` 的狀態守門會自動擋掉編輯，等同凍結目前這版；**只有主管退回時才會新增下一版**（複製主管剛審過的內容給 DRI 繼續編輯），如此重複 | `version=1`：`_ensure_draft()` 第一次打開審核頁時建立。之後遞增：**只有主管退回（`return_to_dri()`）才會新增下一版**（`version+1`，複製剛審過那版的內容）；送出審查不會新增版本 |
| `customer_context` / `project_planning` / `technical_design` | `JSONB` | `NOT NULL`，預設 `'{}'` | DRI 編輯中的暫存內容，形狀與 `sow_structured_content` 完全相同。主管畫面的「修改後」讀**最新版本**（`ORDER BY version DESC LIMIT 1`）；「原內容」讀 `sow_structured_content WHERE version=1`（固定比對最初的 AI 萃取結果，不隨審核輪次改變） | 第一次有值：`_ensure_draft()` 建立時從 `sow_structured_content version=1` 複製。**會隨流程更新**：DRI 存檔（`PUT /draft`）時 in-place 更新目前最新版本，可存檔多次；`dri_status != 'waiting'`（已送審）時會被 409 擋掉、不能再更新；主管退回產生的新版本內容先複製自舊版本，之後才由 DRI 再次存檔更新 |
| `updated_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 每次 `PUT /api/review/cases/{job_code}/draft` 都會更新目前最新版本這一列。同時也是 API 回應中每個欄位 `savedAt` 的來源——**是整份暫存共用同一個時間戳，不是逐欄位記錄**（相較 mock 版本的簡化） | 第一次有值：建立時的 DB 預設值 `now()`。**會隨流程更新**：每次 `PUT /draft` 都更新成 `now()`，作用於目前最新版本那一列 |
| `updated_by` | `TEXT` | 可為 `NULL` | 最後編輯這份暫存的 DRI 身分標記，同樣由 `_resolve_reviewer_email()` 依 `job_code` 自動帶入 `nda_work_station_apply.dri_mail`（不再手動輸入） | 建立時（`_ensure_draft()`）不會帶這欄，一開始是 `NULL`；第一次真正有值是 DRI 第一次存檔（`PUT /draft`）時查 `dri_mail` 寫入；**會隨流程更新**——每次存檔都覆寫成當時查到的 email |

核准（`approve`）時，一律讀**最新版本**（`MAX(version)`）的三個 JSONB 欄位 `INSERT ... SELECT` 進 `sow_structured_content` 成為新版本；退回（`return`）時會立刻 `INSERT` 一筆新版本（`version = MAX(version)+1`，複製主管剛審過那版的內容），DRI 下一輪編輯的是這個新版本，主管審過的舊版本永久保留、不再變動——這樣 `sow_review_draft` 本身就會累積每一輪審核的版本歷史，不用再依賴 `sow_review_comment` 才能回溯「第幾輪改了什麼」。

除了上述兩個 API 觸發的版本遞增，也可以直接手動 `INSERT` 一筆新版本（例如從 `sow_structured_content` 某個特定版本的內容複製一份，指定成下一個 `version`），因為只要滿足 `(sow_id, version)` 唯一約束就能寫入——這在需要「讓審核頁重新以某份原始萃取內容為準、但不想動到既有審核歷史」時是合理的手動操作，`build_review_case()` 一樣會用 `MAX(version)` 抓到這筆當作目前版本，不需要額外程式碼支援。

---

### 4. `sow_review_comment` — 審核頁每個 block 的留言（DRI／主管各自最多一則，可編輯/刪除）

⚠️ 這張表原本的定位是「append-only 留言記錄」，但現在已經支援**編輯**與**刪除**（`PUT`/`DELETE`），不再是純累加。舊有的「一般留言」（不綁定特定 block，例如主管退回理由）仍然是 append-only 寫入、沒有編輯/刪除入口；只有**綁定 `section_key` 的 block 留言**才走得到編輯/刪除。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵；`PUT`/`DELETE .../comments/{comment_id}` 用它定位要編輯/刪除哪一則 | 資料庫 sequence 自動產生，一次性、不再變 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id`；跟 `author_role`/`section_key` 一起組成複合 **UNIQUE** 索引 | 對應哪一份 SOW 文件 | INSERT 時指定，一次性、不再變。寫入點：`add_comment()`（`POST /comments`）或 `return_to_dri()` 帶 `comment` 參數時 |
| `author_role` | `VARCHAR(20)` | `NOT NULL`，**CHECK** `IN ('DRI', 'MANAGER')`；跟 `sow_id`/`section_key` 一起組成複合 **UNIQUE** 索引 | 留言者角色。`PUT`/`DELETE` 都要求 request body 帶 `authorRole`，跟資料庫裡這筆的 `author_role` 不符會回 403（沒有真實登入下的簡單防呆，不是真安全機制） | INSERT 時指定，一次性、不再變。`add_comment()` 由呼叫方帶入；`return_to_dri()` 固定寫 `'MANAGER'` |
| `author_name` | `TEXT` | 可為 `NULL` | 留言者身分標記。**不再是手動輸入**——依留言的 `author_role` 由 `_resolve_reviewer_email()` 查 `nda_work_station_apply.dri_mail`（`DRI`）/`manager_mail`（`MANAGER`）自動帶入 | INSERT 當下算出寫入，一次性、**不會再更新**（`PUT` 編輯只改 `body`/`updated_at`，不會重新查一次身分） |
| `body` | `TEXT` | `NOT NULL`，應用層限制 300 字 | 留言內容。DRI 在 Teams 卡片輸入的留言，由 Power Automate 呼叫 `POST /api/review/cases/{job_code}/comments` 寫入；主管退回時的理由也是寫在這裡（`author_role='MANAGER'`）；審核頁每個 block 右側的留言也是寫這欄 | INSERT 時由呼叫方帶入；**會隨編輯更新**——`PUT /comments/{comment_id}` 會覆寫這欄（同時更新 `updated_at`） |
| `created_at` | `TIMESTAMP` | `NOT NULL`，預設 `now()` | 留言第一次寫入的時間，永遠不隨編輯改變；前端依此由舊到新排序顯示 | DB 預設值，隨 INSERT 寫入一次，**編輯留言不會更新這欄**（跟 `updated_at` 分開，才能同時知道「最初何時寫」跟「最後何時改」） |
| `section_key` | `VARCHAR(100)` | 可為 `NULL`；跟 `sow_id`/`author_role` 一起組成複合 **UNIQUE** 索引 `idx_sow_review_comment_one_per_role_section` | 標記這則留言屬於審核頁哪一個 block，格式是前端 `"{tab}.{key}"`（例如 `"A.industryBackground"`、`"A.kpis"`、`"B.deliverables"`），對齊前端內部 dirty-tracking 的路徑命名。`NULL` 代表「不屬於任何 block 的一般留言」（既有的退回理由、Power Automate 留言都是 `NULL`），這類留言目前**沒有在任何畫面顯示**（審核頁只渲染 `section_key` 對得到的留言） | `add_comment()` 由呼叫方決定要不要帶；一次性、不再變（沒有程式碼會更新既有留言的 `section_key`） |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 最後編輯時間；前端拿它跟 `created_at` 比較是否相等來判斷「有沒有被編輯過」，相等就不顯示「已編輯」字樣 | 新增時 DB 預設值等於建立當下的時間（**不是 `NULL`**，這點跟一般「NULL 代表未編輯」的直覺不同，前端已經用 `updated_at !== created_at` 而不是 `updated_at` 是否為空來判斷）；**會隨編輯更新**——`PUT /comments/{comment_id}` 每次都 `SET updated_at = now()` |

唯一約束 `idx_sow_review_comment_one_per_role_section`（`sow_id`, `author_role`, `section_key`）強制「同一角色在同一 block 最多一則留言」——想再留言只能編輯既有那則，`add_comment()` 送出前會先查一次是否已存在（回 409），資料庫的唯一索引則是最後一道防線（`IntegrityError` 兜底也回 409）。PostgreSQL 的唯一索引把每個 `NULL` 視為互不相同，所以 `section_key IS NULL` 的一般留言彼此之間、跟任何有 `section_key` 的留言之間都不受這個限制。

---

### 5. `skill_list` — AI 實際解析出的技能字典（新增，取代舊的標籤通用機制）

每個 `(category, skill)` 組合只存一筆，跟 `sow_skill_relation` 搭配做「哪個 SOW 掛了哪個技能」的多對多關聯。`category` 是 Bedrock 輸出的 PMO 分類名稱（例如 `"生成式 AI (Generative AI)"`）；不在預設清單裡的新技能，`category`/`domain` 一律正規化成 `"Other Skills"`。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `SERIAL` | **PK**，自動遞增 | 內部代理鍵 | 資料庫 sequence 自動產生 |
| `category` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(category, skill)` | 技能所屬的 PMO 分類（跟 `tag_definition.category` 同語意，但這裡存的是 AI 每次實際判斷出的值，不是參考表） | `db_service.py::save_sow_analysis_to_db()` 用 `ON CONFLICT (category, skill) DO UPDATE` 寫入；同一組 `(category, skill)` 被多個 SOW 共用時只會有一筆 |
| `skill` | `VARCHAR(100)` | `NOT NULL`；屬於複合 **UNIQUE** `(category, skill)` | 技能/工具名稱（例如 `"AWS Lambda"`） | 同上 |

---

### 6. `sow_skill_relation` — 文件 × 技能 多對多關聯（原 `sow_tag_relation` 改名沿用）

這張表是原本的 `sow_tag_relation` **直接改名**沿用（保留原本的 `id`/`created_at`/`tag_source`/`reviewed_by` 欄位與資料列），只是外鍵欄位從 `tag_id`（指向 `tag_definition`）改名成 `skill_id`（指向 `skill_list`）。改名時原本掛在 `INDUSTRY`/`SERVICE_DOMAIN`/`USE_CASE` 標籤上的關聯列已被清除（這三種標籤本身也不再使用，`INDUSTRY` 改存 `sow_document.industry`），只保留原本 `TECH_PLATFORM`（技能）的關聯列，並把 `tag_id` 值 remap 成新建的 `skill_list.id`。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵 | 資料庫 sequence 自動產生 |
| `sow_id` | `BIGINT` | `NOT NULL`，**FK** → `sow_document.id`；屬於複合 **UNIQUE** `(sow_id, skill_id)` | 對應哪一份 SOW 文件 | `db_service.py` 寫入；`common.py::fetch_skills()` 讀取供 `build_case()`/`build_review_case()` 組出案例的 `skills`/`skillsByCategory`（案例平台「技術設計與架構」關鍵字區塊、技能篩選） |
| `skill_id` | `BIGINT` | `NOT NULL`，**FK** → `skill_list.id`；屬於複合 **UNIQUE** `(sow_id, skill_id)`（原欄位名 `tag_id`，已改名並改指向 `skill_list`） | 對應哪一個技能；複合唯一保證同一文件不會重複掛同一個技能 | 同上 |
| `tag_source` | `VARCHAR(50)` | `NOT NULL`，預設 `'AUTO_LLM'` | 這筆關聯的來源（目前全部是 `AUTO_LLM`，代表由 AI 自動判斷） | `db_service.py` 固定寫 `'AUTO_LLM'`（沿用改名前的既有值/欄位） |
| `reviewed_by` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，**目前程式碼未使用** | **目前沒有任何程式碼會填這個欄位**，維持預留 |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `CURRENT_TIMESTAMP` | 建立時間 | DB 預設值，隨資料列建立寫入一次，不再變 |

---

### 7. `tag_definition` — 技能分類參考表（已從通用標籤字典瘦身）

⚠️ 這張表原本身兼「通用標籤字典」（`INDUSTRY`/`SERVICE_DOMAIN`/`USE_CASE`/`TECH_PLATFORM` 四種標籤都存在這裡，靠 `tag_category`/`tag_name` 兩欄區分）跟「技能分類參考表」兩種角色。`migrate_skill_list.py` 已經把 **`tag_category`／`tag_name` 兩欄整個砍掉**：`INDUSTRY` 改存 `sow_document.industry`；`SERVICE_DOMAIN`/`USE_CASE` 目前不再使用、資料直接捨棄；`TECH_PLATFORM`（技能）改用 `skill_list`/`sow_skill_relation`。現在這張表**純粹是** `industry_category_skills.md` 的領域→分類→技能參考表，供 `GET /api/skill-taxonomy` 使用，唯一約束也改成 `(category, skill_name)`。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `tag_id` | `BIGINT` | **PK**，自動遞增（原欄位名 `id`，已改名） | 內部代理鍵 | 資料庫 sequence 自動產生 |
| `is_active` | `BOOLEAN` | `NOT NULL`，預設 `true` | 是否啟用；`GET /api/skill-taxonomy` 有 `WHERE is_active = true` 過濾 | DB 預設值 `true`；`seed_skill_taxonomy.py` 寫入時固定帶 `true`。**目前沒有任何程式碼會把它改成 `false`** |
| `domain` | `VARCHAR(100)` | 可為 `NULL` | 對應 `industry_category_skills.md` 的「領域(Domain)」分類（例如「開發與實作 - 系統開發」）；`db_service.py` 新增 `"Other Skills"` 技能時，`domain` 固定寫 `"Other Skills"` | `backend/seed_skill_taxonomy.py` UPSERT 寫入既有分類表內容；`db_service.py` 遇到不在預設清單的新技能時，也會用 `(category, skill_name)` UPSERT 補一筆進來，讓參考表持續收錄新技能。**目前沒有任何程式碼會讀取這欄**（只寫不讀） |
| `category` | `VARCHAR(100)` | 可為 `NULL`；屬於複合 **UNIQUE** `(category, skill_name)` | 對應 `industry_category_skills.md` 的「分類(Category)」（例如「SAP」「後端開發」） | 同 `domain`。**會被讀取**：`app.py` 的 `GET /api/skill-taxonomy`（`WHERE category IS NOT NULL`），供案例平台 SA 角色的技術領域分類篩選使用（注意：案例卡片本身的技能篩選現在改讀 `skill_list`/`sow_skill_relation`，這張表只用於 `/api/skill-taxonomy` 這支「完整分類參考」端點） |
| `skill_name` | `VARCHAR(100)` | 可為 `NULL`；屬於複合 **UNIQUE** `(category, skill_name)` | 對應 `industry_category_skills.md` 的個別技能/工具（例如「Python」「SAP FI」） | 同 `domain`。**會被讀取**：`GET /api/skill-taxonomy` 用它組出每個分類底下的技能選項清單 |

---

### 8. `nda_work_station_apply` — NDA 工作站申請資料（本專案第 8 張表）

這張表源自「NDA 工作站申請」流程，由 SharePoint 同步寫入（欄位對照見根目錄 [`NDA Work Station Apply .md`](./NDA%20Work%20Station%20Apply%20.md)），不是本專案 migration script 建立的表，但存在同一個 `SDXINTERN` 資料庫裡，且本專案有多處程式碼會查詢它（`backend/common.py`、`backend/review.py`、`backend/enrich_jobcode_dri.py`、`backend/app.py` 的 `GET /api/jobcode/{job_code}/nda-check`），因此列為本專案的第 7 張表。

⚠️ 這張表的 `id`/`title`/`job_code`/`send_mail`/`nda_check`/`created_at` 是由 SharePoint 同步流程建立與寫入（本 repo 之外），本專案完全不會寫入這些欄位，只會讀取。`dri_mail` 起到 `updated_at` 這一段十一個欄位，本專案的 `backend/enrich_jobcode_dri.py` 批次腳本才會寫入（呼叫 Nebula API），**這支腳本要人工手動執行**，repo 內沒有排程/自動觸發程式碼。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，`NOT NULL`，自動遞增（sequence） | 內部代理鍵 | SharePoint 同步流程建立（本 repo 之外），一次性、不再變 |
| `title` | `VARCHAR(255)` | 可為 `NULL` | 對應 SharePoint 的保密協定／合約名稱標題。**目前本專案程式碼未使用** | SharePoint 同步寫入（本 repo 之外）。**本專案程式碼完全沒有讀寫這欄** |
| `job_code` | `VARCHAR(100)` | `NOT NULL`，**無唯一約束**（同一 `job_code` 理論上可重複） | 專案工作碼，對照 `sow_document.job_code` 的關聯鍵（非資料庫層 FK，兩張表分屬不同系統） | SharePoint 同步寫入（本 repo 之外）。**本專案程式碼只會讀取**（`fetch_nda_cost()`/`fetch_nda_department()`/`_resolve_reviewer_email()`/`enrich_jobcode_dri.py` 選取待補資料清單），不會寫入或更新 |
| `send_mail` | `VARCHAR(50)` | 可為 `NULL` | 對應 SharePoint 的郵件通知狀態（如 `done`）。**目前本專案程式碼未使用** | SharePoint 同步寫入（本 repo 之外）。**本專案程式碼完全沒有讀寫這欄** |
| `nda_check` | `BOOLEAN` | 可為 `NULL` | 是否受保密條款約束（原本型態是 `TEXT`，存成員名單，已改成 `BOOLEAN` 布林旗標，語意跟著變成「是/否」而不是名單內容）。由 `backend/app.py` 的 `GET /api/jobcode/{job_code}/nda-check`（需帶 `X-API-Key`）對外查詢回傳 | SharePoint 同步寫入（本 repo 之外）。**本專案程式碼只會讀取**（`GET /api/jobcode/{job_code}/nda-check`），不會寫入 |
| `dri_mail` | `VARCHAR(100)` | 可為 `NULL` | DRI 的 email（原欄位名 `dri`，已改名），由 `backend/enrich_jobcode_dri.py` 呼叫 Nebula API 回填。`backend/review.py` 的 `_resolve_reviewer_email()` 用這欄取代審核頁原本手動輸入的姓名，寫入 `sow_document.edited_by`／`sow_review_comment.author_name`（`author_role='DRI'`）／`sow_review_draft.updated_by` | `enrich_jobcode_dri.py` 批次腳本呼叫 Nebula API（`userJobInfo[0].companyEmail`）回填，只處理該筆 11 個欄位中任一還是 `NULL` 的 `job_code`；**需人工手動跑**、可重複執行；重跑時若該筆仍有欄位缺值，會連同已有值的欄位一起覆寫成 API 當下的最新回應 |
| `dri_name` | `VARCHAR(100)` | 可為 `NULL` | DRI 的帳號名稱（Nebula API `userJobInfo[0].userName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同 `dri_mail` 的回填時機與更新規則。**其餘程式碼未使用**（只寫不讀） |
| `dri_fullname` | `VARCHAR(100)` | 可為 `NULL` | DRI 的全名（`userJobInfo[0].userFullName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `dri_deptno` | `VARCHAR(100)` | 可為 `NULL` | DRI 的部門代碼（`userJobInfo[0].deptNo`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `dri_deptname` | `VARCHAR(200)` | 可為 `NULL` | DRI 的部門名稱（`userJobInfo[0].deptName`），由 `enrich_jobcode_dri.py` 回填。**有被讀取使用**——`common.py` 的 `fetch_nda_department()` 查詢它，`app.py`/`review.py` 用來組成對外案例庫回應的 `driDepartment` 欄位，**也是**案例平台/審核頁「DRI 部門」欄位（原「DRI 負責人」）的權威來源，審核頁會拿它當 `project_planning.owner` 的起始值（可再編輯） | 同 `dri_mail` 的回填時機與更新規則；寫入後會被 `fetch_nda_department()` 讀取 |
| `manager_mail` | `VARCHAR(100)` | 可為 `NULL` | 主管的 email（原欄位名 `dri_manager`，已改名），同樣由 `enrich_jobcode_dri.py` 回填；`_resolve_reviewer_email()` 用這欄寫入 `sow_document.approved_by`／`sow_review_comment.author_name`（`author_role='MANAGER'`） | 同 `dri_mail`，但取 `userJobInfo[1].companyEmail`（主管） |
| `manager_name` | `VARCHAR(100)` | 可為 `NULL` | 主管的帳號名稱（`userJobInfo[1].userName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `manager_fullname` | `VARCHAR(100)` | 可為 `NULL` | 主管的全名（`userJobInfo[1].userFullName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `manager_deptno` | `VARCHAR(100)` | 可為 `NULL` | 主管的部門代碼（`userJobInfo[1].deptNo`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `manager_deptname` | `VARCHAR(200)` | 可為 `NULL` | 主管的部門名稱（`userJobInfo[1].deptName`），由 `enrich_jobcode_dri.py` 回填。**目前本專案程式碼未使用** | 同上，**其餘程式碼未使用** |
| `estimated_mandays` | `NUMERIC` | 可為 `NULL` | Nebula API 回填的權威人天。`backend/common.py` 的 `fetch_nda_cost()` 在此欄與 `total_cost` 皆非 `NULL` 時，用來覆蓋 `sow_structured_content.project_planning.man_days` 的 AI 萃取值 | 同 `dri_mail` 的回填時機與更新規則（Nebula API 的 `estimatedMandays`）；寫入後被 `fetch_nda_cost()` 讀取用於**顯示時覆蓋**，不會回寫進 `sow_structured_content` |
| `total_cost` | `NUMERIC` | 可為 `NULL` | Nebula API 回填的權威成本，用途同上，覆蓋 `project_planning.total_cost` | 同上（Nebula API 的 `totalCost`） |
| `industry` | `VARCHAR(100)` | 可為 `NULL` | 預留欄位，先建欄位、不預先填值。**目前本專案程式碼未使用** | `migrate_add_dri_manager_details.py` 只新增欄位、不填值。**目前沒有任何程式碼會填這個欄位，也沒有任何程式碼會讀取它** |
| `created_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `now()` | 資料列建立時間 | SharePoint 同步流程建立時的 DB 預設值 `now()`（本 repo 之外），一次性、不再變 |
| `updated_at` | `TIMESTAMPTZ` | 可為 `NULL`，預設 `now()` | 最後更新時間；`enrich_jobcode_dri.py` 每次回填 `dri_mail`/`manager_mail`/部門姓名明細/`estimated_mandays`/`total_cost` 時會一併更新這欄 | `enrich_jobcode_dri.py` 每次批次回填成功時 `SET updated_at = now()`（逐筆提交）；SharePoint 同步流程理論上也可能更新這欄，但那部分在本 repo 之外，無法從程式碼確認 |

---

### 9. `customer` — 客戶「我有興趣」留資記錄

直接在資料庫手動建立（不是本 repo migration script 建立），由 `backend/app.py` 的 `POST /api/cases/{sow_id}/interest`（案例平台「我有興趣」按鈕）寫入。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵；沒有對外的文字客戶代碼欄位 | 資料庫 sequence 自動產生，一次性、不再變 |
| `email` | `VARCHAR(100)` | 可為 `NULL`，**無唯一約束** | 客戶留下的聯絡 email。**沒有 email 去重機制**——同一個 email 每次送出「確認聯繫」都會新增一筆新的 `customer` 資料列，不會合併成同一個客戶 | `submit_interest()` 寫入時由前端表單帶入，一次性、不再變 |
| `comment` | `TEXT` | 可為 `NULL` | 客戶留言（選填欄位），對應前端「留言（選填）」文字框 | 同上，一次性、不再變 |

---

### 10. `sow_customer_interest` — 客戶留資 × 案例 關聯

記錄「哪一筆 `customer` 留資是針對哪個 `sow_document`」，跟 `customer` 一起由 `POST /api/cases/{sow_id}/interest` 在同一次請求裡寫入（先 INSERT `customer` 拿到新 `id`，再 INSERT 這張表）。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `customer_id` | `INTEGER` | `NOT NULL`，**FK** → `customer.id`；跟 `sow_id` 組成複合 **PK** | 對應哪一筆客戶留資 | INSERT 時指定，一次性、不再變 |
| `sow_id` | `INTEGER` | `NOT NULL`，**FK** → `sow_document.id`；跟 `customer_id` 組成複合 **PK** | 對應哪一份 SOW 案例 | 同上 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，預設 `CURRENT_TIMESTAMP` | 留資時間 | DB 預設值，隨 INSERT 寫入一次，不再變 |

⚠️ 複合 PK `(customer_id, sow_id)` 只保證「同一筆 `customer` 資料列不會對同一個案例重複留資」，但因為 `customer` 本身每次送出都會新增新的一筆（見上表，沒有 email 去重），**同一個人**（同一個 email）針對同一個案例還是可以透過建立多筆新 `customer` 資料列來重複留資多次——複合 PK 沒有在人的層級擋掉重複，只在資料列層級擋。

---

### 11. `contact` — 目前沒有本 repo 程式碼使用的表

直接在資料庫手動建立，`sow_document.contact_id` 有 FK 指向這張表的 `id`（見第 1 張表），但**本 repo 完全沒有任何程式碼會 `SELECT`/`INSERT`/`UPDATE` 這張表**——現有的關聯（`sow_document.id=1` 的 `contact_id` 指向這張表裡的一筆資料）是外部手動建立與連結的，跟「我有興趣」留資功能用的 `customer`/`sow_customer_interest` 是兩套完全獨立、不相干的機制，不要混淆。

| 欄位 | 型態 | 條件 / 鍵值 | 對應業務邏輯 | 填入時機 |
|---|---|---|---|---|
| `id` | `INTEGER` | **PK**，自動遞增 | 內部代理鍵，被 `sow_document.contact_id` FK 引用 | 資料庫 sequence 自動產生。**目前沒有程式碼會 INSERT 這張表**，現有 1 筆為外部/手動灌入 |
| `email` | `VARCHAR(100)` | `NOT NULL` | 用途不明，**目前本專案程式碼完全未使用** | 外部/手動灌入，**沒有任何程式碼會讀寫這欄** |

---

## 資料流向說明（Data Flow）

### A. 案例建立流程（AI 萃取，已實作：`lambda_function.py` + `bedrock_service.py` + `db_service.py`）

1. Power Automate／S3 觸發 `lambda_function.py`：解析事件（S3 觸發或 Power Automate 帶 `bucket`/`key`），非同步分流叫醒自己背景執行，等 S3 物件確定存在後，用 `pdf_service.py` 從 S3 讀出 PDF 文字，再用 `security_utils.py` 做 PII 去識別化。
2. `bedrock_service.py::invoke_sow_analysis()` 呼叫 Bedrock（`us.anthropic.claude-haiku-4-5-20251001-v1:0`），用 `SOW_ANALYSIS_TOOL` schema 強制輸出結構化結果（`metadata.industry` + `metadata.categories[].{category, skills}`、`customer_context`、`project_planning`、`technical_design`）；Bedrock 失敗時 fallback 呼叫 Gemini。
3. `db_service.py::save_sow_analysis_to_db()` 把結果寫進 RDS（同一個交易內）：
   - `sow_document`：含 `job_code`（從 S3 key 檔名前 12 碼解析）、`file_name`/`s3_key`/`file_hash`/`page_count`/`char_count`/`industry`/`model_version`，`dedup_status`/`processing_status` 固定寫 `'COMPLETED'`，`dri_status`/`manager_status` 沿用 DB 預設 `waiting`/`waiting`。
   - `customer_context`/`project_planning`/`technical_design` → 寫入 `sow_structured_content`（`version=1`）。
   - `metadata.categories[].skills` → 正規化寫入 `skill_list`（不存在則新建）+ `sow_skill_relation`（`tag_source='AUTO_LLM'`）；`category` 不在預設清單的新技能會正規化成 `"Other Skills"`，同時補一筆進 `tag_definition`（`domain`/`category` 都是 `"Other Skills"`），讓參考分類表持續收錄新技能。
4. 此時案例還**不會**出現在對外案例庫（`dri_status`/`manager_status` 仍是 `waiting`/`waiting`），要等審核流程（見下方 B）跑完。

### B. 審核發布流程（DRI → 主管，透過 Power Automate + Teams）

1. AWS 處理完成 → Power Automate 收到通知（**此節點在本 repo 之外**，於 Power Automate 網站設定）→ 發 Teams 卡片給 DRI，帶 `/review/dri.html?jobcode={job_code}` 連結。**前提是這份文件的 `sow_document.job_code` 必須已經人工比對填好**，否則連結會 404（審核 API 用 `job_code` 查不到對應文件）。
2. DRI 開啟頁面：`GET /api/review/cases/{job_code}`，後端先用 `job_code`（比對 `sow_document WHERE job_code = ... AND is_latest = true`）解析出內部 `sow_id`，查不到就回 404；解析成功後，若 `sow_review_draft` 還沒有這個 `sow_id` 的暫存，自動從 `sow_structured_content version=1` 複製建立一份——**建立當下**如果 `job_code` 對得到 `nda_work_station_apply` 且該筆 `dri_deptname`/`estimated_mandays`/`total_cost` 非 `NULL`，會直接把這幾個 NDA 權威值種進新建的草稿，取代 AI 猜測值當起始值。`owner`（DRI 部門）/`manDays`/`totalCost` 這三個欄位**在審核階段都可以編輯**（不會鎖定）——不管起始值是不是來自 NDA，DRI／主管都能再自行調整、存進 `sow_review_draft`；`teamSize` 若是 `null`（AI 在文件裡沒提到乙方團隊人數），DRI 編輯模式仍顯示空欄位（標題會帶「無團隊總人數資料，若有請手動新增」提示）讓 DRI 手動補上，但主管唯讀視圖跟公開案例庫在 `teamSize` 為 `null` 時「團隊配置」整個區塊都不會顯示。
3. DRI 編輯內容 → `PUT /api/review/cases/{job_code}/draft` 更新 `sow_review_draft`（`dri_status` 需為 `waiting`，否則 409）。**不用也不能**帶姓名——`updated_by` 由後端依 `job_code` 自動查 `nda_work_station_apply.dri_mail`。
4. DRI 送出審查 → `POST /api/review/cases/{job_code}/submit`（不需 body）：`sow_document.dri_status → approve`、`manager_status → waiting`（重置，避免上一輪 `reject` 殘留），寫入 `dri_submitted_at`/`edited_by`（同樣自動帶入 email）。
5. **審核頁本身現在有留言 UI**：每個 block（例如「產業背景」「客戶效益」〔原「關鍵成效指標 (KPIs)」，已改名對齊案例平台的稱呼，內文一樣讀 `customer_context.kpis`〕）右側都有留言區，DRI／主管都能各自在自己的框框輸入留言，一次最多一則（`section_key` + `author_role` + `sow_id` 複合唯一索引擋重複），可以編輯或刪除自己的留言，對方的留言唯讀。這些留言前端直接呼叫 `POST`（新增，帶 `sectionKey`）/`PUT`/`DELETE /api/review/cases/{job_code}/comments/...`，`author_name` 由後端依 `authorRole` 自動查 `nda_work_station_apply.dri_mail`/`manager_mail` 帶入，呼叫方不用（也無法）指定姓名，只能宣稱 `authorRole`（`PUT`/`DELETE` 會檢查跟資料庫裡那則留言的 `author_role` 是否一致，不一致回 403）。**跟 Power Automate／Teams 卡片留言是兩條不相干的路徑**：Teams 卡片上的留言（DRI 提交、主管退回理由）一樣是呼叫這組 API 寫入，但不帶 `sectionKey`（存成 `NULL`，「一般留言」），這類留言目前**沒有在審核頁畫面上顯示**，只有帶 `sectionKey` 的 block 留言才會顯示。DRI 完成編輯、Power Automate 通知主管，帶 `/review/manager.html?jobcode={job_code}` 連結。
6. 主管開啟頁面：`GET /api/review/cases/{job_code}` 顯示每個欄位「DRI 修改於 {時間}」（`sow_review_draft` 最新版本 vs `sow_structured_content version=1` 只用來判斷有沒有修改，不再顯示逐欄位的「原內容/修改後」文字對照），以及上述的 block 留言區；主管視圖是唯讀的，`teamSize` 為 `null` 時「團隊配置」整列不顯示，其餘欄位照常顯示。
7. 主管做出決定（皆不需帶姓名，`approved_by`/留言 `author_name` 自動查 `nda_work_station_apply.manager_mail`）：
   - **核准** → `POST /api/review/cases/{job_code}/approve`：把 `sow_review_draft` **最新版本**的三個 JSONB 欄位 `INSERT ... SELECT` 成 `sow_structured_content` 新版本（`version = MAX(version)+1`），`sow_document.manager_status → approve`（`dri_status` 維持 `approve` 不變），寫入 `manager_reviewed_at`/`approved_by`。**案例自此出現在對外案例庫**。
   - **退回** → `POST /api/review/cases/{job_code}/return`（可選填 `comment`，一併寫入 `sow_review_comment`，`author_role='MANAGER'`）：`sow_document.dri_status → waiting`、`manager_status → reject`，同時 `sow_review_draft` 會立刻新增一筆下一版（複製主管剛審過那版的內容），DRI 回到步驟 3 繼續編輯的是這個新版本，主管審過的舊版本永久保留不動。

### C. 案例庫展示流程（對外，`frontend/`）

1. 使用者開啟 `frontend/index.html` → `loadCases()` → `GET /api/cases`。
2. 後端查詢 `sow_document WHERE is_latest = true AND dri_status = 'approve' AND manager_status = 'approve'`。
3. 對每一筆文件：`industry` 直接讀 `sow_document.industry`（查無值時前端顯示 `"Unknown"`）；`fetch_skills()` 查 `sow_skill_relation`/`skill_list` 取這份文件掛的技能（`skills`/`techCategory`/`skillsByCategory`，供「技術設計與架構」關鍵字區塊跟 SA 角色的技能篩選使用）；`fetch_structured_content()` 取最新 `version` 的 JSONB 內容；`fetch_nda_cost(job_code)`/`fetch_nda_department(job_code)` 查 `nda_work_station_apply` 的權威人天/成本/部門，組成回應格式（`build_case()`）。`estimated_mandays`/`total_cost` 非 `NULL` 時用 `format_number()` 格式化後覆蓋 `project_planning.man_days`/`total_cost`（NDA 值不含幣別符號）；`dri_deptname` 非 `NULL` 時覆蓋 `owner`（DRI 部門），否則都 fallback 回 AI 萃取值。`serviceCategory`/`useCase` 目前固定回傳空陣列（`SERVICE_DOMAIN`/`USE_CASE` 標籤已不再使用）。
4. 前端依角色（Customer / PM / SA，角色累加）呈現 `detail.A`/`B`/`C` 不同深度的內容；`getFilterOptions()` 的產業/技術分類/技能篩選選項都直接從已載入的案例資料（`c.industry`/`c.techCategory`/`c.skillsByCategory`）算出，只顯示「實際有案例在用」的選項，不會顯示技能分類參考表（`tag_definition`）裡有、但沒有任何案例實際掛過的選項。

### D. 客戶留資（「我有興趣」）流程（對外，`frontend/`）

1. Customer 角色開啟案例、點「我有興趣」→ 確認卡片顯示真實檔名（`sow_document.file_name` 去掉前 12 碼 jobcode，`build_case()` 的 `contactItemName` 欄位）、必填 Email、選填留言。
2. 送出後呼叫 `POST /api/cases/{sow_id}/interest`：後端驗證 Email 格式、確認 `sow_id` 對應的 `sow_document` 存在，接著 `INSERT INTO customer (email, comment)`拿到新 `id`，再 `INSERT INTO sow_customer_interest (customer_id, sow_id)` 建立關聯。
3. 兩個 INSERT 在同一個 request 內完成，**沒有交易上的特殊處理**，也**沒有** email 去重——同一個人對同一個案例重複點「確認聯繫」，每次都會新增一筆全新的 `customer` + `sow_customer_interest` 資料列（見上方第 9、10 張表說明）。
4. 這條流程完全獨立於審核流程（不會動到 `sow_document`/`sow_structured_content` 任何欄位），業務團隊目前**沒有任何介面**可以查看 `customer`/`sow_customer_interest` 的留資紀錄——資料寫進資料庫後，只能直接查 DB，本 repo 沒有對應的後台列表頁面或 API。

---

## 已知限制

- 審核流程的資料庫變更是用一次性 raw SQL 腳本（`backend/migrate_review_workflow.py`、`backend/migrate_review_comment_sections.py` 等）管理，沒有 Alembic 之類的 migration 工具，schema 異動要手動追蹤；且好幾個欄位（`sow_document.contact_id`、`sow_review_comment.section_key`/`updated_at`、`nda_work_station_apply.nda_check` 的型態變更）是**直接在資料庫手動改的，完全沒有對應的 migration script**，repo 裡的程式碼是事後才追上去配合，之後如果要重建一份乾淨的資料庫，光跑現有的 migration script 並不會重現目前的完整 schema。
- `sow_structured_content` 沒有 `(sow_id, version)` 複合唯一約束，版本號唯一性目前靠應用層邏輯保證，非資料庫強制——**這不是純理論風險**，已經實際發生過同一 `sow_id` 的 `version=1` 累積到 4 筆重複（其中還有內容互相衝突的），後來手動清理過。
- `sow_document.dri_status`/`manager_status` 各自的 `CHECK` 約束只驗證單一欄位合法值，資料庫層沒有阻止兩欄組成不在合法狀態表裡的組合——目前資料庫裡就有一筆 `approve`/`reject` 的不合法組合，會被 `_derive_status()` 誤判成 `DRI_REVIEW`。
- `sow_document.reject_reason`、`sow_skill_relation.reviewed_by`、`nda_work_station_apply.title`/`send_mail`、`sow_document.contact_id`、`contact` 整張表是預留欄位或手動建立但目前程式碼完全沒有讀寫。
- `nda_work_station_apply.job_code` 沒有唯一約束，理論上可能有重複列；目前 `common.fetch_nda_cost()`/`review._resolve_reviewer_email()` 都用 `.first()` 只取第一筆，若真的重複會有資料不一致風險。`sow_document.job_code` 同樣沒有唯一約束，目前資料庫裡 5 筆文件只有 2 個不同的 `job_code`。
- `review-frontend/` 連結目前**沒有任何身分驗證**。`author_name`/`edited_by`/`approved_by` 已經從手動輸入姓名改成自動依 `sow_document.job_code` 查 `nda_work_station_apply.dri_mail`/`manager_mail`，但這**仍然不是身分驗證**——任何拿到 Teams 卡片連結的人都能以該 `job_code` 對應的 DRI／主管身分操作，只是不用自己打字；且 `job_code` 沒串接、或 `nda_work_station_apply` 查無資料時會退化成空字串，完全沒有歸屬記錄。審核頁的 block 留言編輯/刪除也只靠 `authorRole` 防呆（見第 4 張表），同樣不是真正的身分驗證。
- `sow_review_draft` 現在支援逐輪審核的版本歷史（`(sow_id, version)` 複合唯一）：送出審查不會新增版本（靠 `dri_status`/`manager_status` 狀態機凍結），只有主管退回才會新增下一版；核准一律發布最新版本；也可以手動 INSERT 額外版本（例如從 `sow_structured_content` 特定版本重新灌一份進來）。`sow_review_comment` 現在同時是「一般留言」的 append-only 記錄，也是「block 留言」可編輯/刪除的地方，兩種語意共用同一張表，靠 `section_key` 是否為 `NULL` 區分。
- 審核連結（`/review/dri.html?jobcode=`、`/review/manager.html?jobcode=`、`/api/review/cases/{job_code}` 系列路由）改用 `job_code` 當 key 之後，`job_code` 從「填了才有 NDA 權威人天/成本」的加分欄位，變成「不填就無法進入審核流程」的必要前置欄位——`sow_document.job_code` 仍是人工比對填入（見上方 `nda_work_station_apply` 章節），流程上必須先填好 `job_code` 才能讓 Power Automate 產生審核連結。`job_code` 沒有唯一約束，`_resolve_sow_id()` 用 `is_latest = true` + `ORDER BY id DESC LIMIT 1` 取第一筆，若同一 `job_code` 真的出現多筆 `is_latest = true` 的文件會取到不確定的一筆。
- 「我有興趣」留資功能（`customer`/`sow_customer_interest`）沒有任何後台可以查看留資紀錄，也沒有 email 去重——同一人對同一案例可以重複留資產生多筆獨立資料列（見上方第 9、10 張表）。跟這兩張表功能相關但完全沒被使用的 `contact` 表（第 11 張表）容易讓人誤以為跟客戶留資是同一套機制，實際上兩者無關。
- `migrate_skill_list.py` 是破壞性 migration（`DROP COLUMN`、`DELETE`、表格改名），把 `tag_definition.tag_category`/`tag_name` 砍掉、`SERVICE_DOMAIN`/`USE_CASE` 標籤資料永久捨棄前沒有自動備份機制，執行前務必手動備份 `tag_definition`/`sow_tag_relation`（已經在正式環境執行過一次，過程中也修掉兩個只有真實資料量才會暴露的 bug：舊 FK 沒先卸載導致 remap 失敗、id 對調時的 `UNIQUE (sow_id, tag_id)` 瞬間衝突，見腳本內註解）。
- `nda_work_station_apply.estimated_mandays` 可能是非整數（例如 `10.1`），审核頁把它當草稿初始值種進 `sow_review_draft.project_planning.man_days` 時要存成格式化後的字串（`format_number()` 的輸出），不能直接 `CAST AS int`，否則會把小數點截斷成整數、造成 `original`/`current` 顯示不一致——這是實際踩過的 bug，已修正。
- `sow_structured_content.customer_context.kpis` 的 JSONB 形狀正在演進中（舊資料 `{icon,value,label}`，新資料 `{value,label}` 且 `value` 從短數字變成完整句子），資料庫沒有 schema 驗證會擋不一致的形狀，全靠前後端程式碼用 `.get(key, default)` 寬鬆讀取來相容兩種形狀。

更多實作細節（前後端欄位對應、給接手工程師的踩雷筆記）見 [`CLAUDE.md`](./CLAUDE.md)。
