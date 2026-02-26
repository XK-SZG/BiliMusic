import os
import re
import time
import logging
import yaml
from .clipboard_service import get_thread_safe_db_session
from ..database.models import Video
from ..core.paths import BASE_DIR

# 获取项目根目录下的 config.yaml
config_path = os.path.join(BASE_DIR, "config.yaml")

with open(config_path, 'r', encoding='utf-8') as f: # 添加 encoding='utf-8'
    config = yaml.safe_load(f)

from ..core.paths import DATA_DIR

DOWNLOAD_PATH = config['storage']['download_path']
if not os.path.isabs(DOWNLOAD_PATH):
    if DOWNLOAD_PATH.startswith("backend/data/"):
        DOWNLOAD_PATH = os.path.join(DATA_DIR, DOWNLOAD_PATH.replace("backend/data/", ""))
    else:
        DOWNLOAD_PATH = os.path.join(BASE_DIR, DOWNLOAD_PATH)
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

CACHE_LIMIT_BYTES = config['storage']['cache_limit_gb'] * 1024 * 1024 * 1024
CLEANUP_INTERVAL_SECONDS = config['scheduler']['cleanup_interval_hours'] * 3600


def run_cleanup_scheduler():
    logging.info("自动清理服务已启动")
    while True:
        try:
            _clean_orphan_files()
            _enforce_cache_limit()
        except Exception as e:
            logging.error(f"清理任务执行出错: {e}")
        time.sleep(CLEANUP_INTERVAL_SECONDS)


def _clean_orphan_files():
    """清理数据库中已不存在记录的物理文件"""
    logging.info("开始扫描孤立缓存文件...")
    with get_thread_safe_db_session() as db:
        all_videos_in_db = {v.bvid for v in db.query(Video.bvid).all()}

        for filename in os.listdir(DOWNLOAD_PATH):
            # 从文件名 'Title - BVxxxx.mp4' 中提取 BV 号
            bvid_match = re.search(r'(BV[a-zA-Z0-9]{10})', filename)
            if bvid_match:
                bvid = bvid_match.group(1)
                if bvid not in all_videos_in_db:
                    file_path = os.path.join(DOWNLOAD_PATH, filename)
                    os.remove(file_path)
                    logging.info(f"清理孤立文件: {filename}")


def _enforce_cache_limit():
    """清理最旧的文件以满足缓存上限"""
    logging.info("开始检查缓存大小...")
    total_size = sum(os.path.getsize(os.path.join(DOWNLOAD_PATH, f)) for f in os.listdir(DOWNLOAD_PATH))

    if total_size <= CACHE_LIMIT_BYTES:
        logging.info("缓存大小正常")
        return

    logging.info(f"缓存超限 ({total_size / 1024 ** 3:.2f}GB > {CACHE_LIMIT_BYTES / 1024 ** 3:.2f}GB)，开始清理...")
    with get_thread_safe_db_session() as db:
        # 获取所有已下载的视频，按添加时间升序（最旧的在前）
        videos_to_prune = db.query(Video).filter(Video.download_status == 'completed').order_by(
            Video.added_at.asc()).all()

        for video in videos_to_prune:
            if total_size <= CACHE_LIMIT_BYTES:
                break

            if video.local_path and os.path.exists(video.local_path):
                file_size = os.path.getsize(video.local_path)
                os.remove(video.local_path)
                video.download_status = 'not_downloaded'
                video.local_path = None
                total_size -= file_size
                logging.info(f"清理旧缓存: {video.title}")
        db.commit()