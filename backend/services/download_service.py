import queue
import threading
import os
import sys
import contextlib
import yt_dlp
import logging
import shutil
import time
import requests
from datetime import datetime
from .clipboard_service import get_thread_safe_db_session
from ..database.models import Video

# 任务队列
download_queue = queue.Queue()

# 【新增】全局进度缓存 (内存字典) { "bvid": 45.5 }
progress_cache = {}

# 【新增】取消标志集合 (内存集合) { "bvid1", "bvid2", ... }
cancelled_tasks = set()


# ============================================================
# [修复] yt-dlp 控制台输出隔离
# ------------------------------------------------------------
# 问题现象：下载进行到中途抛出
#   OSError: [Errno 22] Invalid argument
# 调用栈固定落在 yt_dlp\minicurses.py -> yt_dlp\utils\_utils.py:write_string，
# 即 yt-dlp 在向标准错误流写进度条时命中了失效 / 不可写的控制台句柄。
# 该异常会被包装成 UnavailableVideoError 冒泡到下载流程，导致：
#   1. 下载在未完成时中断（进度停在 < 100%）；
#   2. 被计入失败重试，而重试计数此前不会因用户「重新下载」而重置，
#      于是表现为「某个媒体永远下载不了」。
#
# 修复策略（双保险）：
#   A. 彻底禁用 yt-dlp 的终端输出渲染（noprogress / noconsoletitle / 静默 logger），
#      从源头避免写终端；
#   B. 下载期间把 sys.stdout / sys.stderr 临时替换为永不抛错的守卫流，
#      即使仍有残留写入也只会被丢弃，不会中断下载。
# 进度数据仍通过 progress_hooks 正常回调，界面进度条不受影响。
# ============================================================

#: 是否已启用安全输出模式（由一键修复置位，并记录到日志便于诊断）
SAFE_OUTPUT_MODE = False

#: 单次写入守卫流的最大耗时（秒），防止极端情况下卡死下载线程
GUARD_WRITE_TIMEOUT = 5.0


class _StreamGuard:
    """包装一个可能失效的标准流，吞掉所有写入异常。

    - 只实现 yt-dlp / logging 实际用到的接口；
    - 任何异常（OSError / ValueError / 超时）都被静默丢弃；
    - 保留 ``isatty() == False``，让 yt-dlp 认为这不是终端，从而不做转义渲染。
    """

    def __init__(self, stream, name='stream'):
        self._stream = stream
        self._name = name
        self.encoding = getattr(stream, 'encoding', None) or 'utf-8'
        self.errors = getattr(stream, 'errors', None) or 'replace'

    # --- 供 library 使用的基础属性 ---
    @property
    def name(self):
        return f'<guarded {self._name}>'

    @property
    def closed(self):
        return False

    @property
    def mode(self):
        return getattr(self._stream, 'mode', 'w')

    def isatty(self):
        return False

    def fileno(self):
        try:
            return self._stream.fileno()
        except Exception:
            return -1

    @property
    def buffer(self):
        """返回一个字节级守卫，避免 yt-dlp 直接写底层 buffer。"""
        inner = self
        try:
            raw = self._stream.buffer
        except Exception:
            raw = None
        return _BinaryStreamGuard(raw, inner)

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return False

    def write(self, data):
        try:
            if self._stream is None or data is None:
                return len(data) if data else 0
            self._stream.write(data)
            return len(data)
        except Exception:
            return len(data) if data else 0

    def writelines(self, lines):
        for line in lines or ():
            self.write(line)

    def flush(self):
        try:
            if self._stream is not None:
                with _time_limit(GUARD_WRITE_TIMEOUT):
                    self._stream.flush()
        except Exception:
            pass

    def close(self):
        # 守卫流不接受关闭请求，避免关闭真实流
        pass


class _BinaryStreamGuard:
    """字节级守卫流。"""

    def __init__(self, raw, parent):
        self._raw = raw
        self._parent = parent
        self.encoding = parent.encoding

    def write(self, data):
        try:
            if self._raw is not None and data:
                self._raw.write(data)
            return len(data) if data else 0
        except Exception:
            return len(data) if data else 0

    def flush(self):
        self._parent.flush()

    def close(self):
        pass


