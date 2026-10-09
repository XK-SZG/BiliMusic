# -*- coding: utf-8 -*-
# Path: backend/core/log_manager.py
"""
BiliMusic 统一日志系统
======================

设计目标（对应 v1.0.21 日志系统重构）：

1. 时间戳与系统时间严格同步：所有时间均通过 ``datetime.now().astimezone()`` 生成，
   并显式携带 UTC 偏移量，避免出现「从 1970 开始计时」这类时间戳错乱。
2. 物理日志：日志同时写入内存环形缓冲（供界面实时查看）与磁盘文件（供事后分析）。
   磁盘文件按「单文件体积上限 + 文件数量上限 + 总占用上限」三级策略自动轮转与回收。
3. 实时日志：内存缓冲支持按序号增量拉取，前端通过 SSE 实时推送，无需手动刷新。
4. 日志筛选：级别、关键字（包含/排除）、时间区间、记录器名称等条件可任意叠加。
5. 崩溃兜底：写日志过程中的任何异常都被吞掉，绝不让日志系统本身导致业务崩溃。

本模块只依赖标准库，可被任意模块安全导入（包括 error_manager / debug_service）。
"""

import os
import sys
import json
import time
import queue
import shutil
import logging
import platform
import subprocess
import threading
from collections import deque
from datetime import datetime, timedelta

# ============================================================
# 常量与默认策略
# ============================================================

#: 日志格式：本地时间（含 UTC 偏移） - 级别 - [记录器] 消息
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] %(message)s'

#: 时间戳格式，带时区偏移，避免不同机器上出现「时间对不上」的困惑
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

#: 内存环形缓冲默认容量（条）
DEFAULT_MEMORY_CAPACITY = 20000

#: 单文件体积上限默认值（MB）
DEFAULT_MAX_FILE_MB = 5

#: 保留日志文件数量上限默认值
DEFAULT_MAX_FILES = 5

#: 日志总占用上限默认值（MB）
DEFAULT_MAX_TOTAL_MB = 25

#: 心跳/高频噪声日志的识别特征（可被前端一键屏蔽）
#: 除常规轮询外，还包含「登录状态验证」相关的噪声日志
HEARTBEAT_PATTERNS = (
    '[请求]',
    'auth/status',
    'B 站登录验证成功',
    '正在请求 B 站导航接口验证登录状态',
    '已清除 B 站 API 缓存',
    'urllib3.connectionpool',
    'httpx',
    '/download/status',
    '/system/events',
    '/system/logs/stream',
    'clipboard/pending',
)

#: 心跳日志的分类标签：命中即归类，便于界面按类别屏蔽
HEARTBEAT_CATEGORIES = {
    'request': ('[请求]', 'urllib3.connectionpool', 'httpx'),
    'login': ('B 站登录验证成功', '正在请求 B 站导航接口验证登录状态',
              '已清除 B 站 API 缓存', 'auth/status'),
    'polling': ('/download/status', '/system/events', '/system/logs/stream',
                'clipboard/pending'),
}

#: 日志文件主名（当前正在写入的文件）
ACTIVE_LOG_NAME = 'bilimusic.log'

#: 轮转归档文件前缀
ARCHIVE_LOG_PREFIX = 'bilimusic-'


def _safe_import_paths():
    """延迟导入路径模块，避免与 paths.py 形成导入环。"""
    from .paths import DATA_DIR
    return DATA_DIR


