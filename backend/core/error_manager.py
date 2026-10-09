# -*- coding: utf-8 -*-
# Path: backend/core/error_manager.py
"""
BiliMusic 错误系统
==================

职责：

1. **结构化错误目录**：为每一类「会导致业务逻辑终止」的错误登记
   「这是什么 / 可能由什么引起 / 可以怎么解决 / 是否需要弹窗」。
2. **错误记录与状态**：错误被记录后进入待处理队列，由 SSE 实时推送给前端弹窗；
   用户可选择「一键修复」「绕过继续」「仅查看」。
3. **诊断包**：收集环境快照 + 最近日志 + 错误详情，打包为 ZIP，
   便于分发给技术客服与开发者。

隐私红线（见 docs/用户协议与隐私政策.md）：诊断包**绝不**包含
Cookie / SESSDATA / bili_jct / 用户媒体库内容 / 播放记录，
所有文本在打包前都会经过脱敏处理。
"""

import io
import os
import re
import sys
import json
import time
import base64
import platform
import logging
import threading
import traceback
import zipfile
from datetime import datetime

logger = logging.getLogger(__name__)

#: 单个错误在内存中保留的上限
MAX_ERROR_RECORDS = 200

#: 诊断包中携带的最近日志条数
DIAG_LOG_LIMIT = 1500

#: 敏感信息脱敏规则（顺序敏感，先长后短）
_SENSITIVE_RULES = (
    (re.compile(r'(SESSDATA|bili_jct|buvid3|buvid4|DedeUserID__ckMd5|sid|access_key|refresh_token)["\']?\s*[:=]\s*["\']?([^"\'\s,;&}]{4,})',
                re.IGNORECASE), r'\1=***REDACTED***'),
    (re.compile(r'(cookie|authorization|token|secret|password|passwd|pwd)\s*[:=]\s*\S+', re.IGNORECASE),
     r'\1=***REDACTED***'),
    (re.compile(r'(?i)(BV[0-9A-Za-z]{10})\b'), r'\1'),
)


def redact(text):
    """对文本做敏感信息脱敏（仅保留结构性信息）。"""
    if text is None:
        return ''
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ''
    out = text
    for pattern, repl in _SENSITIVE_RULES:
        try:
            out = pattern.sub(repl, out)
        except Exception:
            pass
    return out


# ============================================================
# 错误目录
# ============================================================

class ErrorSpec:
    """一类错误的静态描述。"""

    def __init__(self, code, title, summary, causes, solutions,
                 severity='error', popup=True, repairable=False,
                 bypassable=True, repair_label='一键修复',
                 bypass_label='绕过并继续', source='system'):
        self.code = code
        self.title = title
        self.summary = summary
        self.causes = list(causes)
        self.solutions = list(solutions)
        self.severity = severity
        self.popup = popup
        self.repairable = repairable
        self.bypassable = bypassable
        self.repair_label = repair_label
        self.bypass_label = bypass_label
        self.source = source

    def to_dict(self):
        return {
            'code': self.code,
            'title': self.title,
            'summary': self.summary,
            'causes': self.causes,
            'solutions': self.solutions,
            'severity': self.severity,
            'popup': self.popup,
            'repairable': self.repairable,
            'bypassable': self.bypassable,
            'repair_label': self.repair_label,
            'bypass_label': self.bypass_label,
            'source': self.source,
        }


#: 错误目录：key 为错误码
ERROR_CATALOG = {}


def _register(spec: ErrorSpec):
    ERROR_CATALOG[spec.code] = spec
    return spec


# ---- 下载相关 ----

