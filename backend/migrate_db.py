# -*- coding: utf-8 -*-
# Path: backend/migrate_db.py

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

def run_migrations():
    from .core.paths import DATA_DIR
    db_path = os.path.join(DATA_DIR, 'bili_player.db')
    
    if not os.path.exists(db_path):
        logger.info("数据库文件不存在，跳过迁移 (将由 SQLAlchemy 自动创建)")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取 videos 表的所有列名
        cursor.execute("PRAGMA table_info(videos)")
        columns = [info[1] for info in cursor.fetchall()]
        
        # 1. 迁移：添加 trim_start 和 trim_end
        if 'trim_start' not in columns:
            logger.info("正在迁移数据库: 添加 trim_start 列...")
            cursor.execute("ALTER TABLE videos ADD COLUMN trim_start FLOAT DEFAULT 0.0")
            
        if 'trim_end' not in columns:
            logger.info("正在迁移数据库: 添加 trim_end 列...")
            cursor.execute("ALTER TABLE videos ADD COLUMN trim_end FLOAT DEFAULT 0.0")
            
        # 2. 迁移：添加 is_local 和 local_mimetype
        if 'is_local' not in columns:
            logger.info("正在迁移数据库: 添加 is_local 列...")
            cursor.execute("ALTER TABLE videos ADD COLUMN is_local INTEGER DEFAULT 0")

        if 'local_mimetype' not in columns:
            logger.info("正在迁移数据库: 添加 local_mimetype 列...")
            cursor.execute("ALTER TABLE videos ADD COLUMN local_mimetype TEXT")
            
        if 'order_index' not in columns:
            logger.info("正在迁移数据库: 添加 order_index 列到 videos...")
            cursor.execute("ALTER TABLE videos ADD COLUMN order_index INTEGER DEFAULT 0")

        # 获取 collections 表的所有列名
        cursor.execute("PRAGMA table_info(collections)")
        col_columns = [info[1] for info in cursor.fetchall()]
        if 'order_index' not in col_columns:
            logger.info("正在迁移数据库: 添加 order_index 列到 collections...")
            cursor.execute("ALTER TABLE collections ADD COLUMN order_index INTEGER DEFAULT 0")
            
        conn.commit()
        logger.info("数据库迁移检查完成")
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        conn.rollback()
    finally:
        conn.close()

def migrate():
    # 兼容老版直接调用 migrate() 的代码
    run_migrations()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