def get_log_dir():
    """获取物理日志目录（不存在则创建）。

    开发环境为 ``backend/data/logs``，打包后为 ``<exe目录>/data/logs``。
    由于 ``paths.DATA_DIR`` 已兼容两种环境，这里直接复用。
    """
    log_dir = os.path.join(_safe_import_paths(), 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass
    return log_dir


# ============================================================
# 内存环形缓冲
# ============================================================

class LogRingBuffer:
    """线程安全的日志环形缓冲，支持多条件叠加筛选与增量拉取。"""

    def __init__(self, capacity=DEFAULT_MEMORY_CAPACITY):
        self._capacity = capacity
        self._lock = threading.Lock()
        self._records = deque(maxlen=capacity)
        self._seq = 0

    @property
    def capacity(self):
        return self._capacity

    def append(self, record: dict):
        """写入一条日志记录，返回其自增序号。"""
        with self._lock:
            self._seq += 1
            record['seq'] = self._seq
            self._records.append(record)
            return self._seq

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self):
        with self._lock:
            self._records.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._records)

    def snapshot(self):
        """返回当前全部记录的浅拷贝列表（按时间升序）。"""
        with self._lock:
            return list(self._records)

    def query(self, levels=None, keyword=None, exclude=None, start_time=None,
              end_time=None, logger_contains=None, hide_heartbeat=False,
              heartbeat_categories=None, since_seq=None, limit=1000,
              newest_first=True):
        """多条件叠加筛选日志。

        :param levels: 允许的级别列表，例如 ``['ERROR', 'CRITICAL']``
        :param keyword: 必须包含的关键字（不区分大小写），支持 ``|`` 分隔的多个关键字（任一命中）
        :param exclude: 必须排除的关键字，规则同 ``keyword``
        :param start_time: 起始时间（epoch 秒，含）
        :param end_time: 结束时间（epoch 秒，含）
        :param logger_contains: 记录器名称需包含的子串（不区分大小写）
        :param hide_heartbeat: 是否屏蔽心跳类噪声日志
        :param heartbeat_categories: 需要屏蔽的心跳类别集合，
            取值 ``request``（HTTP 请求）/ ``login``（登录验证）/ ``polling``（前端轮询）。
            为 None 且 ``hide_heartbeat`` 为真时，屏蔽全部类别。
        :param since_seq: 只返回序号大于该值的记录（用于实时增量拉取）
        :param limit: 最多返回条数
        :param newest_first: 是否最新在前
        """
        level_set = {str(x).upper() for x in levels} if levels else None
        keyword_terms = _split_terms(keyword)
        exclude_terms = _split_terms(exclude)
        logger_term = (logger_contains or '').strip().lower()

        blocked_categories = None
        if heartbeat_categories:
            blocked_categories = {str(c).strip().lower() for c in heartbeat_categories
                                  if str(c).strip()}
        elif hide_heartbeat:
            blocked_categories = {'request', 'login', 'polling', '__unknown__'}

        with self._lock:
            records = list(self._records)

        matched = []
        for rec in records:
            if since_seq is not None and rec['seq'] <= since_seq:
                continue
            if level_set and rec['level'] not in level_set:
                continue
            if start_time is not None and rec['ts'] < start_time:
                continue
            if end_time is not None and rec['ts'] > end_time:
                continue
            if logger_term and logger_term not in (rec.get('logger') or '').lower():
                continue

            haystack = rec.get('message') or ''
            if exclude_terms:
                low = haystack.lower()
                if any(term in low for term in exclude_terms):
                    continue
            if keyword_terms:
                low = haystack.lower()
                if not any(term in low for term in keyword_terms):
                    continue
            if blocked_categories:
                if rec.get('heartbeat'):
                    category = rec.get('heartbeat_category') or '__unknown__'
                    if category in blocked_categories or '__unknown__' in blocked_categories:
                        continue
                else:
                    # 兼容旧记录（无 heartbeat 字段）与后加入的模式
                    if is_heartbeat_message(haystack):
                        continue
            matched.append(rec)

        if newest_first:
            matched.reverse()
        if limit and len(matched) > limit:
            matched = matched[:limit]
        return matched


def _split_terms(raw):
    """把 ``a|b|c`` 形式的关键字串拆成小写词表。"""
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        parts = []
        for item in raw:
            parts.extend(str(item).split('|'))
    else:
        parts = str(raw).split('|')
    return [p.strip().lower() for p in parts if p and p.strip()]