_register(ErrorSpec(
    code='DOWNLOAD_CONSOLE_IO',
    title='下载中断：终端输出异常（Errno 22）',
    summary='yt-dlp 在向不存在的终端句柄输出下载进度时抛出 OSError [Errno 22] Invalid argument，'
            '导致下载被误判为失败并在未完成时退出。该问题与被下载的媒体无关，'
            '但会因为「失败重试计数」被永久消耗而表现为「某个媒体永远下载不了」。',
    causes=[
        '后端进程由 Electron 以隐藏窗口方式启动，标准输出/错误句柄在某些时刻不可写',
        '控制台被重定向、关闭，或 stdout/stderr 的底层文件句柄失效（Windows 上表现为 Errno 22）',
        '多个下载线程同时向同一控制台句柄写入进度条，发生竞争',
        'yt-dlp 的进度渲染未完全禁用，仍在尝试写终端转义序列',
    ],
    solutions=[
        '点击「一键修复」：切换下载器到安全输出模式（彻底禁用 yt-dlp 终端输出），并重置失败媒体的重试计数',
        '修复后重新点击该媒体的「重试」即可继续下载，历史失败不会再次触发',
        '若仍失败，请在设置中把「下载并发线程数」调低为 1 后重启软件',
        '可下载诊断包并反馈给开发者，其中包含完整的 yt-dlp 调用栈与环境信息',
    ],
    repairable=True,
    bypassable=True,
    repair_label='一键修复并重置重试',
    source='download',
))

_register(ErrorSpec(
    code='DOWNLOAD_PARTIAL_FILE',
    title='下载未完成：媒体文件不完整',
    summary='下载流程结束但产出的媒体文件体积异常或容器头缺失，无法正常播放。',
    causes=[
        '下载中途网络中断或被取消',
        'yt-dlp 因进度输出异常提前退出',
        '磁盘空间不足导致写入被截断',
        '上一次下载留下的损坏文件被复用',
    ],
    solutions=[
        '点击「一键修复」：清除该媒体残留的损坏文件并重置下载状态',
        '确认磁盘剩余空间充足（建议至少保留 2GB）',
        '在设置中降低「媒体质量」，避免超高码率流下载失败',
        '若持续失败，可尝试关闭代理/VPN 后重试',
    ],
    repairable=True,
    bypassable=True,
    repair_label='清理损坏文件并重置',
    source='download',
))

_register(ErrorSpec(
    code='DOWNLOAD_NETWORK',
    title='下载失败：网络请求异常',
    summary='与 B 站服务器或 CDN 的网络通信失败，下载任务无法继续。',
    causes=[
        '本机网络中断、DNS 解析失败或使用了不稳定的代理',
        'B 站接口限流（短时间大量请求）',
        'Cookie 已过期，接口返回未登录',
    ],
    solutions=[
        '检查网络连接后重试',
        '在「设置 → 媒体质量」中降低清晰度以减小带宽压力',
        '重新扫码登录以刷新 Cookie',
        '若使用了代理，请确认代理对 B 站 CDN 域名可用',
    ],
    repairable=False,
    bypassable=True,
    repair_label='',
    source='download',
))

_register(ErrorSpec(
    code='DOWNLOAD_FILE_IO',
    title='下载失败：本地文件读写异常',
    summary='无法在下载目录创建或写入媒体文件，下载流程被终止。',
    causes=[
        '下载目录被删除、被移动，或所在磁盘已满',
        '下载目录被其他程序占用（如正在播放该文件）',
        '文件名包含非法字符或路径过长（Windows 260 字符限制）',
        '杀毒软件拦截了对该目录的写入',
    ],
    solutions=[
        '点击「一键修复」：重建下载目录并清理该媒体的残留临时文件',
        '检查磁盘剩余空间与目录权限',
        '把下载目录改到更短的路径（例如 D:\\BiliMusicCache）',
        '将 BiliMusic 加入杀毒软件白名单',
    ],
    repairable=True,
    bypassable=True,
    repair_label='重建目录并清理残留',
    source='download',
))

_register(ErrorSpec(
    code='DOWNLOAD_PERMANENT',
    title='下载失败：该媒体已无法继续重试',
    summary='该媒体的失败重试次数已耗尽，自动重试不会再触发。',
    causes=[
        '媒体本身已被删除、设为私有或存在地区/会员限制',
        '清晰度参数超出账号权限（例如未登录却请求 4K）',
        '该媒体为互动视频/番剧等 yt-dlp 暂不支持的形态',
        '失败重试计数未随「重新下载」重置（历史缺陷，已修复）',
    ],
    solutions=[
        '点击「一键修复」：清零重试计数，让下载可以重新排队',
        '在「设置 → 媒体质量」中降低清晰度后重试',
        '确认账号有权限访问该内容（大会员/付费内容除外）',
        '换一个媒体验证是否为个案',
    ],
    repairable=True,
    bypassable=True,
    repair_label='清零重试计数',
    source='download',
))

