import os
from urllib.parse import quote_plus  # 引入 URL 編碼工具
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. 載入根目錄底下的 .env 檔案
load_dotenv()

# 組合 RDS 連線字串: 
# postgresql+psycopg2://username:password@endpoint:5432/database_name
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 取得資料庫連線的 Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()