def is_heartbeat_message(message: str) -> bool:
    """判断一条日志是否为心跳/高频轮询类噪声。"""
    if not message:
        return False
    return any(pat in message for pat in HEARTBEAT_PATTERNS)


def classify_heartbeat(message: str):
    """返回该日志命中的心跳类别（request / login / polling），未命中返回 None。"""
    if not message:
        return None
    for category, patterns in HEARTBEAT_CATEGORIES.items():
        if any(pat in message for pat in patterns):
            return category
    return None


# ============================================================
# 物理文件写入（按体积轮转 + 数量/占用回收）
# ============================================================

class RotatingSizeFileHandler(logging.Handler):
    """轻量级按体积轮转的文件处理器。

    相比标准库 ``RotatingFileHandler``，本实现额外负责：
    - 归档文件命名可读（``bilimusic-YYYYmmdd-HHMMSS.log``）
    - 按「文件数量上限」与「总占用上限」回收最旧的归档
    - 任何 IO 异常均被吞掉，避免日志系统影响业务流程
    """

    def __init__(self, log_dir, max_file_mb=DEFAULT_MAX_FILE_MB,
                 max_files=DEFAULT_MAX_FILES, max_total_mb=DEFAULT_MAX_TOTAL_MB,
                 encoding='utf-8'):
        super().__init__()
        self.log_dir = log_dir
        self.max_file_bytes = max(1, int(max_file_mb * 1024 * 1024))
        self.max_files = max(1, int(max_files))
        self.max_total_bytes = max(1, int(max_total_mb * 1024 * 1024))
        self.encoding = encoding
        self.active_path = os.path.join(log_dir, ACTIVE_LOG_NAME)
        self._stream = None
        self._lock = threading.RLock()
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except Exception:
            pass

    # ---------- 内部工具 ----------

    def _open_locked(self):
        if self._stream is not None:
            return self._stream
        try:
            self._stream = open(self.active_path, 'a', encoding=self.encoding, errors='replace')
        except Exception:
            self._stream = None
        return self._stream

    def _close_locked(self):
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _rotate_locked(self):
        """把当前文件归档并以时间戳命名，然后触发回收。"""
        self._close_locked()
        try:
            if os.path.exists(self.active_path) and os.path.getsize(self.active_path) > 0:
                stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                archive = os.path.join(self.log_dir, f'{ARCHIVE_LOG_PREFIX}{stamp}.log')
                # 同一秒内重复轮转时追加序号，避免覆盖
                idx = 1
                while os.path.exists(archive):
                    archive = os.path.join(
                        self.log_dir, f'{ARCHIVE_LOG_PREFIX}{stamp}-{idx}.log')
                    idx += 1
                os.replace(self.active_path, archive)
        except Exception:
            pass
        self.enforce_limits()

    def enforce_limits(self):
        """按文件数量上限与总占用上限回收最旧的归档文件。"""
        with self._lock:
            try:
                entries = []
                for name in os.listdir(self.log_dir):
                    if not name.endswith('.log'):
                        continue
                    if name != ACTIVE_LOG_NAME and not name.startswith(ARCHIVE_LOG_PREFIX):
                        continue
                    path = os.path.join(self.log_dir, name)
                    try:
                        entries.append((path, name, os.path.getsize(path), os.path.getmtime(path)))
                    except Exception:
                        continue

                # 正在写入的文件永远最后回收，归档按修改时间升序（最旧在前）
                entries.sort(key=lambda e: (e[1] == ACTIVE_LOG_NAME, e[3]))

                # 1) 文件数量上限
                while len(entries) > self.max_files:
                    path, _, _, _ = entries.pop(0)
                    self._remove_locked(path)

                # 2) 总占用上限（至少保留一个文件）
                total = sum(e[2] for e in entries)
                while total > self.max_total_bytes and len(entries) > 1:
                    path, _, size, _ = entries.pop(0)
                    if self._remove_locked(path):
                        total -= size
            except Exception:
                pass

    def _remove_locked(self, path):
        if os.path.abspath(path) == os.path.abspath(self.active_path):
            return False
        try:
            os.remove(path)
            return True
        except Exception:
            return False

    def stats(self):
        """统计日志目录的占用情况。"""
        result = {
            'log_dir': self.log_dir,
            'file_count': 0,
            'total_bytes': 0,
            'active_file': self.active_path,
            'max_files': self.max_files,
            'max_file_bytes': self.max_file_bytes,
            'max_total_bytes': self.max_total_bytes,
            'files': [],
        }
        try:
            for name in sorted(os.listdir(self.log_dir)):
                if not name.endswith('.log'):
                    continue
                path = os.path.join(self.log_dir, name)
                if not os.path.isfile(path):
                    continue
                try:
                    size = os.path.getsize(path)
                    mtime = os.path.getmtime(path)
                except Exception:
                    continue
                result['file_count'] += 1
                result['total_bytes'] += size
                result['files'].append({
                    'name': name,
                    'size': size,
                    'modified': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'is_active': name == ACTIVE_LOG_NAME,
                })
        except Exception:
            pass
        return result

    # ---------- logging.Handler 接口 ----------

    def emit(self, record):
        try:
            msg = self.format(record) + '\n'
            with self._lock:
                stream = self._open_locked()
                if stream is None:
                    return
                try:
                    if os.path.getsize(self.active_path) >= self.max_file_bytes:
                        self._rotate_locked()
                        stream = self._open_locked()
                        if stream is None:
                            return
                except OSError:
                    pass
                stream.write(msg)
                stream.flush()
        except Exception:
            # 日志系统自身的异常必须吞掉，避免影响业务
            pass

    def close(self):
        with self._lock:
            self._close_locked()
        super().close()