# ---- 数据库 / 存储 ----

_register(ErrorSpec(
    code='DATABASE_ERROR',
    title='数据库操作失败',
    summary='本地 SQLite 数据库读写异常，相关业务逻辑无法继续。',
    causes=[
        '数据库文件被其他进程独占（例如同时开了两个 BiliMusic）',
        '磁盘空间不足或数据库文件损坏',
        'WAL 日志文件被误删',
    ],
    solutions=[
        '点击「一键修复」：执行数据库完整性检查与 WAL 重建',
        '关闭重复启动的 BiliMusic 窗口后重试',
        '在「设置 → 数据同步」中导出备份，再重建数据库',
    ],
    repairable=True,
    bypassable=True,
    repair_label='校验并重建数据库连接',
    source='database',
))

_register(ErrorSpec(
    code='STORAGE_FULL',
    title='存储空间不足',
    summary='下载目录所在磁盘可用空间不足，无法继续写入媒体文件。',
    causes=[
        '磁盘剩余空间低于媒体文件体积',
        '缓存上限设置过大，历史缓存未及时清理',
    ],
    solutions=[
        '点击「一键修复」：立即执行一次缓存清理',
        '在「设置」中调低缓存上限（cache_limit_gb）',
        '手动清理下载目录中不再需要的媒体文件',
    ],
    repairable=True,
    bypassable=True,
    repair_label='立即清理缓存',
    source='storage',
))

# ---- 网络 / 登录 ----

_register(ErrorSpec(
    code='NETWORK_ERROR',
    title='网络请求失败',
    summary='后端无法访问外部服务，相关在线功能不可用。',
    causes=[
        '本机断网或 DNS 异常',
        '代理软件拦截了请求',
        '目标服务临时不可用',
    ],
    solutions=[
        '检查网络连接后重试',
        '关闭或调整代理设置',
        '稍后再试（可能是对方服务临时故障）',
    ],
    repairable=False,
    bypassable=True,
    source='network',
))

_register(ErrorSpec(
    code='AUTH_EXPIRED',
    title='登录状态已失效',
    summary='B 站登录凭证已过期，需要重新扫码登录。',
    causes=[
        'Cookie 超过有效期',
        '在其他设备上退出了登录',
        '账号触发了风控',
    ],
    solutions=[
        '在侧边栏重新扫码登录',
        '若反复失效，请检查系统时间是否准确',
        '避免短时间内高频请求接口',
    ],
    repairable=False,
    bypassable=True,
    source='auth',
))

# ---- 通用兜底 ----

_register(ErrorSpec(
    code='DOWNLOAD_UNKNOWN',
    title='下载失败：未知错误',
    summary='下载过程中出现了未被分类的异常，业务逻辑已被终止。',
    causes=[
        'yt-dlp 版本与 B 站接口不兼容',
        '媒体本身不可下载（已删除/受限）',
        '依赖组件缺失（ffmpeg 等）',
        '其它未预期的运行时异常',
    ],
    solutions=[
        '点击「一键修复」：重置该媒体的下载状态与重试计数',
        '下载诊断包并反馈给开发者，其中包含完整调用栈',
        '尝试降低清晰度或更换媒体复现',
    ],
    repairable=True,
    bypassable=True,
    repair_label='重置该媒体下载状态',
    source='download',
))

_register(ErrorSpec(
    code='UNKNOWN_ERROR',
    title='发生未预期的错误',
    summary='软件在执行该操作时遇到未预期的异常，操作已终止。',
    causes=[
        '代码缺陷或未覆盖的边界情况',
        '运行环境异常（权限、磁盘、依赖缺失）',
        '第三方接口返回了非预期数据',
    ],
    solutions=[
        '重试该操作',
        '重启软件',
        '下载诊断包并反馈给开发者',
    ],
    repairable=False,
    bypassable=True,
    source='system',
))


