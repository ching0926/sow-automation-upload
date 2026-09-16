"""
批次腳本：對 nda_work_station_apply 裡還缺 dri_mail/manager_mail/estimated_mandays/total_cost
（或其他明細欄位）的 job_code，呼叫 Nebula API 查詢後回填。可重複執行——只處理欄位還是 NULL 的資料列。
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv
from sqlalchemy import text

from db import SessionLocal

load_dotenv()

NEBULA_API_BASE = os.getenv("NEBULA_API_BASE", "https://api.nebula.sit.ecvhrm.com")
NEBULA_CLIENT_ID = os.getenv("NEBULA_CLIENT_ID")
NEBULA_CLIENT_SECRET = os.getenv("NEBULA_CLIENT_SECRET")


def _request_json(method, url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_access_token():
    result = _request_json(
        "POST",
        f"{NEBULA_API_BASE}/auth/token",
        body={"client_id": NEBULA_CLIENT_ID, "client_secret": NEBULA_CLIENT_SECRET},
    )
    return result["access_token"]


def fetch_jobcode_dri(token, job_code):
    query = urllib.parse.urlencode({"skipDri": "false", "top": 10, "includesLeave": "false"})
    url = f"{NEBULA_API_BASE}/api/v1/jobcode/{urllib.parse.quote(job_code)}/dri?{query}"
    try:
        result = _request_json("GET", url, headers={"Authorization": f"Bearer {token}"})
        return result["data"]
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] {job_code}: HTTP {e.code} {e.read().decode('utf-8', 'ignore')}")
        return None
    except urllib.error.URLError as e:
        print(f"  [FAIL] {job_code}: {e}")
        return None


def main():
    if not NEBULA_CLIENT_ID or not NEBULA_CLIENT_SECRET:
        raise SystemExit("請先在 .env 設定 NEBULA_CLIENT_ID / NEBULA_CLIENT_SECRET")

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT job_code FROM nda_work_station_apply
                WHERE dri_mail IS NULL OR manager_mail IS NULL
                   OR dri_name IS NULL OR dri_fullname IS NULL
                   OR dri_deptno IS NULL OR dri_deptname IS NULL
                   OR manager_name IS NULL OR manager_fullname IS NULL
                   OR manager_deptno IS NULL OR manager_deptname IS NULL
                   OR estimated_mandays IS NULL OR total_cost IS NULL
                """
            )
        ).mappings().all()
        job_codes = [r["job_code"] for r in rows]
        if not job_codes:
            print("沒有需要補資料的 job_code。")
            return

        print(f"待補資料的 job_code：{job_codes}")
        token = get_access_token()

        success, failed = 0, 0
        for job_code in job_codes:
            data = fetch_jobcode_dri(token, job_code)
            if data is None:
                failed += 1
                continue

            user_job_info = data.get("userJobInfo") or []
            dri_info = user_job_info[0] if len(user_job_info) > 0 else {}
            manager_info = user_job_info[1] if len(user_job_info) > 1 else {}
            dri_mail = dri_info.get("companyEmail")
            manager_mail = manager_info.get("companyEmail")

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
                    "dri_mail": dri_mail,
                    "dri_deptno": dri_info.get("deptNo"),
                    "dri_deptname": dri_info.get("deptName"),
                    "dri_name": dri_info.get("userName"),
                    "dri_fullname": dri_info.get("userFullName"),
                    "manager_mail": manager_mail,
                    "manager_deptno": manager_info.get("deptNo"),
                    "manager_deptname": manager_info.get("deptName"),
                    "manager_name": manager_info.get("userName"),
                    "manager_fullname": manager_info.get("userFullName"),
                    "job_code": job_code,
                },
            )
            db.commit()
            print(f"  [OK] {job_code}: mandays={data.get('estimatedMandays')} cost={data.get('totalCost')} dri_mail={dri_mail} manager_mail={manager_mail}")
            success += 1

        print(f"完成：成功 {success} 筆，失敗 {failed} 筆。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
