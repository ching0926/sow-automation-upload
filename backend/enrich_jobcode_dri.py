"""
批次腳本：對 nda_work_station_apply 裡還缺 dri_mail/manager_mail/estimated_mandays/total_cost
（或其他明細欄位）的 job_code，呼叫 Nebula API 查詢後回填。可重複執行——只處理欄位還是 NULL 的資料列。

實際的 Nebula 呼叫與回填邏輯在 common.py::ensure_nda_enriched()，跟案例平台/審核頁開案時
的即時補值（JIT）共用同一份程式碼；這支腳本只負責找出目前所有還缺資料的 job_code 並整批跑過一輪。
"""
from dotenv import load_dotenv
from sqlalchemy import text

from common import NDA_INCOMPLETE_WHERE, ensure_nda_enriched
from db import SessionLocal

load_dotenv()


def main():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(f"SELECT job_code FROM nda_work_station_apply WHERE {NDA_INCOMPLETE_WHERE}")
        ).mappings().all()
        job_codes = [r["job_code"] for r in rows]
        if not job_codes:
            print("沒有需要補資料的 job_code。")
            return

        print(f"待補資料的 job_code：{job_codes}")
        for job_code in job_codes:
            ensure_nda_enriched(db, job_code)
            print(f"  [DONE] {job_code}")

        print(f"完成：處理 {len(job_codes)} 筆（實際是否補到資料請查 nda_work_station_apply）。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