def get_spec(code):
    """获取错误码对应的描述，未登记则返回通用兜底描述。"""
    spec = ERROR_CATALOG.get(code)
    if spec is None:
        spec = ERROR_CATALOG['UNKNOWN_ERROR']
    return spec


def catalog_as_list():
    """返回错误目录（供前端「错误百科」展示）。"""
    return [spec.to_dict() for spec in ERROR_CATALOG.values()]


# ============================================================
# 错误分类
# ============================================================

def classify_exception(exc, context=None):
    """把异常对象映射到错误码。"""
    context = context or {}
    text = ''
    try:
        text = f'{type(exc).__name__}: {exc}'
        if exc.__cause__ is not None:
            text += f' | cause: {type(exc.__cause__).__name__}: {exc.__cause__}'
        if exc.__context__ is not None:
            text += f' | context: {type(exc.__context__).__name__}: {exc.__context__}'
    except Exception:
        text = str(exc)

    chain = text + '\n' + (context.get('traceback') or '')
    low = chain.lower()

    # 1) 终端输出异常：Errno 22 / write_string / minicurses / OSError on stdout
    if 'errno 22' in low or ('invalid argument' in low and context.get('scope') == 'download'):
        if any(k in low for k in ('minicurses', 'write_string', 'unavailablevideoerror',
                                  'utils\\_utils.py', 'utils/_utils.py', 'line ')):
            return 'DOWNLOAD_CONSOLE_IO'
    if 'minicurses' in low or 'utils\\_utils.py' in low or 'utils/_utils.py' in low:
        return 'DOWNLOAD_CONSOLE_IO'

    # 2) 文件不完整
    if '文件校验失败' in chain or '文件过小' in chain or 'incomplete' in low:
        return 'DOWNLOAD_PARTIAL_FILE'

    # 3) 存储空间
    if 'no space left' in low or 'errno 28' in low or '磁盘空间' in chain:
        return 'STORAGE_FULL'

    # 4) 本地文件读写
    if any(k in low for k in ('errno 13', 'permission denied', '拒绝访问',
                              'errno 2', 'no such file', 'the system cannot find',
                              'filename too long', 'errno 36', 'invalid cross-device')):
        return 'DOWNLOAD_FILE_IO' if context.get('scope') == 'download' else 'STORAGE_FULL'

    # 5) 网络
    if any(k in low for k in ('connection', 'timeout', 'timed out', 'ssl', 'proxy',
                              'temporary failure in name resolution', 'name or service not known',
                              'http error', 'remote end closed', 'connectionreseterror')):
        return 'DOWNLOAD_NETWORK' if context.get('scope') == 'download' else 'NETWORK_ERROR'

    # 6) 权限 / 登录
    if any(k in low for k in ('not logged in', '未登录', '-101', 'cookie', 'csrf')):
        return 'AUTH_EXPIRED'

    # 7) 数据库
    if any(k in low for k in ('sqlalchemy', 'sqlite', 'database is locked', 'operationalerror')):
        return 'DATABASE_ERROR'

    if context.get('scope') == 'download':
        return 'DOWNLOAD_UNKNOWN'
    return 'UNKNOWN_ERROR'


# ============================================================
# 环境快照（用于诊断包）
# ============================================================

def _run_safe(func, default=None):
    try:
        return func()
    except Exception:
        return default


def _get_app_version():
    """读取应用版本号（以前端 package.json 为单一真实来源）。"""
    try:
        from .paths import BASE_DIR
        pkg = os.path.join(BASE_DIR, 'frontend', 'package.json')
        if os.path.exists(pkg):
            with open(pkg, 'r', encoding='utf-8') as f:
                return json.load(f).get('version', 'unknown')
    except Exception:
        pass
    return 'unknown'


