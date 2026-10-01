import json
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db
from common import (
    derive_title,
    ensure_nda_enriched,
    fetch_nda_cost,
    fetch_nda_department,
    fetch_structured_content,
    format_number,
)

router = APIRouter(prefix="/api/review")


# ---------- request bodies ----------

class KpiIn(BaseModel):
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
    teamSize: Optional[Union[str, int]] = None
    manDays: Union[str, int] = ""
    totalCost: str = ""
    deliverables: List[str] = []


class SystemModuleIn(BaseModel):
    moduleName: str = ""
    responsibility: str = ""


class UnderlyingArchitectureIn(BaseModel):
    summary: str = ""
    dataFlow: str = ""
    deploymentEnvironment: str = ""


class TechnicalDesignIn(BaseModel):
    coreFunctions: List[str] = []
    systemModules: List[SystemModuleIn] = []
    underlyingArchitecture: UnderlyingArchitectureIn = UnderlyingArchitectureIn()


class DraftSaveIn(BaseModel):
    customerContext: CustomerContextIn
    projectPlanning: ProjectPlanningIn
    technicalDesign: TechnicalDesignIn


class ReturnIn(BaseModel):
    comment: Optional[str] = None


class CommentIn(BaseModel):
    authorRole: Literal["DRI", "MANAGER"]
    body: str
    sectionKey: Optional[str] = None


class CommentUpdateIn(BaseModel):
    authorRole: Literal["DRI", "MANAGER"]
    body: str


class CommentDeleteIn(BaseModel):
    authorRole: Literal["DRI", "MANAGER"]


# ---------- helpers ----------

def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def _field(original, current, saved_at):
    return {"original": original, "current": current, "savedAt": saved_at}


def _modules_camel(modules):
    return [
        {"moduleName": m.get("module_name", ""), "responsibility": m.get("responsibility", "")}
        for m in (modules or [])
    ]


def _architecture_camel(architecture):
    architecture = architecture or {}
    return {
        "summary": architecture.get("summary", ""),
        "dataFlow": architecture.get("data_flow", ""),
        "deploymentEnvironment": architecture.get("deployment_environment", ""),
    }


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
        "kpis": [{"value": k.value, "label": k.label} for k in cc.kpis],
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
        "system_modules": [
            {"module_name": m.moduleName, "responsibility": m.responsibility} for m in td.systemModules
        ],
        "underlying_architecture": {
            "summary": td.underlyingArchitecture.summary,
            "data_flow": td.underlyingArchitecture.dataFlow,
            "deployment_environment": td.underlyingArchitecture.deploymentEnvironment,
        },
    }
    return customer_context, project_planning, technical_design


