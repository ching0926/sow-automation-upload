"""
一次性腳本：建立審查流程所需的欄位與資料表，並把現有文件回填為 PUBLISHED。
可重複執行（ADD COLUMN / CREATE TABLE 都加了 IF NOT EXISTS）。
"""
from sqlalchemy import text

from db import SessionLocal


def main():
    db = SessionLocal()
    try:
        db.execute(text(
            "ALTER TABLE sow_document ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'DRI_REVIEW'"
        ))
        db.execute(text(
            "ALTER TABLE sow_document ADD COLUMN IF NOT EXISTS dri_submitted_at TIMESTAMP NULL"
        ))
        db.execute(text(
            "ALTER TABLE sow_document ADD COLUMN IF NOT EXISTS manager_reviewed_at TIMESTAMP NULL"
        ))

        # 回填：migration 當下既有的資料一律視為已發布
        # （剛剛 ADD COLUMN 給的預設值是 DRI_REVIEW，這裡收斂成 PUBLISHED，之後新進文件才維持 DRI_REVIEW 起點）
        db.execute(text(
            "UPDATE sow_document SET review_status = 'PUBLISHED' WHERE review_status = 'DRI_REVIEW'"
        ))

        db.execute(text(
            """
            CREATE TABLE IF NOT EXISTS sow_review_draft (
              id SERIAL PRIMARY KEY,
              sow_id INTEGER NOT NULL UNIQUE REFERENCES sow_document(id),
              customer_context JSONB NOT NULL DEFAULT '{}'::jsonb,
              project_planning JSONB NOT NULL DEFAULT '{}'::jsonb,
              technical_design  JSONB NOT NULL DEFAULT '{}'::jsonb,
              updated_at TIMESTAMP NOT NULL DEFAULT now(),
              updated_by TEXT
            )
            """
        ))
        db.execute(text(
            """
            CREATE TABLE IF NOT EXISTS sow_review_comment (
              id SERIAL PRIMARY KEY,
              sow_id INTEGER NOT NULL REFERENCES sow_document(id),
              author_role VARCHAR(20) NOT NULL CHECK (author_role IN ('DRI', 'MANAGER')),
              author_name TEXT,
              body TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_review_comment_sow_id ON sow_review_comment(sow_id)"
        ))
        db.commit()
        print("Migration applied.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
