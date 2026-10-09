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
        
        # 3. 迁移：添加 download_retry_count
        if 'download_retry_count' not in columns:
            logger.info("正在迁移数据库: 添加 download_retry_count 列...")
            cursor.execute("ALTER TABLE videos ADD COLUMN download_retry_count INTEGER DEFAULT 0")
        
        # 4. 迁移：为 completed 状态但 local_path 为空的记录填充路径
        logger.info("正在迁移数据库: 填充 local_path...")
        from .core.paths import DATA_DIR
        download_path = os.path.join(DATA_DIR, "downloads")
        
        cursor.execute("""
            SELECT bvid FROM videos
            WHERE download_status = 'completed'
            AND (local_path IS NULL OR local_path = '')
            AND is_local = 0
        """)
        videos_to_fix = cursor.fetchall()
        
        fixed_count = 0
        for (bvid,) in videos_to_fix:
            expected_path = os.path.join(download_path, f"{bvid}.mp4")
            if os.path.exists(expected_path):
                cursor.execute(
                    "UPDATE videos SET local_path = ? WHERE bvid = ?",
                    (expected_path, bvid)
                )
                fixed_count += 1
        
        if fixed_count > 0:
            logger.info(f"已为 {fixed_count} 个视频填充 local_path")

        # 获取 collections 表的所有列名
        cursor.execute("PRAGMA table_info(collections)")
        col_columns = [info[1] for info in cursor.fetchall()]
        if 'order_index' not in col_columns:
            logger.info("正在迁移数据库: 添加 order_index 列到 collections...")
            cursor.execute("ALTER TABLE collections ADD COLUMN order_index INTEGER DEFAULT 0")
            
        # 5. 迁移：为关键字段添加索引以提升查询性能
        logger.info("正在迁移数据库: 检查并创建索引...")
        # 检查是否已存在索引
        cursor.execute("PRAGMA index_list(videos)")
        existing_indexes = [info[1] for info in cursor.fetchall()]
        
        if 'ix_videos_download_status' not in existing_indexes:
            logger.info("创建索引: ix_videos_download_status")
            cursor.execute("CREATE INDEX ix_videos_download_status ON videos (download_status)")
            
        if 'ix_videos_is_local' not in existing_indexes:
            logger.info("创建索引: ix_videos_is_local")
            cursor.execute("CREATE INDEX ix_videos_is_local ON videos (is_local)")
            
        if 'ix_videos_owner' not in existing_indexes:
            logger.info("创建索引: ix_videos_owner")
            cursor.execute("CREATE INDEX ix_videos_owner ON videos (owner)")

        conn.commit()
        logger.info("数据库迁移检查完成")
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        conn.rollback()
        # [修复] 原实现只记录日志并吞掉异常，导致 backend/main.py 的 lifespan 里
        # 「迁移失败 -> get_error_manager().report_exception(scope='database')」分支
        # 永远不会执行：用户升级后如果迁移失败，界面不会出现任何错误提示，
        # 而旧库缺少新列会让后续请求以各种奇怪的 500 报错，极难定位。
        # 这里回滚后重新抛出，交由调用方登记到错误系统。
        raise
    finally:
        conn.close()

def migrate():
    # 兼容老版直接调用 migrate() 的代码
    run_migrations()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