def _resolve_sow_id(db: Session, token: str) -> int:
    """把審核連結網址上的 token（HMAC-SHA256(REVIEW_LINK_SECRET, job_code)）解析成內部
    sow_document.id；查不到就 404。網址上不再直接暴露 job_code。"""
    row = db.execute(
        text(
            "SELECT id FROM sow_document WHERE review_token = :token AND is_latest = true ORDER BY id DESC LIMIT 1"
        ),
        {"token": token},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row["id"]


def _fetch_doc_status(db: Session, sow_id: int):
    return db.execute(
        text("SELECT dri_status, manager_status FROM sow_document WHERE id = :id"), {"id": sow_id}
    ).mappings().first()


def _derive_status(dri_status: str, manager_status: str) -> str:
    """把 dri_status/manager_status 組合推導回原本 review_status 的 4 種字串，維持 API 對外的 status 欄位不變。"""
    if dri_status == "approve" and manager_status == "approve":
        return "PUBLISHED"
    if dri_status == "approve" and manager_status == "waiting":
        return "MANAGER_REVIEW"
    if dri_status == "waiting" and manager_status == "reject":
        return "RETURNED_TO_DRI"
    return "DRI_REVIEW"


def _resolve_reviewer_email(db: Session, sow_id: int, role: str) -> str:
    """依 sow_document.job_code 查 nda_work_station_apply 的 dri_mail/manager_mail email，取代原本手動輸入的姓名。"""
    doc = db.execute(
        text("SELECT job_code FROM sow_document WHERE id = :id"), {"id": sow_id}
    ).mappings().first()
    job_code = doc["job_code"] if doc else None
    if not job_code:
        return ""
    column = "dri_mail" if role == "DRI" else "manager_mail"
    row = db.execute(
        text(f"SELECT {column} FROM nda_work_station_apply WHERE job_code = :jc"), {"jc": job_code}
    ).mappings().first()
    return (row[column] if row else None) or ""


def _ensure_draft(db: Session, sow_id: int, nda_man_days=None, nda_total_cost=None, nda_owner=None):
    """DRI 第一次打開審查頁時，從 version=1 的原始萃取內容建立暫存的第一版（version=1）。
    若當下 job_code 已經有 NDA 工作站的權威資料（人天/成本/DRI 部門），第一版直接用 NDA 值
    取代 AI 猜測值作為起始值；這幾個欄位之後就是一般可編輯欄位，DRI/主管都能再自行調整並存檔。"""
    result = db.execute(
        text(
            """
            INSERT INTO sow_review_draft (sow_id, version, customer_context, project_planning, technical_design)
            SELECT :sow_id, 1, customer_context, project_planning, technical_design
            FROM sow_structured_content
            WHERE sow_id = :sow_id AND version = 1
            ON CONFLICT (sow_id, version) DO NOTHING
            RETURNING sow_id
            """
        ),
        {"sow_id": sow_id},
    )
    inserted = result.first() is not None
    if inserted and (nda_man_days is not None or nda_total_cost is not None or nda_owner is not None):
        db.execute(
            text(
                """
                UPDATE sow_review_draft
                SET project_planning = project_planning
                    || CASE WHEN :man_days IS NOT NULL THEN jsonb_build_object('man_days', CAST(:man_days AS text)) ELSE '{}'::jsonb END
                    || CASE WHEN :total_cost IS NOT NULL THEN jsonb_build_object('total_cost', CAST(:total_cost AS text)) ELSE '{}'::jsonb END
                    || CASE WHEN :owner IS NOT NULL THEN jsonb_build_object('owner', CAST(:owner AS text)) ELSE '{}'::jsonb END
                WHERE sow_id = :sow_id AND version = 1
                """
            ),
            {"sow_id": sow_id, "man_days": nda_man_days, "total_cost": nda_total_cost, "owner": nda_owner},
        )


def build_review_case(db: Session, sow_id: int):
    doc = db.execute(
        text(
            """
            SELECT id, file_name, dri_status, manager_status, dri_submitted_at, manager_reviewed_at, created_at, job_code, industry
            FROM sow_document WHERE id = :id
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    if not doc:
        return None

    ensure_nda_enriched(db, doc.get("job_code"))
    nda_department = fetch_nda_department(db, doc.get("job_code"))
    nda_cost = fetch_nda_cost(db, doc.get("job_code"))
    nda_available = bool(
        nda_cost and nda_cost["estimated_mandays"] is not None and nda_cost["total_cost"] is not None
    )
    _ensure_draft(
        db,
        sow_id,
        nda_man_days=format_number(nda_cost["estimated_mandays"]) if nda_available else None,
        nda_total_cost=format_number(nda_cost["total_cost"]) if nda_available else None,
        nda_owner=nda_department,
    )
    db.commit()

    original_row = fetch_structured_content(db, sow_id, version=1)
    draft_row = db.execute(
        text(
            """
            SELECT customer_context, project_planning, technical_design, updated_at
            FROM sow_review_draft WHERE sow_id = :id
            ORDER BY version DESC LIMIT 1
            """
        ),
        {"id": sow_id},
    ).mappings().first()
    comment_rows = db.execute(
        text(
            """
            SELECT id, author_role, author_name, body, section_key, created_at, updated_at
            FROM sow_review_comment WHERE sow_id = :id ORDER BY created_at ASC
            """
        ),
        {"id": sow_id},
    ).mappings().all()
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
                "value": _field(kpi_o.get("value", ""), kpi_c.get("value", ""), saved_at),
                "label": _field(kpi_o.get("label", ""), kpi_c.get("label", ""), saved_at),
                "savedAt": saved_at,
            }
        )

    industry = doc["industry"] or "Unknown"

    # owner（DRI 部門）跟 man_days/total_cost 一樣：有 NDA 權威資料就拿來當「起始基準」
    # （原本 AI 猜的值就不用了），但不鎖住——DRI/主管在審查時都可以再自行調整，調整後
    # 存進 sow_review_draft，跟其他一般欄位（period、teamSize…）走同一套編輯/存檔流程，
    # 所以這裡不設 "source" 鎖定標記。
    owner_baseline = nda_department or pp_o.get("owner", "")
    owner_field = _field(owner_baseline, pp_c.get("owner", owner_baseline), saved_at)
    if nda_available:
        man_days_baseline = format_number(nda_cost["estimated_mandays"])
        total_cost_baseline = format_number(nda_cost["total_cost"])
    else:
        man_days_baseline = pp_o.get("man_days", 0)
        total_cost_baseline = pp_o.get("total_cost", "")
    man_days_field = _field(man_days_baseline, pp_c.get("man_days", man_days_baseline), saved_at)
    total_cost_field = _field(total_cost_baseline, pp_c.get("total_cost", total_cost_baseline), saved_at)

    return {
        "sowId": doc["id"],
        "title": derive_title(doc["file_name"]),
        "industry": industry,
        "uploadedAt": doc["created_at"].date().isoformat() if doc["created_at"] else "",
        "driSubmittedAt": _fmt(doc["dri_submitted_at"]),
        "managerReviewedAt": _fmt(doc["manager_reviewed_at"]),
        "status": _derive_status(doc["dri_status"], doc["manager_status"]),
        "detail": {
            "A": {
                "industryBackground": _field(cc_o.get("industry_background", ""), cc_c.get("industry_background", ""), saved_at),
                "challenge": _field(cc_o.get("challenge", ""), cc_c.get("challenge", ""), saved_at),
                "solution": _field(cc_o.get("solution", ""), cc_c.get("solution", ""), saved_at),
                "kpis": kpis,
            },
            "B": {
                "owner": owner_field,
                "period": _field(pp_o.get("period", ""), pp_c.get("period", ""), saved_at),
                "teamSize": _field(pp_o.get("team_size"), pp_c.get("team_size"), saved_at),
                "manDays": man_days_field,
                "totalCost": total_cost_field,
                "deliverables": _field(pp_o.get("deliverables", []), pp_c.get("deliverables", []), saved_at),
            },
            "C": {
                "coreFunctions": _field(td_o.get("core_functions", []), td_c.get("core_functions", []), saved_at),
                "systemModules": _field(
                    _modules_camel(td_o.get("system_modules", [])),
                    _modules_camel(td_c.get("system_modules", [])),
                    saved_at,
                ),
                "underlyingArchitecture": _field(
                    _architecture_camel(td_o.get("underlying_architecture", {})),
                    _architecture_camel(td_c.get("underlying_architecture", {})),
                    saved_at,
                ),
            },
        },
        "comments": [
            {
                "id": r["id"],
                "sectionKey": r["section_key"],
                "authorRole": r["author_role"],
                "authorName": r["author_name"] or "",
                "body": r["body"],
                "createdAt": _fmt(r["created_at"]),
                "updatedAt": _fmt(r["updated_at"]),
            }
            for r in comment_rows
        ],
    }


# ---------- routes ----------

@router.get("/cases/{token}")
def get_review_case(token: str, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    case = build_review_case(db, sow_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.put("/cases/{token}/draft")
def save_draft(token: str, body: DraftSaveIn, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    if doc["dri_status"] != "waiting":
        raise HTTPException(status_code=409, detail="Case is not editable in its current status")

    _ensure_draft(db, sow_id)
    customer_context, project_planning, technical_design = _to_snake_content(body)
    reviewer = _resolve_reviewer_email(db, sow_id, "DRI")
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
              AND version = (SELECT MAX(version) FROM sow_review_draft WHERE sow_id = :sow_id)
            """
        ),
        {
            "sow_id": sow_id,
            "cc": json.dumps(customer_context, ensure_ascii=False),
            "pp": json.dumps(project_planning, ensure_ascii=False),
            "td": json.dumps(technical_design, ensure_ascii=False),
            "reviewer": reviewer,
        },
    )
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{token}/submit")
def submit_for_review(token: str, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    reviewer = _resolve_reviewer_email(db, sow_id, "DRI")
    result = db.execute(
        text(
            """
            UPDATE sow_document
            SET dri_status = 'approve', manager_status = 'waiting', dri_submitted_at = now(), edited_by = :reviewer
            WHERE id = :id AND dri_status = 'waiting'
            """
        ),
        {"id": sow_id, "reviewer": reviewer},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case is not awaiting DRI submission")
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{token}/comments")
def add_comment(token: str, body: CommentIn, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")

    text_body = body.body.strip()
    if not text_body:
        raise HTTPException(status_code=422, detail="留言內容不可為空")
    if len(text_body) > 300:
        raise HTTPException(status_code=422, detail="留言內容超過 300 字上限")
    if body.sectionKey and len(body.sectionKey) > 100:
        raise HTTPException(status_code=422, detail="sectionKey 過長")

    if body.sectionKey:
        existing = db.execute(
            text(
                """
                SELECT id FROM sow_review_comment
                WHERE sow_id = :sow_id AND author_role = :role AND section_key = :section_key
                """
            ),
            {"sow_id": sow_id, "role": body.authorRole, "section_key": body.sectionKey},
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="您已在此欄位留言，請編輯現有留言")

    author_name = _resolve_reviewer_email(db, sow_id, body.authorRole)
    try:
        db.execute(
            text(
                """
                INSERT INTO sow_review_comment (sow_id, author_role, author_name, body, section_key)
                VALUES (:sow_id, :role, :name, :body, :section_key)
                """
            ),
            {
                "sow_id": sow_id,
                "role": body.authorRole,
                "name": author_name,
                "body": text_body,
                "section_key": body.sectionKey,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="您已在此欄位留言，請編輯現有留言")
    return build_review_case(db, sow_id)


@router.put("/cases/{token}/comments/{comment_id}")
def update_comment(token: str, comment_id: int, body: CommentUpdateIn, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    text_body = body.body.strip()
    if not text_body:
        raise HTTPException(status_code=422, detail="留言內容不可為空")
    if len(text_body) > 300:
        raise HTTPException(status_code=422, detail="留言內容超過 300 字上限")

    row = db.execute(
        text("SELECT id, author_role FROM sow_review_comment WHERE id = :id AND sow_id = :sow_id"),
        {"id": comment_id, "sow_id": sow_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    if row["author_role"] != body.authorRole:
        raise HTTPException(status_code=403, detail="無法編輯其他角色的留言")

    db.execute(
        text("UPDATE sow_review_comment SET body = :body, updated_at = now() WHERE id = :id"),
        {"id": comment_id, "body": text_body},
    )
    db.commit()
    return build_review_case(db, sow_id)


@router.delete("/cases/{token}/comments/{comment_id}")
def delete_comment(token: str, comment_id: int, body: CommentDeleteIn, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    row = db.execute(
        text("SELECT id, author_role FROM sow_review_comment WHERE id = :id AND sow_id = :sow_id"),
        {"id": comment_id, "sow_id": sow_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    if row["author_role"] != body.authorRole:
        raise HTTPException(status_code=403, detail="無法刪除其他角色的留言")

    db.execute(text("DELETE FROM sow_review_comment WHERE id = :id"), {"id": comment_id})
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{token}/return")
def return_to_dri(token: str, body: ReturnIn, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    reviewer = _resolve_reviewer_email(db, sow_id, "MANAGER")
    if body.comment:
        db.execute(
            text(
                """
                INSERT INTO sow_review_comment (sow_id, author_role, author_name, body)
                VALUES (:sow_id, 'MANAGER', :name, :body)
                """
            ),
            {"sow_id": sow_id, "name": reviewer, "body": body.comment},
        )
    result = db.execute(
        text(
            """
            UPDATE sow_document
            SET dri_status = 'waiting', manager_status = 'reject', manager_reviewed_at = now(), approved_by = :reviewer
            WHERE id = :id AND dri_status = 'approve' AND manager_status = 'waiting'
            """
        ),
        {"id": sow_id, "reviewer": reviewer},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case is not awaiting manager review")

    db.execute(
        text(
            """
            INSERT INTO sow_review_draft (sow_id, version, customer_context, project_planning, technical_design)
            SELECT sow_id, version + 1, customer_context, project_planning, technical_design
            FROM sow_review_draft
            WHERE sow_id = :id AND version = (SELECT MAX(version) FROM sow_review_draft WHERE sow_id = :id)
            """
        ),
        {"id": sow_id},
    )
    db.commit()
    return build_review_case(db, sow_id)


@router.post("/cases/{token}/approve")
def approve_and_publish(token: str, db: Session = Depends(get_db)):
    sow_id = _resolve_sow_id(db, token)
    doc = _fetch_doc_status(db, sow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Case not found")
    if not (doc["dri_status"] == "approve" and doc["manager_status"] == "waiting"):
        raise HTTPException(status_code=409, detail="Case is not awaiting manager review")
    reviewer = _resolve_reviewer_email(db, sow_id, "MANAGER")

    next_version = db.execute(
        text("SELECT COALESCE(MAX(version), 0) + 1 FROM sow_structured_content WHERE sow_id = :id"),
        {"id": sow_id},
    ).scalar()

    result = db.execute(
        text(
            """
            INSERT INTO sow_structured_content (sow_id, version, customer_context, project_planning, technical_design)
            SELECT sow_id, :next_version, customer_context, project_planning, technical_design
            FROM sow_review_draft
            WHERE sow_id = :id AND version = (SELECT MAX(version) FROM sow_review_draft WHERE sow_id = :id)
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
            SET manager_status = 'approve', manager_reviewed_at = now(), approved_by = :reviewer
            WHERE id = :id AND dri_status = 'approve' AND manager_status = 'waiting'
            """
        ),
        {"id": sow_id, "reviewer": reviewer},
    )
    db.commit()
    return build_review_case(db, sow_id)