# ============================================================
# logging 处理器
# ============================================================

class MemoryLogHandler(logging.Handler):
    """把日志写入内存环形缓冲（供界面实时查看与筛选）。"""

    def __init__(self, capacity=DEFAULT_MEMORY_CAPACITY):
        super().__init__()
        self.buffer = LogRingBuffer(capacity)

    # 兼容旧接口
    @property
    def capacity(self):
        return self.buffer.capacity

    @property
    def logs(self):
        return self.buffer.snapshot()

    def emit(self, record):
        try:
            entry = {
                'ts': record.created,
                'time': format_record_time(record.created),
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record),
                'heartbeat': False,
                'heartbeat_category': None,
            }
            category = classify_heartbeat(entry['message'])
            entry['heartbeat'] = category is not None
            entry['heartbeat_category'] = category
            self.buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_logs(self):
        """兼容旧接口：返回全部日志（按时间升序）。"""
        return self.buffer.snapshot()


def format_record_time(ts):
    """把 epoch 秒格式化为带时区偏移的本地时间字符串。"""
    try:
        return datetime.fromtimestamp(ts).astimezone().strftime(TIMESTAMP_FORMAT)
    except Exception:
        return datetime.now().strftime(TIMESTAMP_FORMAT)


# ============================================================
# 全局单例与装配
# ============================================================

memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=TIMESTAMP_FORMAT))

file_handler = None
_logger_lock = threading.RLock()
_initialized = False
_config_snapshot = {}
_cleaner_thread = None
_cleaner_stop = threading.Event()


