from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
REVIEW_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "review-frontend"

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


def derive_description(customer_context: dict) -> str:
    challenge = (customer_context or {}).get("challenge", "")
    return challenge[:60] + ("…" if len(challenge) > 60 else "")


def fetch_tags(db: Session, sow_id: int) -> dict:
    rows = db.execute(
        text(
            """
            SELECT t.tag_category, t.tag_name, t.category
            FROM sow_tag_relation r
            JOIN tag_definition t ON t.tag_id = r.tag_id
            WHERE r.sow_id = :sow_id AND t.is_active = true
            ORDER BY t.tag_category, t.tag_name
            """
        ),
        {"sow_id": sow_id},
    ).mappings().all()
    grouped = {"INDUSTRY": [], "SERVICE_DOMAIN": [], "USE_CASE": [], "TECH_PLATFORM": []}
    tech_categories = []
    for row in rows:
        grouped.setdefault(row["tag_category"], []).append(row["tag_name"])
        if row["tag_category"] == "TECH_PLATFORM" and row["category"] and row["category"] not in tech_categories:
            tech_categories.append(row["category"])
    grouped["TECH_PLATFORM_CATEGORY"] = tech_categories
    return grouped


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
