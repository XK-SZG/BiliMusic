from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from backend.core.paths import DATA_DIR

# 确保数据目录存在
DB_DIR = DATA_DIR
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DATABASE_URL = f"sqlite:///{DB_DIR}/bili_player.db"

from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()