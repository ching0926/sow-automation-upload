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
            SELECT t.category, t.tag_name
            FROM sow_tag_relation r
            JOIN tag_definition t ON t.id = r.tag_id
            WHERE r.sow_id = :sow_id AND t.is_active = true
            ORDER BY t.category, t.tag_name
            """
        ),
        {"sow_id": sow_id},
    ).mappings().all()
    grouped = {"INDUSTRY": [], "SERVICE_DOMAIN": [], "USE_CASE": [], "TECH_PLATFORM": []}
    for row in rows:
        grouped.setdefault(row["category"], []).append(row["tag_name"])
    return grouped


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