def _read_log_config():
    """从 config.yaml 读取日志配置（失败则使用默认值）。"""
    from .utils import as_bool
    cfg = {
        'memory_capacity': DEFAULT_MEMORY_CAPACITY,
        'max_file_mb': DEFAULT_MAX_FILE_MB,
        'max_files': DEFAULT_MAX_FILES,
        'max_total_mb': DEFAULT_MAX_TOTAL_MB,
        'console': True,
        'file_enabled': True,
        'level': 'DEBUG',
    }
    try:
        from .config import get_config
        config = get_config()
        cfg['memory_capacity'] = int(config.get('logging.memory_capacity', DEFAULT_MEMORY_CAPACITY))
        cfg['max_file_mb'] = float(config.get('logging.max_file_mb', DEFAULT_MAX_FILE_MB))
        cfg['max_files'] = int(config.get('logging.max_files', DEFAULT_MAX_FILES))
        cfg['max_total_mb'] = float(config.get('logging.max_total_mb', DEFAULT_MAX_TOTAL_MB))
        cfg['console'] = as_bool(config.get('logging.console', True), True)
        cfg['file_enabled'] = as_bool(config.get('logging.file_enabled', True), True)
        cfg['level'] = str(config.get('logging.level', 'DEBUG')).upper()
    except Exception:
        pass
    return cfg


def setup_logging(level=None, force=False):
    """装配全局日志系统（幂等）。

    必须在任何可能失败的导入之前调用；任何异常都不会向外抛出。
    """
    global file_handler, _initialized, _config_snapshot
    with _logger_lock:
        if _initialized and not force:
            return
        try:
            cfg = _read_log_config()
            _config_snapshot = cfg

            root = logging.getLogger()
            resolved_level = getattr(
                logging, (level or cfg['level']).upper() if (level or cfg['level']) else 'DEBUG',
                logging.DEBUG)
            root.setLevel(resolved_level)

            # --- 内存处理器 ---
            if memory_handler not in root.handlers:
                root.addHandler(memory_handler)
            if memory_handler.buffer.capacity != cfg['memory_capacity']:
                memory_handler.buffer = LogRingBuffer(cfg['memory_capacity'])

            # --- 控制台处理器（Electron 主进程日志 / 开发终端）---
            if cfg['console']:
                has_stream = any(
                    isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                    for h in root.handlers)
                if not has_stream and sys.stderr is not None:
                    try:
                        stream_handler = logging.StreamHandler(sys.stderr)
                        stream_handler.setFormatter(
                            logging.Formatter(LOG_FORMAT, datefmt=TIMESTAMP_FORMAT))
                        root.addHandler(stream_handler)
                    except Exception:
                        pass

            # --- 物理文件处理器 ---
            if cfg['file_enabled']:
                if file_handler is None:
                    file_handler = RotatingSizeFileHandler(
                        get_log_dir(),
                        max_file_mb=cfg['max_file_mb'],
                        max_files=cfg['max_files'],
                        max_total_mb=cfg['max_total_mb'],
                    )
                    file_handler.setFormatter(
                        logging.Formatter(LOG_FORMAT, datefmt=TIMESTAMP_FORMAT))
                if file_handler not in root.handlers:
                    root.addHandler(file_handler)
                _start_cleaner()

            # uvicorn / fastapi 的访问日志过于嘈杂，统一收敛到 WARNING
            for noisy in ('uvicorn.access', 'watchfiles', 'python_multipart'):
                logging.getLogger(noisy).setLevel(logging.WARNING)
            # httpx / urllib3 会把每一次 HTTP 请求都记为 INFO，属于典型噪声，
            # 收敛到 DEBUG 后仍可通过界面的「全部级别」查看
            for noisy in ('httpx', 'httpcore'):
                logging.getLogger(noisy).setLevel(logging.DEBUG)

            _initialized = True
        except Exception:
            # 日志系统装配失败绝不能阻断启动
            pass


def _start_cleaner():
    """启动后台清理线程（周期性执行体积/数量回收）。"""
    global _cleaner_thread
    if _cleaner_thread is not None and _cleaner_thread.is_alive():
        return

    def _loop():
        while not _cleaner_stop.wait(60):
            try:
                if file_handler is not None:
                    file_handler.enforce_limits()
            except Exception:
                pass

    _cleaner_thread = threading.Thread(target=_loop, name='LogCleanerThread', daemon=True)
    _cleaner_thread.start()


