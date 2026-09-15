import json
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from common import derive_title, fetch_structured_content, fetch_tags

router = APIRouter(prefix="/api/review")


# ---------- request bodies ----------

class KpiIn(BaseModel):
    icon: str = ""
    value: str = ""
    label: str = ""


class CustomerContextIn(BaseModel):
    industryBackground: str = ""
    challenge: str = ""
    solution: str = ""
    kpis: List[KpiIn] = []


class ProjectPlanningIn(BaseModel):
    owner: str = ""
    period: str = ""
    teamSize: Union[str, int] = ""
    manDays: Union[str, int] = ""
    totalCost: str = ""
    deliverables: List[str] = []


class TechnicalDesignIn(BaseModel):
    coreFunctions: List[str] = []
    architecture: List[str] = []
    techStack: List[str] = []


class DraftSaveIn(BaseModel):
    reviewerName: str
    customerContext: CustomerContextIn
    projectPlanning: ProjectPlanningIn
    technicalDesign: TechnicalDesignIn


class ReviewerIn(BaseModel):
    reviewerName: str


class ReturnIn(BaseModel):
    reviewerName: str
    comment: Optional[str] = None


class CommentIn(BaseModel):
    authorRole: Literal["DRI", "MANAGER"]
    authorName: str = ""
    body: str


# ---------- helpers ----------

def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def _field(original, current, saved_at):
    return {"original": original, "current": current, "savedAt": saved_at}