def _get_disk_info(path):
    """获取目标路径所在磁盘的容量信息。"""
    def _impl():
        target = path
        while target and not os.path.exists(target):
            parent = os.path.dirname(target)
            if parent == target:
                break
            target = parent
        usage = __import__('shutil').disk_usage(target or os.getcwd())
        return {
            'path': path,
            'total_bytes': usage.total,
            'used_bytes': usage.used,
            'free_bytes': usage.free,
            'free_gb': round(usage.free / (1024 ** 3), 2),
        }
    return _run_safe(_impl, {'path': path, 'error': 'unavailable'})


def _get_download_stats():
    """统计下载目录的文件数量与体积（不读取文件内容）。"""
    def _impl():
        from ..services import cleanup_service
        path = cleanup_service.DOWNLOAD_PATH
        count = 0
        total = 0
        if os.path.isdir(path):
            for name in os.listdir(path):
                fp = os.path.join(path, name)
                if os.path.isfile(fp):
                    count += 1
                    total += os.path.getsize(fp)
        return {'path': path, 'file_count': count, 'total_bytes': total}
    return _run_safe(_impl, {'error': 'unavailable'})


def collect_environment(extra=None):
    """收集环境快照。**不包含**任何凭据或用户数据内容。"""
    def _base():
        return {
            'generated_at': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z'),
            'app_version': _get_app_version(),
            'python_version': sys.version,
            'python_executable': sys.executable,
            'frozen': bool(getattr(sys, 'frozen', False)),
            'platform': platform.platform(),
            'os_name': platform.system(),
            'os_release': platform.release(),
            'os_version': platform.version(),
            'architecture': platform.machine(),
            'processor': platform.processor(),
            'cpu_count': os.cpu_count(),
            'cwd': os.getcwd(),
            'argv': redact(' '.join(sys.argv)),
            'encoding': {
                'stdout': _run_safe(lambda: sys.stdout.encoding if sys.stdout else None),
                'stderr': _run_safe(lambda: sys.stderr.encoding if sys.stderr else None),
                'preferred': _run_safe(lambda: __import__('locale').getpreferredencoding(False)),
                'filesystem': _run_safe(sys.getfilesystemencoding),
            },
            'stream_state': probe_stream_state(),
            'timezone': time.strftime('%Z'),
            'tz_offset_seconds': -time.timezone,
        }
    env = _run_safe(_base, {}) or {}
    env['download_dir'] = _get_download_stats()
    env['disk'] = _run_safe(lambda: _get_disk_info(
        env.get('download_dir', {}).get('path') or os.getcwd()), {})
    env['yt_dlp_version'] = _run_safe(
        lambda: __import__('yt_dlp.version', fromlist=['__version__']).__version__, 'unknown')
    env['dependencies'] = _run_safe(_dependency_versions, {})
    if extra:
        env['extra'] = extra
    return env


def _dependency_versions():
    versions = {}
    for name in ('requests', 'fastapi', 'uvicorn', 'sqlalchemy', 'yt_dlp'):
        try:
            mod = __import__(name)
            versions[name] = getattr(mod, '__version__', 'unknown')
        except Exception:
            versions[name] = 'not-installed'
    return versions


def probe_stream_state():
    """探测标准输出/错误句柄的健康度。

    这是 Errno 22 类问题的关键诊断信息：一旦发现某个流不可写，
    就会自动启用「安全输出模式」。
    """
    state = {}
    for name, stream in (('stdout', sys.stdout), ('stderr', sys.stderr)):
        info = {'present': stream is not None}
        try:
            info['class'] = type(stream).__name__ if stream else None
            info['encoding'] = getattr(stream, 'encoding', None)
            info['closed'] = bool(getattr(stream, 'closed', True)) if stream else True
            try:
                info['fileno'] = stream.fileno() if stream else None
            except Exception as e:
                info['fileno'] = f'error: {e}'
            info['isatty'] = _run_safe(lambda s=stream: bool(s.isatty()) if s else False, False)
            info['writable'] = _probe_writable(stream)
        except Exception as e:
            info['error'] = str(e)
        state[name] = info
    return state


def _probe_writable(stream):
    """真正尝试 flush 一次，判断流是否可写（不写入任何可见内容）。"""
    if stream is None:
        return False
    try:
        stream.flush()
        return True
    except Exception:
        return False