def get_logger(name):
    """获取标准库 logger（统一入口，便于后续替换实现）。"""
    return logging.getLogger(name)


# ============================================================
# 对外查询 / 管理接口
# ============================================================

def query_logs(**kwargs):
    """按条件查询内存日志。"""
    return memory_handler.buffer.query(**kwargs)


def latest_seq():
    return memory_handler.buffer.latest_seq()


def clear_memory_logs():
    memory_handler.buffer.clear()


def get_log_stats():
    """汇总日志系统状态，供界面展示与控制。"""
    buffer = memory_handler.buffer
    stats = {
        'memory_count': buffer.size(),
        'memory_capacity': buffer.capacity,
        'latest_seq': buffer.latest_seq(),
        'limited': buffer.size() >= buffer.capacity,
        'level': logging.getLevelName(logging.getLogger().level),
        'format': LOG_FORMAT,
        'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z'),
        'timezone': time.strftime('%Z'),
    }
    if file_handler is not None:
        stats.update(file_handler.stats())
    else:
        stats.setdefault('log_dir', get_log_dir())
        stats.setdefault('file_count', 0)
        stats.setdefault('total_bytes', 0)
        stats.setdefault('max_files', DEFAULT_MAX_FILES)
        stats.setdefault('max_file_bytes', DEFAULT_MAX_FILE_MB * 1024 * 1024)
        stats.setdefault('max_total_bytes', DEFAULT_MAX_TOTAL_MB * 1024 * 1024)
    return stats


def update_retention(max_files=None, max_file_mb=None, max_total_mb=None):
    """运行时调整日志保留策略并立即回收。"""
    if file_handler is None:
        return get_log_stats()
    with file_handler._lock:  # noqa: SLF001 - 同模块内的受控访问
        if max_files is not None:
            file_handler.max_files = max(1, int(max_files))
        if max_file_mb is not None:
            file_handler.max_file_bytes = max(1, int(float(max_file_mb) * 1024 * 1024))
        if max_total_mb is not None:
            file_handler.max_total_bytes = max(1, int(float(max_total_mb) * 1024 * 1024))
    file_handler.enforce_limits()
    return get_log_stats()


def purge_log_files(include_active=False):
    """删除物理日志文件。

    :param include_active: 为 True 时同时清空当前正在写入的日志文件
    :return: 删除的文件数量
    """
    removed = 0
    log_dir = get_log_dir()
    try:
        for name in os.listdir(log_dir):
            if not name.endswith('.log'):
                continue
            if name == ACTIVE_LOG_NAME and not include_active:
                continue
            path = os.path.join(log_dir, name)
            if not os.path.isfile(path):
                continue
            if name == ACTIVE_LOG_NAME and file_handler is not None:
                # 正在写入的文件需要先关闭句柄
                with file_handler._lock:  # noqa: SLF001
                    file_handler._close_locked()
                    try:
                        os.remove(path)
                        removed += 1
                    except Exception:
                        pass
                continue
            try:
                os.remove(path)
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