def _int_or_raw(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _to_snake_content(body: DraftSaveIn):
    cc, pp, td = body.customerContext, body.projectPlanning, body.technicalDesign
    customer_context = {
        "industry_background": cc.industryBackground,
        "challenge": cc.challenge,
        "solution": cc.solution,
        "kpis": [{"icon": k.icon, "value": k.value, "label": k.label} for k in cc.kpis],
    }
    project_planning = {
        "owner": pp.owner,
        "period": pp.period,
        "team_size": _int_or_raw(pp.teamSize),
        "man_days": _int_or_raw(pp.manDays),
        "total_cost": pp.totalCost,
        "deliverables": pp.deliverables,
    }
    technical_design = {
        "core_functions": td.coreFunctions,
        "architecture_nodes": td.architecture,
        "tech_stack": td.techStack,
    }
    return customer_context, project_planning, technical_design


def _fetch_doc_status(db: Session, sow_id: int):
    return db.execute(
        text("SELECT review_status FROM sow_document WHERE id = :id"), {"id": sow_id}
    ).mappings().first()


def _ensure_draft(db: Session, sow_id: int):
    """DRI 第一次打開審查頁、或暫存曾被清掉時，從 version=1 的原始萃取內容建立暫存基準。"""
    db.execute(
        text(
            """
            INSERT INTO sow_review_draft (sow_id, customer_context, project_planning, technical_design)
            SELECT :sow_id, customer_context, project_planning, technical_design
            FROM sow_structured_content
            WHERE sow_id = :sow_id AND version = 1
            ON CONFLICT (sow_id) DO NOTHING
            """
        ),
        {"sow_id": sow_id},
    )


def build_review_case(db: Session, sow_id: int):
    doc = db.execute(
        text(
            """
            SELECT id, file_name, review_status, dri_submitted_at, manager_reviewed_at, created_at
            FROM sow_document WHERE id = :id
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    if not doc:
        return None

    _ensure_draft(db, sow_id)
    db.commit()

    original_row = fetch_structured_content(db, sow_id, version=1)
    draft_row = db.execute(
        text(
            """
            SELECT customer_context, project_planning, technical_design, updated_at
            FROM sow_review_draft WHERE sow_id = :id
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    comment_rows = db.execute(
        text(
            """
            SELECT author_role, author_name, body, created_at
            FROM sow_review_comment WHERE sow_id = :id ORDER BY created_at ASC
            """
        ),
        {"id": sow_id},
    ).mappings().all()
    tags = fetch_tags(db, sow_id)

    cc_o = (original_row or {}).get("customer_context") or {}
    pp_o = (original_row or {}).get("project_planning") or {}
    td_o = (original_row or {}).get("technical_design") or {}
    cc_c = (draft_row or {}).get("customer_context") or cc_o
    pp_c = (draft_row or {}).get("project_planning") or pp_o
    td_c = (draft_row or {}).get("technical_design") or td_o
    saved_at = _fmt(draft_row["updated_at"]) if draft_row else None

    kpis_current = cc_c.get("kpis") or []
    kpis_original = cc_o.get("kpis") or []
    kpis = []
    for i, kpi_c in enumerate(kpis_current):
        kpi_o = kpis_original[i] if i < len(kpis_original) else {}
        kpis.append(
            {
                "icon": kpi_c.get("icon", ""),
                "value": _field(kpi_o.get("value", ""), kpi_c.get("value", ""), saved_at),
                "label": _field(kpi_o.get("label", ""), kpi_c.get("label", ""), saved_at),
                "savedAt": saved_at,
            }
        )

    industry = tags["INDUSTRY"][0] if tags["INDUSTRY"] else "Unknown"

    return {
        "sowId": doc["id"],
        "title": derive_title(doc["file_name"]),
        "industry": industry,
        "uploadedAt": doc["created_at"].date().isoformat() if doc["created_at"] else "",
        "driSubmittedAt": _fmt(doc["dri_submitted_at"]),
        "managerReviewedAt": _fmt(doc["manager_reviewed_at"]),
        "status": doc["review_status"],
        "detail": {
            "A": {
                "industryBackground": _field(cc_o.get("industry_background", ""), cc_c.get("industry_background", ""), saved_at),
                "challenge": _field(cc_o.get("challenge", ""), cc_c.get("challenge", ""), saved_at),
                "solution": _field(cc_o.get("solution", ""), cc_c.get("solution", ""), saved_at),
                "kpis": kpis,
            },
            "B": {
                "owner": _field(pp_o.get("owner", ""), pp_c.get("owner", ""), saved_at),
                "period": _field(pp_o.get("period", ""), pp_c.get("period", ""), saved_at),
                "teamSize": _field(pp_o.get("team_size", 0), pp_c.get("team_size", 0), saved_at),
                "manDays": _field(pp_o.get("man_days", 0), pp_c.get("man_days", 0), saved_at),
                "totalCost": _field(pp_o.get("total_cost", ""), pp_c.get("total_cost", ""), saved_at),
                "deliverables": _field(pp_o.get("deliverables", []), pp_c.get("deliverables", []), saved_at),
            },
            "C": {
                "coreFunctions": _field(td_o.get("core_functions", []), td_c.get("core_functions", []), saved_at),
                "architecture": _field(td_o.get("architecture_nodes", []), td_c.get("architecture_nodes", []), saved_at),
                "techStack": _field(td_o.get("tech_stack", []), td_c.get("tech_stack", []), saved_at),
            },
        },
        "comments": [
            {
                "authorRole": r["author_role"],
                "authorName": r["author_name"] or "",
                "body": r["body"],
                "createdAt": _fmt(r["created_at"]),
            }
            for r in comment_rows
        ],
    }


# ---------- routes ----------

@router.get("/cases/{sow_id}")
def get_review_case(sow_id: int, db: Session = Depends(get_db)):
    case = build_review_case(db, sow_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.put("/cases/{sow_id}/draft")
def save_draft(sow_id: int, body: DraftSaveIn, db: Session = Depends(get_db)):
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    if doc["review_status"] not in ("DRI_REVIEW", "RETURNED_TO_DRI"):
        raise HTTPException(status_code=409, detail="Case is not editable in its current status")

    _ensure_draft(db, sow_id)
    customer_context, project_planning, technical_design = _to_snake_content(body)
    db.execute(
        text(
            """
            UPDATE sow_review_draft
            SET customer_context = CAST(:cc AS JSONB),
                project_planning = CAST(:pp AS JSONB),
                technical_design = CAST(:td AS JSONB),
                updated_at = now(),
                updated_by = :reviewer
            WHERE sow_id = :sow_id
            """
        ),
        {
            "sow_id": sow_id,
            "cc": json.dumps(customer_context, ensure_ascii=False),
            "pp": json.dumps(project_planning, ensure_ascii=False),
            "td": json.dumps(technical_design, ensure_ascii=False),
            "reviewer": body.reviewerName,
        },
    )
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{sow_id}/submit")
def submit_for_review(sow_id: int, body: ReviewerIn, db: Session = Depends(get_db)):
    result = db.execute(
        text(
            """
            UPDATE sow_document
            SET review_status = 'MANAGER_REVIEW', dri_submitted_at = now(), edited_by = :reviewer
            WHERE id = :id AND review_status IN ('DRI_REVIEW', 'RETURNED_TO_DRI')
            """
        ),
        {"id": sow_id, "reviewer": body.reviewerName},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case is not awaiting DRI submission")
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{sow_id}/comments")
def add_comment(sow_id: int, body: CommentIn, db: Session = Depends(get_db)):
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    db.execute(
        text(
            """
            INSERT INTO sow_review_comment (sow_id, author_role, author_name, body)
            VALUES (:sow_id, :role, :name, :body)
            """
        ),
        {"sow_id": sow_id, "role": body.authorRole, "name": body.authorName, "body": body.body},
    )
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{sow_id}/return")
def return_to_dri(sow_id: int, body: ReturnIn, db: Session = Depends(get_db)):
    if body.comment:
        db.execute(
            text(
                """
                INSERT INTO sow_review_comment (sow_id, author_role, author_name, body)
                VALUES (:sow_id, 'MANAGER', :name, :body)
                """
            ),
            {"sow_id": sow_id, "name": body.reviewerName, "body": body.comment},
        )
    result = db.execute(
        text(
            """
            UPDATE sow_document
            SET review_status = 'RETURNED_TO_DRI', manager_reviewed_at = now(), approved_by = :reviewer
            WHERE id = :id AND review_status = 'MANAGER_REVIEW'
            """
        ),
        {"id": sow_id, "reviewer": body.reviewerName},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case is not awaiting manager review")
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{sow_id}/approve")
def approve_and_publish(sow_id: int, body: ReviewerIn, db: Session = Depends(get_db)):
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    if doc["review_status"] != "MANAGER_REVIEW":
        raise HTTPException(status_code=409, detail="Case is not awaiting manager review")

    next_version = db.execute(
        text("SELECT COALESCE(MAX(version), 0) + 1 FROM sow_structured_content WHERE sow_id = :id"),
        {"id": sow_id},
    ).scalar()

    result = db.execute(
        text(
            """
            INSERT INTO sow_structured_content (sow_id, version, customer_context, project_planning, technical_design)
            SELECT sow_id, :next_version, customer_context, project_planning, technical_design
            FROM sow_review_draft WHERE sow_id = :id
            """
        ),
        {"id": sow_id, "next_version": next_version},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="No draft content to publish")

    db.execute(
        text(
            """
            UPDATE sow_document
            SET review_status = 'PUBLISHED', manager_reviewed_at = now(), approved_by = :reviewer
            WHERE id = :id AND review_status = 'MANAGER_REVIEW'
            """
        ),
        {"id": sow_id, "reviewer": body.reviewerName},
    )
    db.commit()
    return build_review_case(db, sow_id)
