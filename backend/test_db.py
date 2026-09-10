from sqlalchemy import text
from db import engine  # 假設你剛剛建立的檔案叫 db.py

try:
    # 嘗試建立連線並發送一個最簡單的 SQL 查詢
    with engine.connect() as connection:
        result = connection.execute(text("SELECT VERSION();"))
        db_version = result.fetchone()
        
        print("--------------------------------------------------")
        print("成功連接到 AWS RDS 資料庫！")
        print(f"資料庫版本資訊: {db_version[0]}")
        print("--------------------------------------------------")
        
except Exception as e:
    print("--------------------------------------------------")
    print("❌ 連線失敗，請檢查以下項目：")
    print(e)
    print("--------------------------------------------------")