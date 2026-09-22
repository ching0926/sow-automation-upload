import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
REVIEW_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "review-frontend"

NEBULA_API_BASE = os.getenv("NEBULA_API_BASE", "https://api.nebula.sit.ecvhrm.com")
NEBULA_CLIENT_ID = os.getenv("NEBULA_CLIENT_ID")
NEBULA_CLIENT_SECRET = os.getenv("NEBULA_CLIENT_SECRET")

ALERT_API_BASE = os.getenv("ALERT_API_BASE", "https://api.alertsystem.sit.ecvhrm.com")
ALERT_CLIENT_ID = os.getenv("ALERT_CLIENT_ID")
ALERT_CLIENT_SECRET = os.getenv("ALERT_CLIENT_SECRET")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "institution.dx@ecloudvalley.com")

NDA_INCOMPLETE_WHERE = """
    dri_mail IS NULL OR manager_mail IS NULL
    OR dri_name IS NULL OR dri_fullname IS NULL
    OR dri_deptno IS NULL OR dri_deptname IS NULL
    OR manager_name IS NULL OR manager_fullname IS NULL
    OR manager_deptno IS NULL OR manager_deptname IS NULL
    OR estimated_mandays IS NULL OR total_cost IS NULL
"""

INDUSTRY_ICON = {
    "Financial Services": "🏦",
    "Healthcare": "🩺",
    "Technology": "💻",
    "Professional Services": "📊",
    "Retail": "🛒",
    "Manufacturing": "⚙️",
    "Logistics": "🚚",
}
DEFAULT_ICON = "📁"


def bi(text_value):
    """把單語（AI 產出多為中文）字串包成前端既有的 {zh, en} 形狀，避免更動前端 render 邏輯。"""
    return {"zh": text_value, "en": text_value}


def derive_title(file_name: str) -> str:
    stem = Path(file_name).stem
    return stem.replace("_", " ").replace("-", " ").strip()


def derive_contact_item_name(file_name: str) -> str:
    """檔名前 12 碼是 jobcode，聯繫卡片只顯示 12 碼之後、去副檔名的檔名。"""
    remainder = file_name[12:].lstrip("_- ")
    stem = Path(remainder).stem
    return stem.replace("_", " ").replace("-", " ").strip()


def derive_description(customer_context: dict) -> str:
    challenge = (customer_context or {}).get("challenge", "")
    return challenge[:60] + ("…" if len(challenge) > 60 else "")


def fetch_skills(db: Session, sow_id: int) -> dict:
    rows = db.execute(
        text(
            """
            SELECT sl.category, sl.skill
            FROM sow_skill_relation r
            JOIN skill_list sl ON sl.id = r.skill_id
            WHERE r.sow_id = :sow_id
            ORDER BY sl.category, sl.skill
            """
        ),
        {"sow_id": sow_id},
    ).mappings().all()
    categories = []
    by_category: dict = {}
    for row in rows:
        if row["category"] not in categories:
            categories.append(row["category"])
        by_category.setdefault(row["category"], []).append(row["skill"])
    return {
        "skills": [row["skill"] for row in rows],
        "categories": categories,
        "by_category": by_category,
    }


