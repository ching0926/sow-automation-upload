import os
import re

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from mangum import Mangum

from db import get_db
from common import (
    DEFAULT_ICON,
    FRONTEND_DIR,
    INDUSTRY_ICON,
    REVIEW_FRONTEND_DIR,
    bi,
    derive_contact_item_name,
    derive_description,
    derive_title,
    fetch_nda_cost,
    fetch_nda_department,
    fetch_structured_content,
    fetch_tags,
    format_number,
)
from review import router as review_router

app = FastAPI(title="SOW Knowledge Base API")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InterestRequest(BaseModel):
    email: str
    message: str | None = None


def build_case(db: Session, doc: dict) -> dict:
    tags = fetch_tags(db, doc["id"])
    content_row = fetch_structured_content(db, doc["id"])
    customer_context = (content_row or {}).get("customer_context") or {}
    project_planning = (content_row or {}).get("project_planning") or {}
    technical_design = (content_row or {}).get("technical_design") or {}

    industry = tags["INDUSTRY"][0] if tags["INDUSTRY"] else "Unknown"

    nda_cost = fetch_nda_cost(db, doc.get("job_code"))
    man_days = (
        format_number(nda_cost["estimated_mandays"])
        if nda_cost and nda_cost["estimated_mandays"] is not None
        else project_planning.get("man_days", 0)
    )
    total_cost = (
        format_number(nda_cost["total_cost"])
        if nda_cost and nda_cost["total_cost"] is not None
        else project_planning.get("total_cost", "")
    )

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
        "contactItemName": derive_contact_item_name(doc["file_name"]),
        "serviceCategory": tags["SERVICE_DOMAIN"],
        "useCase": tags["USE_CASE"],
        "skills": tags["TECH_PLATFORM"],
        "techCategory": tags["TECH_PLATFORM_CATEGORY"],
        "driDepartment": fetch_nda_department(db, doc.get("job_code")),
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
                    "manDays": man_days,
                    "total": total_cost,
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
            SELECT id, file_name, edited_by, approved_by, created_at, job_code
            FROM sow_document
            WHERE is_latest = true AND dri_status = 'approve' AND manager_status = 'approve'
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
            SELECT id, file_name, edited_by, approved_by, created_at, job_code
            FROM sow_document
            WHERE id = :id AND dri_status = 'approve' AND manager_status = 'approve'
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_case(db, doc)


@app.post("/api/cases/{sow_id}/interest")
def submit_interest(sow_id: int, body: InterestRequest, db: Session = Depends(get_db)):
    if not body.email or not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(status_code=422, detail="Invalid email")
    exists = db.execute(text("SELECT 1 FROM sow_document WHERE id = :id"), {"id": sow_id}).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Case not found")
    customer_id = db.execute(
        text("INSERT INTO customer (email, comment) VALUES (:email, :comment) RETURNING id"),
        {"email": body.email.strip(), "comment": (body.message or "").strip() or None},
    ).scalar()
    db.execute(
        text("INSERT INTO sow_customer_interest (customer_id, sow_id) VALUES (:cid, :sid)"),
        {"cid": customer_id, "sid": sow_id},
    )
    db.commit()
    return {"ok": True}


@app.get("/api/skill-taxonomy")
def get_skill_taxonomy(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
            SELECT DISTINCT category, skill_name FROM tag_definition
            WHERE tag_category = 'TECH_PLATFORM' AND category IS NOT NULL AND skill_name IS NOT NULL
              AND is_active = true
            ORDER BY category, skill_name
            """
        )
    ).mappings().all()
    taxonomy: dict = {}
    for row in rows:
        taxonomy.setdefault(row["category"], []).append(row["skill_name"])
    return taxonomy


NDA_API_KEY = os.getenv("NDA_API_KEY")


def verify_nda_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    if not NDA_API_KEY or x_api_key != NDA_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/api/jobcode/{job_code}/nda-check")
def get_nda_check(job_code: str, db: Session = Depends(get_db), _: None = Depends(verify_nda_api_key)):
    row = db.execute(
        text("SELECT nda_check FROM nda_work_station_apply WHERE job_code = :job_code"),
        {"job_code": job_code},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="job_code not found")
    return {"jobCode": job_code, "ndaCheck": row["nda_check"]}


app.include_router(review_router)
app.mount("/review", StaticFiles(directory=str(REVIEW_FRONTEND_DIR), html=True), name="review-frontend")
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

handler = Mangum(app)