@contextlib.contextmanager
def _time_limit(seconds):
    """在支持 signal 的平台上限制单次操作的耗时；不支持时退化为直接执行。"""
    if os.name == 'nt' or not hasattr(__import__('signal'), 'SIGALRM'):
        # Windows 无 SIGALRM，读取管道失败会立刻抛 OSError，无需额外保护
        yield
        return

    import signal

    def _handler(signum, frame):
        raise TimeoutError('stream write timeout')

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


@contextlib.contextmanager
def guarded_standard_streams():
    """下载期间把 sys.stdout / sys.stderr 替换为守卫流。

    说明：守卫流只是吞掉写入异常，不会吞掉业务的日志内容——
    日志的文件处理器与内存处理器在 StreamHandler 层独立工作，
    即使控制台句柄失效，日志依然完整落盘。
    """
    original_out, original_err = sys.stdout, sys.stderr
    try:
        if original_out is not None and not isinstance(original_out, _StreamGuard):
            sys.stdout = _StreamGuard(original_out, 'stdout')
        if original_err is not None and not isinstance(original_err, _StreamGuard):
            sys.stderr = _StreamGuard(original_err, 'stderr')
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            sys.stdout = original_out
            sys.stderr = original_err
        except Exception:
            pass


class _SilentYdlLogger:
    """yt-dlp 的静默日志器：把输出重定向到 logging，绝不触碰终端句柄。

    [修复] ``ignoreerrors=True`` 时 yt-dlp 只会「打印错误然后正常返回」，
    下载流程会误以为下载成功，随后才在文件校验阶段炸掉，
    导致拿不到真正的失败原因。这里顺带把错误信息收集起来，
    供 ``_download_video_file`` 抛出可诊断的异常。
    """

    def __init__(self, name='yt_dlp', error_sink=None):
        self._logger = logging.getLogger(name)
        self._error_sink = error_sink

    def debug(self, msg):
        try:
            self._logger.debug('[yt-dlp] %s', msg)
        except Exception:
            pass

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        try:
            self._logger.warning('[yt-dlp] %s', msg)
        except Exception:
            pass

    def error(self, msg):
        try:
            if self._error_sink is not None:
                self._error_sink.append(str(msg))
            self._logger.error('[yt-dlp] %s', msg)
        except Exception:
            pass


def enable_safe_output_mode(reason='manual'):
    """启用安全输出模式（一键修复 / 自动自愈均调用此函数）。"""
    global SAFE_OUTPUT_MODE
    SAFE_OUTPUT_MODE = True
    logging.warning(f'[下载服务] 已启用安全输出模式（yt-dlp 终端输出隔离），触发原因: {reason}')
    return True


def is_safe_output_mode() -> bool:
    """查询当前是否处于安全输出模式（供自检与调试接口使用）。"""
    return bool(SAFE_OUTPUT_MODE)


def build_yt_dlp_options(output_path, progress_hook, extra=None, error_sink=None):
    """构建 yt-dlp 选项（集中管理，确保安全输出开关不会被遗漏）。"""
    opts = {
        # 优先选择 AVC (H.264) 编码的视频以确保浏览器兼容性，回退到其他编码的 bestvideo
        'format': 'bestvideo[height<={h}][vcodec^=avc]+bestaudio/bestvideo[height<={h}]+bestaudio/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        # [修复 Errno 22] 彻底关闭进度渲染 / 控制台标题 / 警告输出，
        # progress_hooks 依旧会被调用，界面进度不受影响。
        'noprogress': True,
        'noconsoletitle': True,
        'no_warnings': True,
        'logger': _SilentYdlLogger(error_sink=error_sink),
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
        'nocachedir': True,
    }
    if extra:
        opts.update(extra)
    return opts