# ============================================================
# 错误记录
# ============================================================

class ErrorRecord:
    """一条待处理 / 已处理的错误记录。"""

    def __init__(self, code, message, detail=None, context=None, exc=None):
        spec = get_spec(code)
        now = time.time()
        self.id = f'ERR-{int(now * 1000)}-{os.urandom(2).hex()}'
        self.code = code
        self.title = spec.title
        self.message = redact(message)
        self.detail = redact(detail or '')
        self.context = context or {}
        self.ts = now
        self.time = datetime.fromtimestamp(now).astimezone().strftime('%Y-%m-%d %H:%M:%S')
        self.severity = spec.severity
        self.status = 'pending'      # pending | resolved | bypassed | viewed
        self.resolution = None
        self.resolved_at = None
        self.traceback = redact((context or {}).get('traceback') or '')
        if exc is not None and not self.traceback:
            try:
                self.traceback = redact(''.join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)))
            except Exception:
                pass
        self.spec = spec

    def to_dict(self, with_spec=True):
        data = {
            'id': self.id,
            'code': self.code,
            'title': self.title,
            'message': self.message,
            'detail': self.detail,
            'time': self.time,
            'ts': self.ts,
            'severity': self.severity,
            'status': self.status,
            'resolution': self.resolution,
            'resolved_at': self.resolved_at,
            'context': self.context,
            'traceback': self.traceback,
        }
        if with_spec:
            data['spec'] = self.spec.to_dict()
        return data


