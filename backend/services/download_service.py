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


class Downloader:
    def __init__(self, download_path, session):
        self.download_path = download_path
        self.session = session
        from ..core.paths import DATA_DIR
        self.covers_path = os.path.join(DATA_DIR, "covers")
        os.makedirs(self.download_path, exist_ok=True)
        os.makedirs(self.covers_path, exist_ok=True)

        worker_thread = threading.Thread(target=self._worker, daemon=True)
        worker_thread.start()

    def add_to_queue(self, bvid: str, quality: int = 80):
        with get_thread_safe_db_session() as db:
            video = db.query(Video).filter(Video.bvid == bvid).first()
            if not video or video.download_status in ['completed', 'downloading', 'pending']:
                return False
            video.download_status = 'pending'

        download_queue.put((bvid, quality))
        # 初始化进度
        progress_cache[bvid] = 0
        logging.info(f"视频 {bvid} 已加入下载队列 (QN={quality})")
        return True

    def _worker(self):
        logging.info("下载工作线程已启动")
        while True:
            try:
                task = download_queue.get()
                bvid, quality = task if isinstance(task, tuple) else (task, 80)
                self._process_download(bvid, quality)
            except Exception as e:
                logging.error(f"下载线程发生致命错误: {e}")
            finally:
                download_queue.task_done()
                # 下载结束（无论成功失败），清除进度缓存
                if 'bvid' in locals() and bvid in progress_cache:
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
                resp = requests.get(pic_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
            return filename
        except Exception as e:
            logging.error(f"下载封面失败 {bvid}: {e}")
            return pic_url

    def _process_download(self, bvid, quality=80):
        title = ""
        pic_url = ""
        with get_thread_safe_db_session() as db:
            video = db.query(Video).filter(Video.bvid == bvid).first()
            if not video: return
            title = video.title
            pic_url = video.pic
            video.download_status = 'downloading'
            logging.info(f"开始下载: {title} ({bvid}) QN={quality}")

        try:
            filename = f"{bvid}.mp4"
            file_path = os.path.join(self.download_path, filename)

            if os.path.exists(file_path):
                logging.info(f"文件已存在: {filename}")
            else:
                self._download_video_file(bvid, file_path, quality)
                
            # 封面同步下载逻辑
            local_pic = self._download_cover(bvid, pic_url)

            with get_thread_safe_db_session() as db:
                video = db.query(Video).filter(Video.bvid == bvid).first()
                if video:
                    video.download_status = 'completed'
                    video.local_path = file_path
                    if local_pic and local_pic != video.pic:
                        video.pic = local_pic
            logging.info(f"下载成功: {title}")

        except Exception as e:
            logging.error(f"下载失败 {title}: {e}")
            with get_thread_safe_db_session() as db:
                video = db.query(Video).filter(Video.bvid == bvid).first()
                if video: video.download_status = 'failed'

    def _download_video_file(self, bvid_string, output_path, quality=80):
        is_part = "_p" in bvid_string
        real_bvid, p_num = (bvid_string.split("_p")[0], bvid_string.split("_p")[1]) if is_part else (bvid_string, None)

        cookie_str = "; ".join([f"{k}={v}" for k, v in self.session.cookies.get_dict().items()])

        def progress_hook(d):
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
                        progress_cache[bvid_string] = float(clean_p_str)
                except:
                    pass
            elif d['status'] == 'finished':
                progress_cache[bvid_string] = 100.0

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
            'http_headers': {'Cookie': cookie_str, 'Referer': 'https://www.bilibili.com'},
            'progress_hooks': [progress_hook]
        }

        if is_part:
            ydl_opts['playlist_items'] = str(p_num)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.bilibili.com/video/{real_bvid}"])