def _api_request_json(method, url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_nebula_access_token():
    result = _api_request_json(
        "POST",
        f"{NEBULA_API_BASE}/auth/token",
        body={"client_id": NEBULA_CLIENT_ID, "client_secret": NEBULA_CLIENT_SECRET},
    )
    return result["access_token"]


def _fetch_jobcode_dri(token, job_code):
    query = urllib.parse.urlencode({"skipDri": "false", "top": 10, "includesLeave": "false"})
    url = f"{NEBULA_API_BASE}/api/v1/jobcode/{urllib.parse.quote(job_code)}/dri?{query}"
    result = _api_request_json("GET", url, headers={"Authorization": f"Bearer {token}"})
    return result["data"]


def _apply_nebula_dri_data(db: Session, job_code: str, data: dict) -> None:
    user_job_info = data.get("userJobInfo") or []
    dri_info = user_job_info[0] if len(user_job_info) > 0 else {}
    manager_info = user_job_info[1] if len(user_job_info) > 1 else {}
    db.execute(
        text(
            """
            UPDATE nda_work_station_apply
            SET estimated_mandays = :mandays,
                total_cost = :cost,
                dri_mail = :dri_mail,
                dri_deptno = :dri_deptno,
                dri_deptname = :dri_deptname,
                dri_name = :dri_name,
                dri_fullname = :dri_fullname,
                manager_mail = :manager_mail,
                manager_deptno = :manager_deptno,
                manager_deptname = :manager_deptname,
                manager_name = :manager_name,
                manager_fullname = :manager_fullname,
                updated_at = now()
            WHERE job_code = :job_code
            """
        ),
        {
            "mandays": data.get("estimatedMandays"),
            "cost": data.get("totalCost"),
            "dri_mail": dri_info.get("companyEmail"),
            "dri_deptno": dri_info.get("deptNo"),
            "dri_deptname": dri_info.get("deptName"),
            "dri_name": dri_info.get("userName"),
            "dri_fullname": dri_info.get("userFullName"),
            "manager_mail": manager_info.get("companyEmail"),
            "manager_deptno": manager_info.get("deptNo"),
            "manager_deptname": manager_info.get("deptName"),
            "manager_name": manager_info.get("userName"),
            "manager_fullname": manager_info.get("userFullName"),
            "job_code": job_code,
        },
    )
    db.commit()


def ensure_nda_enriched(db: Session, job_code: str) -> None:
    """開案件時檢查 nda_work_station_apply 這列是否還缺 DRI/主管/人天/成本欄位，缺的話當場呼叫
    Nebula API 回填。查無此 job_code（別系統還沒建列）或欄位已齊全就不用打 API；Nebula 認證沒設定
    或呼叫失敗都只記 log、不拋例外，沿用既有 fallback 邏輯（缺資料就退回 AI 萃取值），不能因為
    Nebula 打不通就讓案例頁跟著壞掉。"""
    if not job_code:
        return
    row = db.execute(
        text(f"SELECT 1 FROM nda_work_station_apply WHERE job_code = :job_code AND ({NDA_INCOMPLETE_WHERE})"),
        {"job_code": job_code},
    ).first()
    if not row:
        return
    if not NEBULA_CLIENT_ID or not NEBULA_CLIENT_SECRET:
        print(f"[nda-enrich] job_code={job_code} 略過：未設定 NEBULA_CLIENT_ID/NEBULA_CLIENT_SECRET")
        return
    try:
        token = _get_nebula_access_token()
        data = _fetch_jobcode_dri(token, job_code)
    except Exception as exc:  # noqa: BLE001 - Nebula 打不通不該讓案例頁跟著炸
        print(f"[nda-enrich] job_code={job_code} Nebula API 失敗，略過：{exc!r}")
        return
    if not data:
        return
    _apply_nebula_dri_data(db, job_code, data)


def fetch_nda_cost(db: Session, job_code: str):
    """依 sow_document.job_code 對照 nda_work_station_apply，取得 Nebula API 回填的權威人天／成本。"""
    if not job_code:
        return None
    return db.execute(
        text(
            "SELECT estimated_mandays, total_cost FROM nda_work_station_apply WHERE job_code = :job_code"
        ),
        {"job_code": job_code},
    ).mappings().first()


def fetch_nda_department(db: Session, job_code: str):
    """依 sow_document.job_code 對照 nda_work_station_apply，取得 DRI 部門名稱，供案例平台的 PM/SA 篩選使用。"""
    if not job_code:
        return None
    row = db.execute(
        text("SELECT dri_deptname FROM nda_work_station_apply WHERE job_code = :job_code"),
        {"job_code": job_code},
    ).mappings().first()
    return (row["dri_deptname"] if row else None) or None


def fetch_nda_contact_email(db: Session, job_code: str):
    """依 sow_document.job_code 對照 nda_work_station_apply.contact_id，取得負責人 email（contact 表）。"""
    if not job_code:
        return None
    row = db.execute(
        text(
            """
            SELECT c.email FROM nda_work_station_apply n
            JOIN contact c ON c.id = n.contact_id
            WHERE n.job_code = :job_code
            """
        ),
        {"job_code": job_code},
    ).mappings().first()
    return (row["email"] if row else None) or None


def _get_alert_access_token():
    result = _api_request_json(
        "POST",
        f"{ALERT_API_BASE}/auth/token",
        body={"client_id": ALERT_CLIENT_ID, "client_secret": ALERT_CLIENT_SECRET},
    )
    return result["access_token"]


def _send_alert_mail(to: list, subject: str, body: str) -> None:
    token = _get_alert_access_token()
    _api_request_json(
        "POST",
        f"{ALERT_API_BASE}/api/v1/alert/mail",
        headers={"Authorization": f"Bearer {token}"},
        body={
            "attachemntId": [],
            "alertLevel": "info",
            "to": to,
            "cc": [],
            "bcc": [],
            "subject": subject,
            "body": body,
            "reporter": "SOW Knowledge Base",
            "importance": "normal",
            "emailFrom": ALERT_EMAIL_FROM,
        },
    )


def notify_case_interest(db: Session, sow_id: int, customer_email: str, comment: str) -> None:
    """客戶送出「我有興趣」後盡力通知負責人；解析不到聯絡人、或 Alert API 失敗都只記 log、
    不拋例外——客戶的興趣登記已經存進資料庫，不能因為寄信失敗就讓整個請求變成 500。"""
    doc = db.execute(
        text("SELECT job_code, file_name FROM sow_document WHERE id = :id"), {"id": sow_id}
    ).mappings().first()
    if not doc:
        return
    to_email = fetch_nda_contact_email(db, doc.get("job_code"))
    if not to_email:
        print(f"[interest-mail] sow_id={sow_id} 找不到負責人 email（job_code={doc.get('job_code')}），略過寄信")
        return
    if not ALERT_CLIENT_ID or not ALERT_CLIENT_SECRET:
        print(f"[interest-mail] sow_id={sow_id} 略過：未設定 ALERT_CLIENT_ID/ALERT_CLIENT_SECRET")
        return
    try:
        title = derive_title(doc["file_name"])
        subject = f"【SOW 案例知識庫】有客戶對「{title}」表示興趣"
        body = f"客戶 email：{customer_email}<br>留言：{comment or '（無）'}<br><br>案例：{title}"
        _send_alert_mail([to_email], subject, body)
    except Exception as exc:  # noqa: BLE001 - 寄信失敗不能讓客戶的興趣登記跟著失敗
        print(f"[interest-mail] sow_id={sow_id} 寄信失敗，略過：{exc!r}")


def format_number(value) -> str:
    value = float(value)
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.1f}"


def fetch_structured_content(db: Session, sow_id: int, version: int = None):
    """version 省略時回傳最新版本（公開 API 用）；指定 version 時回傳該版本（審查 API 抓原始基準用）。"""
    if version is None:
        return db.execute(
            text(
                """
                SELECT version, customer_context, project_planning, technical_design
                FROM sow_structured_content
                WHERE sow_id = :sow_id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"sow_id": sow_id},
        ).mappings().first()
    return db.execute(
        text(
            """
            SELECT version, customer_context, project_planning, technical_design
            FROM sow_structured_content
            WHERE sow_id = :sow_id AND version = :version
            """
        ),
        {"sow_id": sow_id, "version": version},
    ).mappings().first()
