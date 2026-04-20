import queue
import threading
import os
import yt_dlp
import logging
import time
import requests
from .clipboard_service import get_thread_safe_db_session
from ..database.models import Video

# 任务队列
download_queue = queue.Queue()

# 【新增】全局进度缓存 (内存字典) { "bvid": 45.5 }
progress_cache = {}

# 【新增】取消标志集合 (内存集合) { "bvid1", "bvid2", ... }
cancelled_tasks = set()


class Downloader:
    def __init__(self, download_path, session):
        self.download_path = download_path
        self.session = session
        from ..core.paths import DATA_DIR
        from ..core.config import get_config
        self.covers_path = os.path.join(DATA_DIR, "covers")
        os.makedirs(self.download_path, exist_ok=True)
        os.makedirs(self.covers_path, exist_ok=True)

        # [性能优化] 引入并发下载池，消除单线程下的网络 I/O 与信息抽取(yt-dlp解析)的阻塞
        # 从配置文件读取并发线程数
        config = get_config()
        self.max_workers = config.get('download.max_workers', 3)
        self.max_retries = config.get('download.max_retries', 3)
        logging.info(f"[下载服务] 初始化 {self.max_workers} 个下载工作线程")
        for i in range(self.max_workers):
            worker_thread = threading.Thread(target=self._worker, name=f"DownloadWorker-{i}", daemon=True)
            worker_thread.start()
    
    def _verify_file_integrity(self, file_path, min_size_mb=0.5):
        """校验文件是否存在且大小合理"""
        if not os.path.exists(file_path):
            return False
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb < min_size_mb:
                logging.warning(f"文件过小，可能损坏: {file_path} ({file_size_mb:.2f}MB)")
                return False
            return True
        except Exception as e:
            logging.error(f"文件校验异常: {e}")
            return False

    def add_to_queue(self, bvid: str, quality: int = 80):
        """
        [性能优化] 使用条件更新代替悲观锁，避免 SQLite 锁竞争
        """
        # 清除旧的取消标志（如果存在）
        if bvid in cancelled_tasks:
            logging.info(f"[下载队列] 清除旧的取消标志: {bvid}")
            cancelled_tasks.discard(bvid)
        
        with get_thread_safe_db_session() as db:
            # [性能优化] 移除 with_for_update()，使用原子条件更新
            # 仅当状态为 not_downloaded 或 failed 时才允许加入队列
            updated_count = db.query(Video).filter(
                Video.bvid == bvid,
                Video.download_status.in_(['not_downloaded', 'failed'])
            ).update(
                {"download_status": "pending"},
                synchronize_session=False
            )
            db.commit()
            
            # 如果 updated_count == 0，说明记录不存在或状态不满足条件
            if updated_count == 0:
                logging.info(f"[下载队列] 视频 {bvid} 正在处理中或不存在，忽略加入请求")
                return False

        # 更新成功后，放入内存队列
        download_queue.put((bvid, quality))
        progress_cache[bvid] = 0
        logging.info(f"[下载队列] 视频 {bvid} 已加入下载队列 (QN={quality})")
        return True

    def _worker(self):
        worker_name = threading.current_thread().name
        logging.info(f"[{worker_name}] 下载工作线程已启动")
        while True:
            bvid = None
            try:
                task = download_queue.get()
                bvid, quality = task if isinstance(task, tuple) else (task, 80)
                self._process_download(bvid, quality)
            except Exception as e:
                logging.error(f"[{worker_name}] 下载线程发生致命错误: {e}")
            finally:
                download_queue.task_done()
                # 下载结束（无论成功失败），清除进度缓存
                if bvid and bvid in progress_cache:
                    del progress_cache[bvid]

    def _download_cover(self, bvid, pic_url):
        if not pic_url or not pic_url.startswith("http"):
            return pic_url
            
        try:
            ext = os.path.splitext(pic_url)[1].split('@')[0]
            if not ext or len(ext) > 5: ext = ".jpg"
            filename = f"{bvid}_cover{ext}"
            file_path = os.path.join(self.covers_path, filename)
            
            if not os.path.exists(file_path):
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com/"
                }
                # [性能优化] 缩短超时时间，避免单封面下载卡死整个下载工作线程
                resp = requests.get(pic_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
            return filename
        except Exception as e:
            logging.error(f"下载封面失败 {bvid}: {e}")
            return pic_url

    def _process_download(self, bvid, quality=80):
        max_retries = 3
        title = ""
        pic_url = ""
        retry_count = 0
        
        # 检查任务是否已被取消
        if bvid in cancelled_tasks:
            logging.info(f"[下载取消] 任务已被取消: {bvid}")
            cancelled_tasks.discard(bvid)
            return
        
        with get_thread_safe_db_session() as db:
            video = db.query(Video).filter(Video.bvid == bvid).first()
            if not video: return
            
            # 再次检查数据库状态，确保任务未被取消
            if video.download_status == 'not_downloaded':
                logging.info(f"[下载取消] 任务状态已重置: {bvid}")
                return
            
            title = video.title
            pic_url = video.pic
            retry_count = video.download_retry_count
            video.download_status = 'downloading'
            logging.info(f"[下载开始] bvid={bvid}, title={title}, quality={quality}, retry={retry_count}")

        try:
            # 在下载过程中定期检查取消标志
            if bvid in cancelled_tasks:
                logging.info(f"[下载取消] 下载过程中被取消: {bvid}")
                cancelled_tasks.discard(bvid)
                with get_thread_safe_db_session() as db:
                    video = db.query(Video).filter(Video.bvid == bvid).first()
                    if video:
                        video.download_status = 'not_downloaded'
                return
            filename = f"{bvid}.mp4"
            file_path = os.path.join(self.download_path, filename)

            # 检查文件是否已存在且完整
            if os.path.exists(file_path):
                if self._verify_file_integrity(file_path):
                    logging.info(f"文件已存在且完整: {filename}")
                else:
                    logging.warning(f"文件已存在但不完整，重新下载: {filename}")
                    os.remove(file_path)
                    self._download_video_file(bvid, file_path, quality)
            else:
                self._download_video_file(bvid, file_path, quality)
            
            # 下载完成后校验文件
            if not self._verify_file_integrity(file_path):
                raise Exception(f"文件校验失败: {file_path}")
                
            # --- 记录下载产生的网络流量 ---
            try:
                file_size = os.path.getsize(file_path)
                from datetime import datetime
                from ..database import models
                with get_thread_safe_db_session() as db:
                    today = datetime.utcnow().strftime('%Y-%m-%d')
                    stat = db.query(models.DailyStat).filter(models.DailyStat.date == today).first()
                    if not stat:
                        stat = models.DailyStat(date=today)
                        db.add(stat)
                    stat.network_traffic += file_size
                    stat.uncached_traffic += file_size # 下载肯定是未缓存的流量
                    db.commit()
            except Exception as e:
                logging.error(f"记录下载流量失败: {e}")

            # 封面同步下载逻辑
            local_pic = self._download_cover(bvid, pic_url)

            # 下载成功，重置重试计数
            with get_thread_safe_db_session() as db:
                video = db.query(Video).filter(Video.bvid == bvid).first()
                if video:
                    video.download_status = 'completed'
                    video.local_path = file_path
                    video.download_retry_count = 0
                    if local_pic and local_pic != video.pic:
                        video.pic = local_pic
            
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            logging.info(f"[下载完成] bvid={bvid}, file_size={file_size_mb:.2f}MB")

        except Exception as e:
            error_msg = str(e)
            
            # 如果是用户取消，不视为失败
            if "取消" in error_msg or "cancelled" in error_msg.lower():
                logging.info(f"[下载取消] 用户取消下载: {bvid}")
                cancelled_tasks.discard(bvid)
                with get_thread_safe_db_session() as db:
                    video = db.query(Video).filter(Video.bvid == bvid).first()
                    if video:
                        video.download_status = 'not_downloaded'
                # 删除未完成的文件
                file_path = os.path.join(self.download_path, f"{bvid}.mp4")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logging.info(f"已删除未完成的文件: {file_path}")
                    except:
                        pass
                return
            
            logging.error(f"[下载失败] bvid={bvid}, error={error_msg}", exc_info=True)
            
            with get_thread_safe_db_session() as db:
                video = db.query(Video).filter(Video.bvid == bvid).first()
                if video:
                    # 检查是否已被取消，如果是则不重试
                    if video.download_status == 'not_downloaded' or bvid in cancelled_tasks:
                        logging.info(f"[下载取消] 任务已被取消，不重试: {bvid}")
                        video.download_status = 'not_downloaded'
                        cancelled_tasks.discard(bvid)
                        return
                    
                    video.download_retry_count += 1
                    
                    # 如果未达到最大重试次数，重新加入队列
                    if video.download_retry_count < max_retries:
                        logging.info(f"将重试下载 ({video.download_retry_count}/{max_retries}): {bvid}")
                        video.download_status = 'pending'
                        download_queue.put((bvid, quality))
                    else:
                        logging.error(f"下载失败次数过多，放弃: {bvid}")
                        video.download_status = 'failed'

    def _download_video_file(self, bvid_string, output_path, quality=80):
        import tempfile
        
        is_part = "_p" in bvid_string
        real_bvid, p_num = (bvid_string.split("_p")[0], bvid_string.split("_p")[1]) if is_part else (bvid_string, None)

        # 将 Cookie 保存到临时文件（Netscape 格式）
        cookie_file = None
        try:
            cookie_dict = self.session.cookies.get_dict()
            if cookie_dict:
                cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
                cookie_file.write("# Netscape HTTP Cookie File\n")
                for name, value in cookie_dict.items():
                    # 格式：domain flag path secure expiration name value
                    cookie_file.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
                cookie_file.close()

            def progress_hook(d):
                # 检查任务是否被取消
                if bvid_string in cancelled_tasks:
                    logging.info(f"[下载取消] 检测到取消标志，中断下载: {bvid_string}")
                    raise Exception(f"下载已被用户取消: {bvid_string}")
                
                if d['status'] == 'downloading':
                    try:
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        if total and total > 0:
                            percent = (downloaded / total) * 100
                            progress_cache[bvid_string] = round(percent, 1)
                        else:
                            import re
                            p_str = d.get('_percent_str', '0%')
                            clean_p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str).replace('%', '').strip()
                            # [修复] 视频和音频分开下载时（DASH流），第二个流（音频）的进度会从 0 重新开始。
                            # 简单的累加策略：如果是第一次（视频流），我们映射到 0~80%；
                            # 第二次（音频流或合并阶段），映射到 80~100%，以保证进度条单调递增，不会闪回。
                            val = float(clean_p_str)
                            prev_val = progress_cache.get(bvid_string, 0)
                            
                            # 检测到骤降，说明进入了阶段 2
                            if val < 5.0 and prev_val > 70.0:
                                progress_cache[bvid_string] = 80.0 + (val * 0.2)
                            else:
                                if prev_val > 80.0:
                                    progress_cache[bvid_string] = 80.0 + (val * 0.2)
                                else:
                                    progress_cache[bvid_string] = val * 0.8
                    except Exception as e:
                        if "取消" in str(e):
                            raise
                        pass
                elif d['status'] == 'finished':
                    # yt-dlp 每个流下载完都会触发一次 finished
                    prev_val = progress_cache.get(bvid_string, 0)
                    if prev_val > 80.0:
                        progress_cache[bvid_string] = 100.0
                    else:
                        progress_cache[bvid_string] = 80.0

            max_height = 720
            if quality >= 120: max_height = 2160
            elif quality >= 80: max_height = 1080

            ydl_opts = {
                # 优先选择 AVC (H.264) 编码的视频以确保浏览器兼容性，回退到其他编码的 bestvideo
                'format': f'bestvideo[height<={max_height}][vcodec^=avc]+bestaudio/bestvideo[height<={max_height}]+bestaudio/best',
                'outtmpl': output_path,
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'http_headers': {'Referer': 'https://www.bilibili.com'},
                'progress_hooks': [progress_hook],
                # [性能优化] 禁用播放列表解析，跳过评论和弹幕，极致加快 yt-dlp 初始化与元数据抽取速度
                'noplaylist': True,
                'extract_flat': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'getcomments': False,
                # [性能优化] 开启并发片段下载（适用于 B 站 DASH 流切片），最大化带宽利用率
                'concurrent_fragment_downloads': 3,
                # [性能优化] 禁用预处理校验防止卡死
                'check_formats': False,
                'ignoreerrors': True,
                # 避免下载到临时文件，然后移动和重命名的I/O开销，对大文件极其明显
                'outtmpl': output_path,
                'nocachedir': True
            }

            # 使用 cookiefile 而不是通过 header 传递 Cookie
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file.name

            if is_part:
                ydl_opts['playlist_items'] = str(p_num)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.bilibili.com/video/{real_bvid}"])
        
        finally:
            # 清理临时 Cookie 文件
            if cookie_file and os.path.exists(cookie_file.name):
                try:
                    os.remove(cookie_file.name)
                except:
                    pass
