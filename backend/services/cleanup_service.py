import os
import re
import time
import logging
from .clipboard_service import get_thread_safe_db_session
from ..database.models import Video
from ..core.paths import BASE_DIR, DATA_DIR
from ..core.config import get_config

# 使用统一的配置管理
config = get_config()
storage_config = config.get_storage_config()
scheduler_config = config.get_scheduler_config()

DOWNLOAD_PATH = storage_config.get('download_path', 'backend/data/downloads')
if not os.path.isabs(DOWNLOAD_PATH):
    if DOWNLOAD_PATH.startswith("backend/data/"):
        DOWNLOAD_PATH = os.path.join(DATA_DIR, DOWNLOAD_PATH.replace("backend/data/", ""))
    else:
        DOWNLOAD_PATH = os.path.join(BASE_DIR, DOWNLOAD_PATH)
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

CACHE_LIMIT_BYTES = storage_config.get('cache_limit_gb', 10) * 1024 * 1024 * 1024
CLEANUP_INTERVAL_SECONDS = scheduler_config.get('cleanup_interval_hours', 6) * 3600

logging.info(f"[清理服务] 下载目录: {DOWNLOAD_PATH}")
logging.info(f"[清理服务] 缓存上限: {storage_config.get('cache_limit_gb', 10)} GB")
logging.info(f"[清理服务] 清理间隔: {scheduler_config.get('cleanup_interval_hours', 6)} 小时")


def run_cleanup_scheduler():
    logging.info("自动清理服务已启动")
    while True:
        try:
            _clean_orphan_files()
            _enforce_cache_limit()
        except Exception as e:
            logging.error(f"清理任务执行出错: {e}")
        time.sleep(CLEANUP_INTERVAL_SECONDS)


def clean_caches():
    """[新增] 立即执行一次完整清理，供错误系统「一键修复（存储空间不足）」调用。

    返回 (清理的孤立文件数, 释放前的缓存字节数)，异常时由调用方捕获。
    """
    orphan_removed = _clean_orphan_files()
    before_bytes = 0
    with get_thread_safe_db_session() as db:
        for (local_path,) in db.query(Video.local_path).filter(
                Video.download_status == 'completed').all():
            if local_path and os.path.exists(local_path):
                try:
                    before_bytes += os.path.getsize(local_path)
                except Exception:
                    pass
    _enforce_cache_limit()
    logging.info(f"[清理服务] 手动清理完成：孤立文件 {orphan_removed} 个，清理前缓存 {before_bytes} 字节")
    return orphan_removed, before_bytes


def _clean_orphan_files():
    """清理数据库中已不存在记录的物理文件"""
    logging.info("开始扫描孤立缓存文件...")
    removed = 0
    with get_thread_safe_db_session() as db:
        all_videos_in_db = {v.bvid for v in db.query(Video.bvid).all()}

        for filename in os.listdir(DOWNLOAD_PATH):
            # 从文件名中提取 BV 号（支持多集视频的 _pX 后缀）
            # 匹配 BVxxxx.mp4 或 BVxxxx_pX.mp4
            bvid_match = re.search(r'(BV[a-zA-Z0-9]{10}(?:_p\d+)?)', filename)
            if bvid_match:
                bvid = bvid_match.group(1)
                if bvid not in all_videos_in_db:
                    file_path = os.path.join(DOWNLOAD_PATH, filename)
                    try:
                        os.remove(file_path)
                        removed += 1
                        logging.info(f"清理孤立文件: {filename}")
                    except Exception as e:
                        logging.warning(f"清理孤立文件失败 {filename}: {e}")
    return removed


def _enforce_cache_limit():
    """清理最旧的文件以满足缓存上限"""
    logging.info("开始检查缓存大小...")
    
    with get_thread_safe_db_session() as db:
        # 获取所有已下载的视频，按添加时间升序（最旧的在前）
        # 排除本地导入的视频 (is_local == 1) 和已加入任何媒体库的视频 (~Video.collections.any())
        videos_to_prune = db.query(Video).filter(
            Video.download_status == 'completed',
            Video.is_local == 0,
            ~Video.collections.any()
        ).order_by(Video.added_at.asc()).all()

        total_size = 0
        valid_videos = []
        for v in videos_to_prune:
            if v.local_path and os.path.exists(v.local_path):
                try:
                    size = os.path.getsize(v.local_path)
                    total_size += size
                    valid_videos.append((v, size))
                except Exception as e:
                    logging.warning(f"无法获取文件大小 {v.local_path}: {e}")

        if total_size <= CACHE_LIMIT_BYTES:
            logging.info("缓存大小正常")
            return

        logging.info(f"缓存超限 ({total_size / 1024 ** 3:.2f}GB > {CACHE_LIMIT_BYTES / 1024 ** 3:.2f}GB)，开始清理...")

        for video, file_size in valid_videos:
            if total_size <= CACHE_LIMIT_BYTES:
                break

            local_path_copy = video.local_path
            bvid = video.bvid
            title = video.title
            
            # 先尝试删除物理文件，因为在 Windows 上文件可能被播放器占用导致删除失败
            try:
                os.remove(local_path_copy)
            except Exception as e:
                logging.warning(f"文件删除失败 (可能被占用)，跳过清理 {title}: {e}")
                continue
            
            # 文件删除成功后，再更新数据库状态
            try:
                db.query(Video).filter(Video.bvid == bvid).update({
                    "download_status": "not_downloaded",
                    "local_path": None
                })
                db.commit()
                total_size -= file_size
                logging.info(f"清理旧缓存: {title}")
            except Exception as e:
                logging.error(f"更新数据库失败 {title}: {e}")
                db.rollback()