def open_log_dir():
    """在系统文件管理器中打开物理日志目录。

    [修复] 原实现只调用一次 ``os.startfile``，一旦失败就直接抛错。
    实测在「后端由 Electron 以隐藏窗口方式启动」的场景下，
    ``os.startfile`` 会抛出 ``PermissionError: [WinError 5] 拒绝访问``。
    现在改为多路径回退，并把每次失败的原因记录下来，便于诊断。

    :return: ``(ok, detail)``；``ok`` 为 False 时 ``detail`` 是失败原因汇总
    """
    log_dir = get_log_dir()
    system = platform.system()

    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            return False, f'日志目录不存在且无法创建: {log_dir} ({e})'

    # Windows 上 explorer.exe 需要反斜杠路径；其他平台用原始路径
    native_dir = os.path.normpath(log_dir) if system == 'Windows' else log_dir

    attempts = []

    if system == 'Windows':
        # 路径 1：ShellExecuteW（等价于双击目录，最“正规”的方式）
        try:
            import ctypes
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 'open', native_dir, None, None, 1)
            if int(result) > 32:
                return True, native_dir
            attempts.append(f'ShellExecuteW 返回码 {int(result)}')
        except Exception as e:
            attempts.append(f'ShellExecuteW: {e}')

        # 路径 2：os.startfile
        try:
            os.startfile(native_dir)  # type: ignore[attr-defined]
            return True, native_dir
        except Exception as e:
            attempts.append(f'os.startfile: {e}')

        # 路径 3：explorer.exe
        try:
            subprocess.Popen(['explorer.exe', native_dir], close_fds=True)
            return True, native_dir
        except Exception as e:
            attempts.append(f'explorer.exe: {e}')

        # 路径 4：explorer.exe /select,（explorer 的容错路径写法）
        try:
            subprocess.Popen(f'explorer.exe /select,"{native_dir}"', shell=True,
                             close_fds=True)
            return True, native_dir
        except Exception as e:
            attempts.append(f'explorer /select: {e}')
    else:
        opener = 'open' if system == 'Darwin' else 'xdg-open'
        try:
            subprocess.Popen([opener, native_dir], close_fds=True)
            return True, native_dir
        except Exception as e:
            attempts.append(f'{opener}: {e}')

    detail = f'无法打开目录 {native_dir}；尝试记录：' + ' | '.join(attempts)
    try:
        logging.getLogger(__name__).warning(f'[日志系统] {detail}')
    except Exception:
        pass
    return False, detail


def render_records_text(records):
    """把日志记录渲染为可复制的纯文本。"""
    lines = []
    for rec in records:
        lines.append(f"[{rec.get('time', '')}] {rec.get('level', ''):<8} [{rec.get('logger', '')}] {rec.get('message', '')}")
    return '\n'.join(lines)


def export_records(records, fmt='txt'):
    """把日志记录导出为字节内容，供下载。"""
    if fmt == 'json':
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        return payload.encode('utf-8')
    if fmt == 'jsonl':
        payload = '\n'.join(json.dumps(r, ensure_ascii=False) for r in records)
        return payload.encode('utf-8')
    return render_records_text(records).encode('utf-8')


def read_file_tail(filename, max_bytes=512 * 1024):
    """读取物理日志文件的尾部内容（用于查看归档文件）。"""
    log_dir = os.path.abspath(get_log_dir())
    target = os.path.abspath(os.path.join(log_dir, filename))
    if not target.startswith(log_dir):
        raise ValueError('非法的日志文件名')
    if not os.path.isfile(target):
        raise FileNotFoundError(filename)
    size = os.path.getsize(target)
    with open(target, 'rb') as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    return data.decode('utf-8', errors='replace')


# 兼容旧调用名（backend/main.py 历史实现）
def setup_memory_logger():
    """兼容旧接口：装配日志系统。"""
    setup_logging()


def install_excepthook():
    """安装全局未捕获异常钩子，把崩溃栈完整写入日志。"""
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        try:
            logging.getLogger('backend.crash').critical(
                '未捕获异常导致进程异常', exc_info=(exc_type, exc_value, exc_tb))
        except Exception:
            pass

    def _thread_hook(args):
        try:
            logging.getLogger('backend.crash').critical(
                '子线程未捕获异常: %s', args.thread.name if args.thread else 'unknown',
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        except Exception:
            pass

    try:
        sys.excepthook = _hook
    except Exception:
        pass
    try:
        if hasattr(threading, 'excepthook'):
            threading.excepthook = _thread_hook
    except Exception:
        pass
