from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from common import (
    DEFAULT_ICON,
    FRONTEND_DIR,
    INDUSTRY_ICON,
    REVIEW_FRONTEND_DIR,
    bi,
    derive_description,
    derive_title,
    fetch_structured_content,
    fetch_tags,
)
from review import router as review_router

app = FastAPI(title="SOW Knowledge Base API")


def build_case(db: Session, doc: dict) -> dict:
    tags = fetch_tags(db, doc["id"])
    content_row = fetch_structured_content(db, doc["id"])
    customer_context = (content_row or {}).get("customer_context") or {}
    project_planning = (content_row or {}).get("project_planning") or {}
    technical_design = (content_row or {}).get("technical_design") or {}

    industry = tags["INDUSTRY"][0] if tags["INDUSTRY"] else "Unknown"

    kpis = [
        {
            "icon": kpi.get("icon", ""),
            "value": kpi.get("value", ""),
            "label": bi(kpi.get("label", "")),
        }
        for kpi in customer_context.get("kpis", [])
    ]

    return {
        "id": doc["id"],
        "industry": industry,
        "icon": INDUSTRY_ICON.get(industry, DEFAULT_ICON),
        "title": bi(derive_title(doc["file_name"])),
        "description": bi(derive_description(customer_context)),
        "serviceCategory": tags["SERVICE_DOMAIN"],
        "useCase": tags["USE_CASE"],
        "skills": tags["TECH_PLATFORM"],
        "date": doc["created_at"].date().isoformat() if doc["created_at"] else "",
        "creator": doc["edited_by"] or doc["approved_by"] or "—",
        "detail": {
            "A": {
                "industryBackground": bi(customer_context.get("industry_background", "")),
                "challenge": bi(customer_context.get("challenge", "")),
                "solution": bi(customer_context.get("solution", "")),
                "kpis": kpis,
            },
            "B": {
                "owner": project_planning.get("owner", ""),
                "period": project_planning.get("period", ""),
                "teamSize": project_planning.get("team_size", 0),
                "team": [],
                "cost": {
                    "manDays": project_planning.get("man_days", 0),
                    "total": project_planning.get("total_cost", ""),
                },
                "wbs": [],
                "deliverables": project_planning.get("deliverables", []),
            },
            "C": {
                "coreFunctions": technical_design.get("core_functions", []),
                "architecture": technical_design.get("architecture_nodes", []),
                "techStack": technical_design.get("tech_stack", []),
            },
        },
    }


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)):
    docs = db.execute(
        text(
            """
            SELECT id, file_name, edited_by, approved_by, created_at
            FROM sow_document
            WHERE is_latest = true AND review_status = 'PUBLISHED'
            ORDER BY created_at DESC
            """
        )
    ).mappings().all()
    return [build_case(db, doc) for doc in docs]


@app.get("/api/cases/{sow_id}")
def get_case(sow_id: int, db: Session = Depends(get_db)):
    doc = db.execute(
        text(
            """
            SELECT id, file_name, edited_by, approved_by, created_at
            FROM sow_document
            WHERE id = :id AND review_status = 'PUBLISHED'
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_case(db, doc)


app.include_router(review_router)
app.mount("/review", StaticFiles(directory=str(REVIEW_FRONTEND_DIR), html=True), name="review-frontend")
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