class ErrorManager:
    """错误记录、推送与修复的集中管理。"""

    def __init__(self, capacity=MAX_ERROR_RECORDS):
        self._lock = threading.RLock()
        self._records = []
        self._by_id = {}
        self._capacity = capacity
        self._listeners = []
        self._repair_handlers = {}
        self._suppressed = set()   # 用户选择「不再提示」的错误码

    # ---------- 监听（SSE 推送）----------

    def add_listener(self, callback):
        """注册错误推送回调，返回取消函数。"""
        with self._lock:
            self._listeners.append(callback)

        def _remove():
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)
        return _remove

    def _notify(self, payload):
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(payload)
            except Exception:
                pass

    # ---------- 修复器注册 ----------

    def register_repair(self, code, handler):
        """注册某个错误码的一键修复回调 ``handler(record) -> (ok, message)``。"""
        with self._lock:
            self._repair_handlers[code] = handler

    # ---------- 记录 ----------

    def report(self, code, message, detail=None, context=None, exc=None,
               dedupe_key=None, popup=None, extra=None):
        """记录一条错误并推送给前端。

        :param dedupe_key: 相同去重键的未处理错误会被合并，避免批量下载时刷屏
        :param popup: 是否弹窗，None 表示使用错误目录中的默认值
        """
        context = dict(context or {})
        if extra:
            context.update(extra)
        if exc is not None and 'traceback' not in context:
            try:
                context['traceback'] = ''.join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__))
            except Exception:
                pass
        if dedupe_key:
            context['dedupe_key'] = dedupe_key

        spec = get_spec(code)

        with self._lock:
            # 合并同源的未处理错误
            if dedupe_key:
                existing = self._find_pending_locked(dedupe_key)
                if existing is not None:
                    existing.context['occurrences'] = existing.context.get('occurrences', 1) + 1
                    existing.context['last_message'] = redact(message)
                    return existing

            record = ErrorRecord(code, message, detail=detail, context=context, exc=exc)
            self._records.append(record)
            self._by_id[record.id] = record
            if len(self._records) > self._capacity:
                dropped = self._records.pop(0)
                self._by_id.pop(dropped.id, None)
            should_popup = spec.popup if popup is None else bool(popup)
            suppressed = code in self._suppressed

        try:
            logger.error('[错误系统] %s | %s | %s', record.code, record.title, record.message)
        except Exception:
            pass

        self._notify({
            'type': 'error',
            'error': record.to_dict(),
            'popup': bool(should_popup and not suppressed),
        })
        return record

    def _find_pending_locked(self, dedupe_key):
        for rec in reversed(self._records):
            if rec.status == 'pending' and rec.context.get('dedupe_key') == dedupe_key:
                return rec
        return None

    def report_exception(self, exc, scope=None, message=None, context=None,
                         dedupe_key=None, popup=None):
        """按异常类型自动分类后记录。"""
        ctx = dict(context or {})
        if scope:
            ctx['scope'] = scope
        code = classify_exception(exc, ctx)
        text = message or f'{type(exc).__name__}: {exc}'
        return self.report(code, text, detail=str(exc), context=ctx, exc=exc,
                           dedupe_key=dedupe_key, popup=popup)

    # ---------- 查询 ----------

    def list_errors(self, status=None, limit=100):
        with self._lock:
            items = list(self._records)
        if status:
            allowed = {s.strip() for s in status.split(',') if s.strip()}
            items = [r for r in items if r.status in allowed]
        items.reverse()
        return [r.to_dict() for r in items[:limit]]

    def get(self, error_id):
        with self._lock:
            return self._by_id.get(error_id)

    def pending_count(self):
        with self._lock:
            return len([r for r in self._records if r.status == 'pending'])

    # ---------- 处理 ----------

    def _resolve(self, error_id, status, resolution):
        record = self.get(error_id)
        if record is None:
            return None
        with self._lock:
            record.status = status
            record.resolution = resolution
            record.resolved_at = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
        self._notify({
            'type': 'error_resolved',
            'error_id': record.id,
            'status': status,
            'resolution': resolution,
        })
        return record

    def mark_viewed(self, error_id):
        return self._resolve(error_id, 'viewed', '用户已查看')

    def bypass(self, error_id, note=None):
        """绕过该错误继续业务逻辑。"""
        return self._resolve(error_id, 'bypassed', note or '用户选择绕过该错误')

    def suppress_code(self, code, suppressed=True):
        """设置某错误码是否不再弹窗。"""
        with self._lock:
            if suppressed:
                self._suppressed.add(code)
            else:
                self._suppressed.discard(code)
        return suppressed

    def repair(self, error_id):
        """执行一键修复。

        :return: ``(ok, message, record)``
        """
        record = self.get(error_id)
        if record is None:
            return False, '错误记录不存在或已被清理', None

        with self._lock:
            handler = self._repair_handlers.get(record.code)
        if handler is None:
            spec = get_spec(record.code)
            if spec.repairable:
                return False, '该类错误暂无可用的自动修复动作，请按建议手动处理', record
            return False, '该类错误不支持自动修复，请按建议手动处理', record

        try:
            ok, message = handler(record)
        except Exception as e:
            ok, message = False, f'修复过程本身发生异常: {e}'
            try:
                logger.error('[错误系统] 修复 %s 失败: %s', record.code, e, exc_info=True)
            except Exception:
                pass

        if ok:
            self._resolve(error_id, 'resolved', f'一键修复已执行：{message}')
        return ok, message, record

    # ---------- 诊断包 ----------

    def build_diagnostics(self, error_id=None, include_logs=True, note=None):
        """构建诊断包（ZIP 字节流）。

        内容：
        - ``error.json``        错误详情（若有指定错误）
        - ``environment.json``  环境快照（已脱敏）
        - ``logs/recent.log``   最近日志（已脱敏）
        - ``summary.txt``       人类可读的概要，便于直接粘贴给客服
        """
        from . import log_manager

        buffer = io.BytesIO()
        error_dict = None
        record = self.get(error_id) if error_id else None
        if record is not None:
            error_dict = record.to_dict()

        environment = collect_environment(extra={'note': redact(note) if note else None})

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('environment.json',
                        json.dumps(environment, ensure_ascii=False, indent=2))
            if error_dict is not None:
                zf.writestr('error.json',
                            json.dumps(error_dict, ensure_ascii=False, indent=2))

            if include_logs:
                try:
                    records = log_manager.query_logs(limit=DIAG_LOG_LIMIT, newest_first=False)
                except Exception:
                    records = []
                text = log_manager.render_records_text(records)
                zf.writestr('logs/recent.log', redact(text))
                zf.writestr('logs/records.jsonl', redact(
                    '\n'.join(json.dumps(r, ensure_ascii=False) for r in records)))

            zf.writestr('summary.txt', redact(
                self._render_summary(error_dict, environment)))

            zf.writestr('README.txt', self._render_readme())

        buffer.seek(0)
        return buffer.getvalue(), record

    @staticmethod
    def _render_readme():
        return (
            'BiliMusic 诊断包\n'
            '================\n\n'
            '本压缩包用于向 BiliMusic 开发者或技术客服反馈问题，内容包含：\n'
            '  summary.txt        问题概要（可直接粘贴到聊天窗口）\n'
            '  environment.json   运行环境快照（系统、Python、依赖版本、磁盘占用等）\n'
            '  error.json         本次错误的完整内容与调用栈\n'
            '  logs/recent.log    最近的后台日志（已脱敏）\n'
            '  logs/records.jsonl 结构化日志（便于程序化分析）\n\n'
            '【隐私说明】\n'
            '本诊断包不会包含您的 B 站 Cookie、SESSDATA、账号信息、\n'
            '媒体库内容或播放记录；所有文本在打包前均已执行敏感信息脱敏。\n'
            '本项目不存在任何自动上传行为，诊断包仅保存在您的本机，\n'
            '需要由您手动发送给开发者。\n'
        )

    @staticmethod
    def _render_summary(error_dict, environment):
        lines = []
        lines.append('=' * 68)
        lines.append('BiliMusic 问题诊断摘要')
        lines.append('=' * 68)
        lines.append(f"生成时间   : {environment.get('generated_at', '-')}")
        lines.append(f"软件版本   : {environment.get('app_version', '-')}")
        lines.append(f"系统       : {environment.get('platform', '-')}")
        lines.append(f"Python     : {str(environment.get('python_version', '-')).splitlines()[0]}")
        lines.append(f"yt-dlp     : {environment.get('yt_dlp_version', '-')}")
        lines.append(f"打包运行   : {environment.get('frozen', '-')}")
        disk = environment.get('disk') or {}
        lines.append(f"磁盘剩余   : {disk.get('free_gb', '-')} GB")
        lines.append('')

        if error_dict:
            lines.append('-' * 68)
            lines.append(f"错误编号   : {error_dict.get('id')}")
            lines.append(f"错误码     : {error_dict.get('code')}")
            lines.append(f"错误标题   : {error_dict.get('title')}")
            lines.append(f"发生时间   : {error_dict.get('time')}")
            spec = error_dict.get('spec') or {}
            lines.append('')
            lines.append(f"【这是什么】\n{spec.get('summary', '')}")
            lines.append('')
            lines.append('【可能的原因】')
            for i, cause in enumerate(spec.get('causes', []), 1):
                lines.append(f'  {i}. {cause}')
            lines.append('')
            lines.append('【可以怎么解决】')
            for i, sol in enumerate(spec.get('solutions', []), 1):
                lines.append(f'  {i}. {sol}')
            lines.append('')
            lines.append('【错误原始信息】')
            lines.append(str(error_dict.get('message', '')))
            if error_dict.get('detail'):
                lines.append(f"详情: {error_dict.get('detail')}")
            lines.append('')
            lines.append('【调用栈】')
            lines.append(str(error_dict.get('traceback') or '(无)'))
            lines.append('')

        lines.append('-' * 68)
        lines.append('【流状态探测】（Errno 22 类问题的关键线索）')
        lines.append(json.dumps(environment.get('stream_state', {}), ensure_ascii=False, indent=2))
        lines.append('')
        lines.append('=' * 68)
        return '\n'.join(lines)

    # ---------- 一键修复辅助 ----------

    def report_and_repair_info(self, code):
        spec = get_spec(code)
        return {
            'repairable': spec.repairable,
            'repair_label': spec.repair_label,
            'bypassable': spec.bypassable,
            'bypass_label': spec.bypass_label,
        }


#: 全局单例
error_manager = ErrorManager()


def get_error_manager():
    return error_manager