class Downloader:
    def __init__(self, download_path, session):
        self.download_path = download_path
        self.session = session
        from ..core.paths import DATA_DIR
        from ..core.config import get_config
        self.covers_path = os.path.join(DATA_DIR, "covers")
        # [新增] 失败媒体隔离区：避免重试时反复复用损坏的残留文件
        self.failed_path = os.path.join(DATA_DIR, "failed_downloads")
        os.makedirs(self.download_path, exist_ok=True)
        os.makedirs(self.covers_path, exist_ok=True)
        os.makedirs(self.failed_path, exist_ok=True)

        # [性能优化] 引入并发下载池，消除单线程下的网络 I/O 与信息抽取(yt-dlp解析)的阻塞
        # 从配置文件读取并发线程数
        config = get_config()
        self.max_workers = int(config.get('download.max_workers', 3) or 3)
        self.max_retries = int(config.get('download.max_retries', 3) or 3)
        # [修复] bool("false") 为 True：若 config.yaml 里把 keep_failed_files 写成字符串
        # "false"/"0"，原来的 bool(...) 会得到 True，用户以为丢弃的失败残留仍会被保留。
        from ..core.utils import as_bool
        self.keep_failed_files = as_bool(config.get('download.keep_failed_files', True), True)
        logging.info(f"[下载服务] 初始化 {self.max_workers} 个下载工作线程（最大重试 {self.max_retries} 次）")
        for i in range(self.max_workers):
            worker_thread = threading.Thread(target=self._worker, name=f"DownloadWorker-{i}", daemon=True)
            worker_thread.start()

        # [修复] 启动时自检：若标准流已损坏，直接进入安全输出模式，避免首次下载就踩坑
        try:
            from ..core.error_manager import probe_stream_state
            state = probe_stream_state()
            broken = [name for name, info in state.items()
                      if info.get('present') and not info.get('writable')]
            if broken:
                enable_safe_output_mode(f'启动自检发现不可写的标准流: {", ".join(broken)}')
            else:
                logging.debug(f"[下载服务] 标准流自检通过: {state}")
        except Exception as e:
            logging.debug(f"[下载服务] 标准流自检跳过: {e}")

        # [新增] 注册一键修复动作
        self._register_repairs()

    # ------------------------------------------------------------
    # 文件校验
    # ------------------------------------------------------------

    def _verify_file_integrity(self, file_path, min_size_mb=0.5):
        """校验文件是否存在、大小合理且容器头完整。

        [修复] 原实现只看体积，无法识别「下载中途被 Errno 22 打断但已写入数百 MB」
        的残缺文件，导致这类文件被误判为下载成功（或反复复用导致永远下载失败）。
        """
        if not os.path.exists(file_path):
            return False
        try:
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            if file_size_mb < min_size_mb:
                logging.warning(f"文件过小，可能损坏: {file_path} ({file_size_mb:.2f}MB)")
                return False
            if not self._has_valid_container(file_path):
                logging.warning(f"文件容器头缺失，判定为不完整: {file_path}")
                return False
            return True
        except Exception as e:
            logging.error(f"文件校验异常: {e}")
            return False

    @staticmethod
    def _has_valid_container(file_path, probe_bytes=64 * 1024):
        """轻量容器校验：MP4/FLV 等常见格式检查文件头魔数。"""
        try:
            with open(file_path, 'rb') as f:
                head = f.read(probe_bytes)
        except Exception:
            return False
        if len(head) < 12:
            return False
        # ISO BMFF (mp4/m4a/mov)：第 4~8 字节应为 'ftyp'（也可能首个 box 是 free/skip）
        if head[4:8] in (b'ftyp', b'free', b'skip', b'moov', b'mdat', b'styp'):
            return True
        # FLV
        if head[:3] == b'FLV':
            return True
        # Matroska / WebM
        if head[:4] == b'\x1a\x45\xdf\xa3':
            return True
        # MPEG-TS (0x47 同步字节)
        if head[0] == 0x47 and head[188] == 0x47:
            return True
        # 其他情况（未知但体积足够的容器）不阻断下载流程
        logging.debug(f"[下载服务] 未识别的容器头（放行）: {file_path} head={head[:8]!r}")
        return True

    # ------------------------------------------------------------
    # 队列
    # ------------------------------------------------------------

    def add_to_queue(self, bvid: str, quality: int = 80, manual_retry: bool = False):
        """
        [性能优化] 使用条件更新代替悲观锁，避免 SQLite 锁竞争

        :param manual_retry: 是否为用户主动点击「下载 / 重试」。
            为 True 时清零失败重试计数，否则历史失败会让该媒体永久无法下载
            （这正是「某媒体永远重试失败」的另一半原因）。
        """
        # 清除旧的取消标志（如果存在）
        if bvid in cancelled_tasks:
            logging.info(f"[下载队列] 清除旧的取消标志: {bvid}")
            cancelled_tasks.discard(bvid)

        # [修复] 用户主动重试时先清理上一次的失败残留，避免复用损坏文件
        if manual_retry:
            self._discard_failed_artifact(bvid)

        with get_thread_safe_db_session() as db:
            # [性能优化] 移除 with_for_update()，使用原子条件更新
            # 仅当状态为 not_downloaded 或 failed 时才允许加入队列
            updated_count = db.query(Video).filter(
                Video.bvid == bvid,
                Video.download_status.in_(['not_downloaded', 'failed'])
            ).update(
                {"download_status": "pending",
                 "download_retry_count": 0 if manual_retry else Video.download_retry_count},
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
        logging.info(f"[下载队列] 视频 {bvid} 已加入下载队列 (QN={quality}, 手动重试={manual_retry})")
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
                logging.error(f"[{worker_name}] 下载线程发生致命错误: {e}", exc_info=True)
                self._report_error(e, bvid, scope='download', message='下载线程发生致命错误')
            finally:
                download_queue.task_done()
                # 下载结束（无论成功失败），清除进度缓存
                if bvid and bvid in progress_cache:
                    del progress_cache[bvid]

    def _download_cover(self, bvid, pic_url):
        # [修复] 只对真正的远程 http(s) 直链下载封面。
        # 历史脏数据里可能存着 `/api/proxy/image?url=...` 这类**自引用**地址
        # （前端曾误把展示用的 formatImg 结果写回数据库），若照单全收会请求自己，
        # 表现为封面全部 404 且日志出现 `https:///api/proxy/image?...`。
        # 这里统一先做一次净化：剥掉代理包装，只保留原始直链。
        from ..core.cover_utils import sanitize_cover_url
        cleaned = sanitize_cover_url(pic_url)
        if not cleaned or not cleaned.startswith("http"):
            # 本地文件名或无法还原的地址：原样返回，不发起请求
            return pic_url

        pic_url = cleaned
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

    # ------------------------------------------------------------
    # 失败残留隔离
    # ------------------------------------------------------------

    def _quarantine_failed_file(self, bvid, file_path):
        """把失败的残留文件移动到隔离区，避免污染下一次重试。"""
        if not self.keep_failed_files:
            return False
        try:
            if not os.path.exists(file_path):
                return False
            os.makedirs(self.failed_path, exist_ok=True)
            target = os.path.join(self.failed_path, f"{bvid}.mp4.incomplete")
            if os.path.exists(target):
                os.remove(target)
            shutil.move(file_path, target)
            logging.info(f"[下载服务] 已隔离未完成的残留文件: {target}")
            return True
        except Exception as e:
            logging.warning(f"[下载服务] 隔离残留文件失败（将直接删除）: {e}")
            try:
                os.remove(file_path)
                return True
            except Exception:
                return False

    def _discard_failed_artifact(self, bvid):
        """手动重试前清理失败的残留（含隔离区）。"""
        removed = []
        for path in (os.path.join(self.download_path, f"{bvid}.mp4"),
                     os.path.join(self.failed_path, f"{bvid}.mp4.incomplete")):
            if os.path.exists(path):
                try:
                    os.remove(path)
                    removed.append(os.path.basename(path))
                except Exception as e:
                    logging.warning(f"[下载服务] 清理残留失败 {path}: {e}")
        if removed:
            logging.info(f"[下载服务] 手动重试前已清理残留: {', '.join(removed)}")

    # ------------------------------------------------------------
    # 错误上报
    # ------------------------------------------------------------

    @staticmethod
    def _report_error(exc, bvid=None, scope='download', message=None, extra=None):
        """把异常上报到错误系统（失败不影响下载流程）。"""
        try:
            from ..core.error_manager import get_error_manager
            context = {'bvid': bvid, 'scope': scope}
            if extra:
                context.update(extra)
            return get_error_manager().report_exception(
                exc,
                scope=scope,
                message=message,
                context=context,
                dedupe_key=f'{scope}:{bvid}' if bvid else None,
            )
        except Exception as e:
            logging.debug(f"[下载服务] 错误上报失败（忽略）: {e}")
            return None

    def _check_disk_space(self, required_bytes=0):
        """下载前检查磁盘空间，空间不足直接给出可修复的错误。"""
        try:
            usage = shutil.disk_usage(self.download_path)
            if usage.free < max(required_bytes, 500 * 1024 * 1024):
                raise OSError(28, 'No space left on device（下载目录所在磁盘可用空间不足）',
                              self.download_path)
        except OSError:
            raise
        except Exception:
            pass

    # ------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------

    def _process_download(self, bvid, quality=80):
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
            retry_count = video.download_retry_count or 0
            video.download_status = 'downloading'
            logging.info(f"[下载开始] bvid={bvid}, title={title}, quality={quality}, "
                         f"已失败次数={retry_count}, 安全输出模式={SAFE_OUTPUT_MODE}")

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

            # [修复] 磁盘空间前置检查，把「写到一半失败」变成可诊断的错误
            self._check_disk_space()

            filename = f"{bvid}.mp4"
            file_path = os.path.join(self.download_path, filename)

            # 检查文件是否已存在且完整
            if os.path.exists(file_path):
                if self._verify_file_integrity(file_path):
                    logging.info(f"文件已存在且完整: {filename}")
                else:
                    logging.warning(f"文件已存在但不完整，重新下载: {filename}")
                    self._quarantine_failed_file(bvid, file_path)
                    self._download_video_file(bvid, file_path, quality)
            else:
                self._download_video_file(bvid, file_path, quality)

            # 下载完成后校验文件
            # [修复] 原实现直接 raise Exception，无法被准确归类；现在交由错误分类器处理
            if not self._verify_file_integrity(file_path):
                raise RuntimeError(f"文件校验失败（下载未完成或文件损坏）: {file_path}")

            # --- 记录下载产生的网络流量 ---
            try:
                file_size = os.path.getsize(file_path)
                from ..database import models
                with get_thread_safe_db_session() as db:
                    # [修复] 统一按本地时间归属日期：stats.py 的 record_play / record_app_usage /
                    # record_network_traffic 三个接口都用 datetime.now() 计算 today，
                    # 而此处原先用 utcnow()。在 UTC+8 等时区，凌晨 0:00-8:00 下载产生的流量
                    # 会被写到「前一天」的行上，导致日统计与排行榜前后不一致。
                    today = datetime.now().strftime('%Y-%m-%d')
                    stat = db.query(models.DailyStat).filter(models.DailyStat.date == today).first()
                    if not stat:
                        stat = models.DailyStat(date=today)
                        db.add(stat)
                    # [修复] 历史行可能因补列而为 NULL，直接 += 会抛 TypeError
                    stat.network_traffic = (stat.network_traffic or 0) + file_size
                    stat.uncached_traffic = (stat.uncached_traffic or 0) + file_size # 下载肯定是未缓存的流量
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
                    except Exception:
                        pass
                return

            # [修复] 归类错误并交给错误系统（弹窗 / 一键修复 / 诊断包）
            from ..core.error_manager import classify_exception
            code = classify_exception(e, {'scope': 'download', 'bvid': bvid})
            record = self._report_error(
                e, bvid, scope='download',
                message=f'下载失败：{title or bvid}',
                extra={'quality': quality, 'attempt': retry_count + 1,
                       'safe_output_mode': SAFE_OUTPUT_MODE},
            )

            logging.error(f"[下载失败] bvid={bvid}, code={code}, error={error_msg}", exc_info=True)

            # [修复] Errno 22 类终端输出异常：立即切换到安全输出模式并自动重试一次，
            # 不再白白消耗用户的重试次数。
            if code == 'DOWNLOAD_CONSOLE_IO' and not SAFE_OUTPUT_MODE:
                enable_safe_output_mode('检测到 Errno 22 终端输出异常')
                with get_thread_safe_db_session() as db:
                    video = db.query(Video).filter(Video.bvid == bvid).first()
                    if video and bvid not in cancelled_tasks:
                        video.download_status = 'pending'
                        download_queue.put((bvid, quality))
                        logging.warning(f"[下载自愈] 已切换安全输出模式并自动重排下载: {bvid}")
                        return

            with get_thread_safe_db_session() as db:
                video = db.query(Video).filter(Video.bvid == bvid).first()
                if video:
                    # 检查是否已被取消，如果是则不重试
                    if video.download_status == 'not_downloaded' or bvid in cancelled_tasks:
                        logging.info(f"[下载取消] 任务已被取消，不重试: {bvid}")
                        video.download_status = 'not_downloaded'
                        cancelled_tasks.discard(bvid)
                        return

                    video.download_retry_count = (video.download_retry_count or 0) + 1

                    # 如果未达到最大重试次数，重新加入队列
                    if video.download_retry_count <= self.max_retries:
                        logging.info(f"将重试下载 ({video.download_retry_count}/{self.max_retries}): {bvid}")
                        video.download_status = 'pending'
                        download_queue.put((bvid, quality))
                    else:
                        logging.error(f"下载失败次数过多，放弃: {bvid}")
                        video.download_status = 'failed'
                        # [新增] 再次上报为「永久失败」，提示用户可一键清零重试计数
                        try:
                            from ..core.error_manager import get_error_manager
                            get_error_manager().report(
                                'DOWNLOAD_PERMANENT',
                                f'{title or bvid} 已达到最大重试次数（{self.max_retries} 次），自动重试已停止',
                                detail=error_msg,
                                context={'bvid': bvid, 'quality': quality,
                                         'traceback': record.traceback if record else ''},
                                dedupe_key=f'download-permanent:{bvid}',
                            )
                        except Exception:
                            pass

    # ------------------------------------------------------------
    # yt-dlp 调用
    # ------------------------------------------------------------

    def _download_video_file(self, bvid_string, output_path, quality=80):
        import tempfile

        is_part = "_p" in bvid_string
        real_bvid, p_num = (bvid_string.split("_p")[0], bvid_string.split("_p")[1]) if is_part else (bvid_string, None)

        # [修复] 收集 yt-dlp 自身报告的失败原因（ignoreerrors=True 时它不会抛异常）
        ydl_errors = []

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
                        # [修复] 进度解析失败绝不能影响下载本身
                        logging.debug(f"[下载服务] 进度解析跳过: {e}")
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

            ydl_opts = build_yt_dlp_options(output_path, progress_hook, error_sink=ydl_errors)
            ydl_opts['format'] = (
                f'bestvideo[height<={max_height}][vcodec^=avc]+bestaudio/'
                f'bestvideo[height<={max_height}]+bestaudio/best'
            )

            # 使用 cookiefile 而不是通过 header 传递 Cookie
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file.name

            # [修复] 分集视频必须把集号写进 URL 的 ?p= 查询串。
            # 原实现只设置 ydl_opts['playlist_items']，但 yt-dlp 的 B 站解析器是从
            # **URL 查询串**读取 part_id 的；且本函数上面已设 noplaylist=True，
            # 解析器不会把选集展开成播放列表，playlist_items 因此始终不生效 ——
            # 结果是下载 BVxxx_p3 时把 P1 的流写进了 BVxxx_p3.mp4，
            # 校验还会通过并被标记为「已完成」，用户永久拿到错误的剧集且不会重下。
            download_url = f"https://www.bilibili.com/video/{real_bvid}"
            if is_part:
                download_url += f"?p={p_num}"
                # playlist_items 对 noplaylist 场景无效，移除以免误导
                ydl_opts.pop('playlist_items', None)

            # [修复 Errno 22] 下载全程隔离标准流的写入异常
            with guarded_standard_streams():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([download_url])

            # [修复] ignoreerrors=True 时 yt-dlp 会「打印错误后正常返回」，
            # 若不在这里检查，下载会被误判为成功，随后才在校验阶段暴露，
            # 且丢失真正的失败原因（Errno 22 之流）。
            if ydl_errors and not self._verify_file_integrity(output_path):
                detail = ydl_errors[-1].strip() or '未知下载错误'
                raise RuntimeError(f'yt-dlp 报告下载失败: {detail}')

        finally:
            # 清理临时 Cookie 文件
            if cookie_file and os.path.exists(cookie_file.name):
                try:
                    os.remove(cookie_file.name)
                except Exception:
                    pass

    # ------------------------------------------------------------
    # 一键修复动作注册
    # ------------------------------------------------------------

    def _register_repairs(self):
        """把可自动修复的错误码注册到错误系统。"""
        try:
            from ..core.error_manager import get_error_manager
            manager = get_error_manager()
            manager.register_repair('DOWNLOAD_CONSOLE_IO', self._repair_console_io)
            manager.register_repair('DOWNLOAD_PARTIAL_FILE', self._repair_partial_file)
            manager.register_repair('DOWNLOAD_FILE_IO', self._repair_file_io)
            manager.register_repair('DOWNLOAD_PERMANENT', self._repair_permanent)
            manager.register_repair('DATABASE_ERROR', self._repair_database)
            manager.register_repair('STORAGE_FULL', self._repair_storage)
            manager.register_repair('DOWNLOAD_UNKNOWN', self._repair_unknown)
        except Exception as e:
            logging.warning(f"[下载服务] 注册一键修复动作失败: {e}")

    def _repair_console_io(self, record):
        """修复终端输出异常：启用安全输出模式 + 重置该媒体重试计数。"""
        enable_safe_output_mode(f'用户一键修复（错误 {record.id}）')
        bvid = record.context.get('bvid')
        detail = '已启用安全输出模式（yt-dlp 终端输出隔离）'
        if bvid:
            self._discard_failed_artifact(bvid)
            reset = self.reset_download_state(bvid)
            detail += f'；已清理残留并清零 {bvid} 的重试计数' if reset else f'；未找到 {bvid} 的下载记录'
        return True, detail

    def _repair_partial_file(self, record):
        """修复文件不完整：删除损坏残留并重置状态。"""
        bvid = record.context.get('bvid')
        if not bvid:
            return False, '错误记录中没有媒体标识，无法自动清理'
        self._discard_failed_artifact(bvid)
        self.reset_download_state(bvid)
        return True, f'已清除 {bvid} 的损坏残留文件并重置下载状态'

    def _repair_file_io(self, record):
        """修复文件读写异常：重建目录 + 清理残留。"""
        try:
            os.makedirs(self.download_path, exist_ok=True)
            os.makedirs(self.covers_path, exist_ok=True)
            os.makedirs(self.failed_path, exist_ok=True)
        except Exception as e:
            return False, f'重建下载目录失败: {e}'
        bvid = record.context.get('bvid')
        if bvid:
            self._discard_failed_artifact(bvid)
            self.reset_download_state(bvid)
        return True, f'已重建下载目录（{self.download_path}）并清理残留'

    def _repair_permanent(self, record):
        """修复永久失败：清零重试计数。"""
        bvid = record.context.get('bvid')
        if not bvid:
            return False, '错误记录中没有媒体标识，无法清零'
        if self.reset_download_state(bvid):
            return True, f'已清零 {bvid} 的重试计数，可重新点击「重试」继续下载'
        return False, f'未找到 {bvid} 的下载记录'

    def _repair_database(self, record):
        """修复数据库异常：执行 WAL 检查点与完整性校验。"""
        try:
            from ..database import db
            from sqlalchemy import text
            with db.engine.connect() as conn:
                integrity = conn.execute(text('PRAGMA integrity_check')).scalar()
                conn.execute(text('PRAGMA wal_checkpoint(TRUNCATE)'))
                conn.commit()
            return True, f'数据库完整性检查结果: {integrity}'
        except Exception as e:
            return False, f'数据库校验失败: {e}'

    def _repair_storage(self, record):
        """修复存储不足：立即执行一次缓存清理。"""
        try:
            from . import cleanup_service
            orphan_removed, before_bytes = cleanup_service.clean_caches()
            usage = shutil.disk_usage(self.download_path)
            return True, (f'已清理缓存（孤立文件 {orphan_removed} 个，清理前缓存 '
                          f'{before_bytes / (1024 ** 3):.2f} GB），当前可用空间 '
                          f'{usage.free / (1024 ** 3):.2f} GB')
        except Exception as e:
            return False, f'清理缓存失败: {e}'

    def _repair_unknown(self, record):
        """兜底修复：重置该媒体的下载状态与重试计数。"""
        bvid = record.context.get('bvid')
        if not bvid:
            return False, '错误记录中没有媒体标识，无法自动修复'
        self._discard_failed_artifact(bvid)
        if self.reset_download_state(bvid):
            return True, f'已重置 {bvid} 的下载状态与重试计数'
        return False, f'未找到 {bvid} 的下载记录'

    def reset_download_state(self, bvid, status='not_downloaded'):
        """把某个媒体的下载状态与重试计数复位（供一键修复使用）。"""
        try:
            with get_thread_safe_db_session() as db:
                updated = db.query(Video).filter(Video.bvid == bvid).update(
                    {'download_status': status, 'download_retry_count': 0},
                    synchronize_session=False)
                db.commit()
            if updated:
                cancelled_tasks.discard(bvid)
                progress_cache.pop(bvid, None)
                logging.info(f"[下载服务] 已重置下载状态: {bvid} -> {status}（重试计数清零）")
            return bool(updated)
        except Exception as e:
            logging.error(f"[下载服务] 重置下载状态失败 {bvid}: {e}")
            return False

    def retry_download(self, bvid, quality=80):
        """用户主动重试：清零计数并重新入队。"""
        return self.add_to_queue(bvid, quality=quality, manual_retry=True)
