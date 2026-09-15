"""
一次性腳本：在 sow_document 新增 job_code 欄位，用來對照 nda_work_station_apply.job_code，
讓「專案規劃與交付」的人天／成本改用 nda_work_station_apply 的權威資料（Nebula API 回填），
找不到對應 job_code 或該筆資料還沒有人天／成本時，仍 fallback 回
sow_structured_content.project_planning 的 AI 萃取值。可重複執行。
"""
from sqlalchemy import text

from db import SessionLocal


def main():
    db = SessionLocal()
    try:
        db.execute(text(
            "ALTER TABLE sow_document ADD COLUMN IF NOT EXISTS job_code VARCHAR(100) NULL"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sow_document_job_code ON sow_document(job_code)"
        ))
        db.commit()
        print("Migration applied.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
