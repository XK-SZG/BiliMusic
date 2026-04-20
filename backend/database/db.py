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
from sqlalchemy import event

# [性能优化] 数据库连接池配置优化
from backend.core.config import get_config

config = get_config()
db_config = config.get_database_config()

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 20  # SQLite 锁等待超时（秒）
    },
    poolclass=QueuePool,
    pool_size=db_config.get('pool_size', 20),
    max_overflow=db_config.get('max_overflow', 40),
    pool_timeout=db_config.get('pool_timeout', 10),
    pool_recycle=db_config.get('pool_recycle', 1800),
    pool_pre_ping=True,    # [优化] 连接前检查有效性，防止使用失效连接
    echo_pool=False        # 生产环境关闭连接池日志
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()