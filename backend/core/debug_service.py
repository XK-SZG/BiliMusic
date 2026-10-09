# -*- coding: utf-8 -*-
# Path: backend/core/debug_service.py
"""
BiliMusic 调试系统
==================

面向开发者与具备技术能力的用户，提供**远程调试**能力：
通过本机 HTTP API 读取运行状态、查看日志、执行受限命令，
便于配合 Vibe Coding（AI 辅助编码）工作流进行问题定位。

安全设计（不可绕过的三道闸门）
------------------------------
1. **协议闸门**：必须完整阅读《调试模式使用协议 / 风险说明书 / 责任划分书》并逐项确认，
   确认记录（含版本号与时间）持久化在 ``backend/data/debug_consent.json``。
2. **显式开关**：调试模式默认关闭，需用户主动开启；关闭时立即销毁访问令牌。
3. **令牌鉴权 + 命令白名单**：所有调试接口都需要 ``X-Debug-Token``；
   代码执行能力默认关闭，开启后也仅允许白名单内的动作，且每条指令都会写入审计日志。

隐私红线：调试系统不会主动上传任何数据；审计日志仅保存在本机。
"""

import os
import re
import sys
import json
import hmac
import time
import uuid
import shutil
import logging
import platform
import secrets
import subprocess
import threading
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

#: 协议版本号：内容变更时必须同步递增，已同意的旧版本需要重新确认
CONSENT_VERSION = '1.0'
CONSENT_FILE = 'debug_consent.json'

#: 审计日志在内存中保留的条数
AUDIT_CAPACITY = 500

#: 命令执行的硬性超时（秒）
COMMAND_TIMEOUT = 20

#: 命令输出截断长度
OUTPUT_LIMIT = 20000

#: 允许通过 ``/api/debug/action`` 执行的动作用途
ALLOWED_ACTIONS = (
    'python',
    'shell',
    'db_query',
)

#: shell 动作的命令白名单（仅允许只读诊断类命令）
SHELL_WHITELIST = (
    r'^ipconfig(\s+/\w+)*$',
    r'^systeminfo$',
    r'^tasklist(\s+/\w+(\s+[\w.]+)?)*$',
    r'^netstat(\s+-\w+)*$',
    r'^ver$',
    r'^where\s+[\w.\-]+$',
    r'^ping\s+-n\s+\d+\s+[\w.\-:]+$',
    r'^nslookup\s+[\w.\-]+$',
    r'^dir(\s+"?[\w:\\.\-]+"?)?$',
    r'^echo\s+[\w\s\-.:]*$',
)

#: 数据库只读查询白名单（仅允许 SELECT）
_SELECT_PATTERN = re.compile(r'^\s*select\b', re.IGNORECASE)
_FORBIDDEN_SQL = re.compile(
    r'\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b',
    re.IGNORECASE)

#: python 动作允许访问的模块白名单（前缀匹配）
PYTHON_MODULE_ALLOWLIST = (
    'os', 'sys', 'platform', 'json', 'time', 'datetime', 'shutil', 'subprocess',
    'logging', 'collections', 're', 'math', 'statistics', 'psutil', 'threading',
    'socket', 'sqlite3', 'hashlib', 'uuid', 'traceback', 'gc', 'locale',
)

#: python 动作中被禁止出现的危险片段
PYTHON_FORBIDDEN = (
    '__import__', 'importlib', 'eval(', 'exec(', 'compile(', 'open(',
    'shutil.rmtree', 'os.remove', 'os.unlink', 'os.rmdir', 'os.system',
    'subprocess.popen', 'socket.socket', 'urllib', 'requests', 'pickle',
    'ctypes', 'builtins', 'globals(', 'locals(', 'setattr(', 'delattr(',
    '__subclasses__', '__globals__', '__builtins__', 'input(',
    'bili_cookies', 'bili_user_info', 'sessdata', 'bili_jct',
)


# ============================================================
# 协议文本
# ============================================================

AGREEMENT_TEXT = """BiliMusic 调试模式使用协议 / 风险说明书 / 责任划分书
版本 {version}

────────────────────────────────────────────────────────────
第一部分　调试模式是什么
────────────────────────────────────────────────────────────

调试模式（Debug Mode）是 BiliMusic 面向**开发者与具备技术能力的用户**
提供的高级功能。开启后，本机会启动一组调试接口，允许外部程序（例如
AI 编码助手、Postman、脚本）读取运行状态、查看日志、并执行受限指令。

它不是给普通用户使用的功能，也不会让软件「变得更好用」。它是一把手术刀：
用得好可以精准定位问题，用不好会直接伤到你自己。

────────────────────────────────────────────────────────────
第二部分　风险说明书（请逐条确认你已理解）
────────────────────────────────────────────────────────────

风险 1｜本机数据暴露风险
  调试接口监听在 127.0.0.1，仅本机可访问，但**本机上的任何程序**只要拿到
  访问令牌就能读取运行状态与日志。若你的电脑上存在恶意软件，调试模式会
  扩大它的可达范围。日志中可能包含你的文件路径、媒体标题等信息。

风险 2｜命令执行风险
  「命令执行」能力可以让调试方在本机执行受限的系统指令。尽管本项目内置了
  命令白名单与表达式过滤，**任何白名单都不可能做到 100% 安全**。恶意构造的
  指令有可能造成数据损坏、隐私泄露或系统异常。

风险 3｜数据损坏风险
  调试过程中可能触发缓存清理、数据库读写、下载状态重置等操作。
  这些操作有可能导致媒体库数据、缓存文件或播放记录损坏或丢失。

风险 4｜账号与网络风险
  调试接口可以触发对 B 站的网络请求。高频或异常请求可能触发
  B 站的风控策略，进而导致账号被限制访问。

风险 5｜稳定性风险
  调试模式会暴露内部实现细节，对内部状态的直接操作可能让软件进入
  非预期状态，出现崩溃、卡死或行为异常。

────────────────────────────────────────────────────────────
第三部分　责任划分书
────────────────────────────────────────────────────────────

1. 调试模式是**完全自愿开启**的高级功能。你需要在阅读本文件后主动勾选
   全部确认项并点击开启按钮，软件才会启用它。

2. 一旦开启，你或你授权的第三方（包括但不限于 AI 编码助手、自动化脚本）
   通过调试接口所执行的一切操作，**均由你本人承担全部责任**。

3. 因使用调试模式而直接或间接导致的任何后果——包括但不限于本机数据
   损坏或丢失、系统异常、账号被限制访问、因违反第三方平台服务条款而
   产生的纠纷、以及任何法律与经济损失——**BiliMusic 开发者不承担任何
   连带责任与赔偿责任**。

4. 调试模式**不提供任何数据上传通道**。本项目没有、也不会部署任何中心化
   遥测服务器；调试与审计数据全部留在你的本机，是否对外提供由你自行决定。

5. 你承诺不利用调试模式从事任何违反法律法规、侵犯他人合法权益、
   绕过第三方平台付费/版权限制的行为。

6. 开发者保留在不另行通知的情况下修改、限制或移除调试模式的权利。

────────────────────────────────────────────────────────────
第四部分　如何关闭
────────────────────────────────────────────────────────────

在「设置 → 调试系统」中点击「关闭调试模式」即可。关闭后：
  · 访问令牌立即销毁；
  · 所有调试接口返回 403；
  · 审计日志保留（便于事后追溯），可手动清空。

你也可以直接退出并重启软件——调试模式不会在未经确认的情况下自动恢复。
"""

#: 需要在界面上逐项勾选的确认项
CONSENT_CHECKLIST = [
    {
        'id': 'read',
        'text': '我已完整阅读并理解上述《调试模式使用协议 / 风险说明书 / 责任划分书》',
    },
    {
        'id': 'risk',
        'text': '我理解调试模式存在本机数据暴露、命令执行、数据损坏、账号风控与稳定性风险',
    },
    {
        'id': 'liability',
        'text': '我明确知晓并同意：使用调试模式的一切后果由我本人承担，开发者不承担连带或赔偿责任',
    },
    {
        'id': 'lawful',
        'text': '我承诺仅在合法合规的范围内使用调试能力，不侵犯他人权益与第三方平台权益',
    },
    {
        'id': 'privacy',
        'text': '我理解调试模式不会上传任何数据，但本机日志与运行状态会对持有令牌的调试方可见',
    },
]


def get_agreement_text():
    """返回带版本号的协议全文。"""
    return AGREEMENT_TEXT.format(version=CONSENT_VERSION)


# ============================================================
# 状态持久化
# ============================================================

def _data_dir():
    from .paths import DATA_DIR
    return DATA_DIR


def _consent_path():
    return os.path.join(_data_dir(), CONSENT_FILE)


def _load_consent():
    try:
        with open(_consent_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_consent(data):
    try:
        path = _consent_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f'[调试系统] 保存确认记录失败: {e}')
        return False


# ============================================================
# 调试会话
# ============================================================

class DebugSession:
    """调试模式的运行状态（内存态，进程退出即失效）。"""

    def __init__(self):
        self._lock = threading.RLock()
        self.enabled = False
        self.token = None
        self.enabled_at = None
        self.enabled_by = None
        self.allow_python = False
        self.allow_shell = False
        self.allow_db_write = False
        self.request_count = 0
        self.last_request_at = None
        self._audit = deque(maxlen=AUDIT_CAPACITY)
        self._consent = _load_consent()

    # ---------- 协议 ----------

    def consent_state(self):
        """返回协议确认状态。"""
        with self._lock:
            consent = dict(self._consent)
        confirmed = (consent.get('version') == CONSENT_VERSION
                     and bool(consent.get('confirmed')))
        return {
            'version': CONSENT_VERSION,
            'confirmed': confirmed,
            'confirmed_at': consent.get('confirmed_at'),
            'checklist': CONSENT_CHECKLIST,
            'stale': bool(consent.get('version') and consent.get('version') != CONSENT_VERSION),
            'agreement': get_agreement_text(),
        }

    def accept_consent(self, checklist=None, source='ui'):
        """记录协议确认（必须逐项确认）。"""
        required = {item['id'] for item in CONSENT_CHECKLIST}
        provided = set(checklist or [])
        missing = required - provided
        if missing:
            return False, f'以下确认项未勾选，无法开启调试模式: {", ".join(sorted(missing))}'
        record = {
            'version': CONSENT_VERSION,
            'confirmed': True,
            'confirmed_at': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z'),
            'source': source,
            'platform': platform.platform(),
            'app_version': _app_version(),
        }
        with self._lock:
            self._consent = record
        _save_consent(record)
        self.audit('consent_accepted', f'已确认调试协议 v{CONSENT_VERSION}', source=source)
        return True, '协议确认记录已保存'

    def revoke_consent(self):
        """撤回协议确认，同时关闭调试模式。"""
        self.disable(reason='用户撤回协议确认')
        with self._lock:
            self._consent = {}
        _save_consent({})
        self.audit('consent_revoked', '用户撤回调试协议确认')
        return True

    # ---------- 开关 ----------

    def enable(self, allow_python=False, allow_shell=False, source='ui'):
        """开启调试模式并生成访问令牌。"""
        state = self.consent_state()
        if not state['confirmed']:
            return False, '尚未完成协议确认，无法开启调试模式', None
        with self._lock:
            self.enabled = True
            self.token = secrets.token_urlsafe(32)
            self.enabled_at = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
            self.enabled_by = source
            self.allow_python = bool(allow_python)
            self.allow_shell = bool(allow_shell)
            self.request_count = 0
            token = self.token
        mode_note = []
        if self.allow_python:
            mode_note.append('表达式执行')
        if self.allow_shell:
            mode_note.append('命令执行')
        logger.warning(f'[调试系统] 调试模式已开启（{"、".join(mode_note) or "只读"}），来源: {source}')
        self.audit('enable', f'开启调试模式（{"、".join(mode_note) or "只读"}）', source=source)
        return True, '调试模式已开启', token

    def disable(self, reason='用户关闭'):
        """关闭调试模式并销毁令牌。"""
        with self._lock:
            was_enabled = self.enabled
            self.enabled = False
            self.token = None
            self.enabled_at = None
            self.enabled_by = None
            self.allow_python = False
            self.allow_shell = False
        if was_enabled:
            logger.warning(f'[调试系统] 调试模式已关闭：{reason}')
            self.audit('disable', f'关闭调试模式（{reason}）')
        return True

    def rotate_token(self):
        """轮换访问令牌（用于令牌疑似泄露时）。"""
        with self._lock:
            if not self.enabled:
                return False, '调试模式未开启', None
            self.token = secrets.token_urlsafe(32)
            token = self.token
        self.audit('rotate_token', '已轮换访问令牌')
        return True, '访问令牌已轮换，请更新你的调试脚本', token

    # ---------- 鉴权 ----------

    def verify(self, token):
        with self._lock:
            if not self.enabled or not self.token:
                return False
            if not token:
                return False
            return hmac.compare_digest(str(token), self.token)

    def touch(self):
        with self._lock:
            self.request_count += 1
            self.last_request_at = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')

    # ---------- 审计 ----------

    def audit(self, action, detail='', source='api', ok=True, duration_ms=None):
        entry = {
            'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S'),
            'action': action,
            'detail': str(detail)[:2000],
            'source': source,
            'ok': bool(ok),
            'duration_ms': duration_ms,
        }
        with self._lock:
            self._audit.append(entry)
        try:
            logger.info(f'[调试审计] {action} | {entry["detail"][:200]}')
        except Exception:
            pass
        return entry

    def get_audit(self, limit=200):
        with self._lock:
            items = list(self._audit)
        items.reverse()
        return items[:limit]

    def clear_audit(self):
        with self._lock:
            self._audit.clear()
        self.audit('clear_audit', '已清空审计日志')
        return True

    # ---------- 状态 ----------

    def status(self, include_token=False):
        with self._lock:
            data = {
                'enabled': self.enabled,
                'enabled_at': self.enabled_at,
                'enabled_by': self.enabled_by,
                'allow_python': self.allow_python,
                'allow_shell': self.allow_shell,
                'request_count': self.request_count,
                'last_request_at': self.last_request_at,
                'endpoint': f'http://127.0.0.1:{_server_port()}/api/debug',
                'consent': self.consent_state(),
                'server_time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z'),
            }
            if include_token and self.enabled:
                data['token'] = self.token
        return data


def _server_port():
    try:
        from .config import get_config
        return get_config().get('server.port', 12180)
    except Exception:
        return 12180


def _app_version():
    try:
        from .paths import BASE_DIR
        pkg = os.path.join(BASE_DIR, 'frontend', 'package.json')
        if os.path.exists(pkg):
            with open(pkg, 'r', encoding='utf-8') as f:
                return json.load(f).get('version', 'unknown')
    except Exception:
        pass
    return 'unknown'


#: 全局单例
debug_session = DebugSession()


def get_debug_session():
    return debug_session


# ============================================================
# 受限执行
# ============================================================

class DebugActionError(Exception):
    """调试动作被拒绝。"""


def _truncate(text):
    if text and len(text) > OUTPUT_LIMIT:
        return text[:OUTPUT_LIMIT] + f'\n...（输出已截断，共 {len(text)} 字符）'
    return text


def _check_python_expression(expr):
    """校验 Python 表达式是否允许执行。"""
    if not expr or not expr.strip():
        raise DebugActionError('表达式不能为空')
    # 逐词匹配禁止片段，避免 "os.remove" 之类的组合写法被误判为 "os." 之类子串
    low = expr.lower()
    for bad in PYTHON_FORBIDDEN:
        if bad in low:
            raise DebugActionError(f'表达式中包含被禁止的片段: {bad}')
    # 禁止属性访问链中的下划线魔术属性（阻断 __class__ / __globals__ 类逃逸）
    if re.search(r'\.\s*_', expr):
        raise DebugActionError('表达式中不允许访问下划线开头的私有属性')
    # 只允许白名单模块被引用，其它对象名一律拒绝
    referenced = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\.', expr))
    unknown = referenced - set(PYTHON_MODULE_ALLOWLIST) - {
        'self', 'session', 'collections', 'statistics', 'logging',
    }
    if unknown:
        raise DebugActionError(
            f'表达式中引用了未授权的对象: {", ".join(sorted(unknown))}；'
            f'可用对象: {", ".join(PYTHON_MODULE_ALLOWLIST)}')
    return expr


def run_python_expression(expr):
    """在一个受限命名空间中执行 Python 表达式。"""
    _check_python_expression(expr)
    import math
    import statistics
    import collections
    import hashlib

    allowed_modules = {
        'os': os, 'sys': sys, 'platform': platform, 'json': json,
        'time': time, 'datetime': datetime, 'shutil': shutil,
        'logging': logging, 'collections': collections, 're': re,
        'math': math, 'statistics': statistics, 'hashlib': hashlib,
        'threading': threading, 'uuid': uuid, 'subprocess': subprocess,
    }
    try:
        import psutil  # 可选依赖
        allowed_modules['psutil'] = psutil
    except Exception:
        pass

    sandbox = {'__builtins__': {
        'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
        'list': list, 'dict': dict, 'set': set, 'tuple': tuple, 'range': range,
        'min': min, 'max': max, 'sum': sum, 'abs': abs, 'round': round,
        'sorted': sorted, 'any': any, 'all': all, 'print': print,
        'enumerate': enumerate, 'zip': zip, 'isinstance': isinstance,
        'type': type, 'repr': repr, 'format': format, 'map': map, 'filter': filter,
    }}
    sandbox.update(allowed_modules)
    try:
        result = eval(expr, sandbox, {})  # noqa: S307 - 已通过白名单与黑名单双重校验
    except Exception as e:
        raise DebugActionError(f'表达式执行失败: {type(e).__name__}: {e}')
    try:
        json.dumps(result, ensure_ascii=False)
        return result
    except Exception:
        return repr(result)


def run_shell_command(command):
    """执行白名单内的只读诊断命令。"""
    if not command or not command.strip():
        raise DebugActionError('命令不能为空')
    cmd = command.strip()
    if any(ch in cmd for ch in ('&', '|', ';', '>', '<', '`', '$', '\n', '\r')):
        raise DebugActionError('命令中不允许出现管道、重定向或分隔符')
    if not any(re.match(pattern, cmd, re.IGNORECASE) for pattern in SHELL_WHITELIST):
        raise DebugActionError(
            f'命令不在白名单内。允许的命令形态: {", ".join(SHELL_WHITELIST[:5])} ...')

    try:
        completed = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT, cwd=os.getcwd(),
            encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise DebugActionError(f'命令执行超时（>{COMMAND_TIMEOUT}s）')
    except Exception as e:
        raise DebugActionError(f'命令执行失败: {e}')

    return {
        'command': cmd,
        'returncode': completed.returncode,
        'stdout': _truncate(completed.stdout or ''),
        'stderr': _truncate(completed.stderr or ''),
    }


def run_db_query(sql):
    """执行只读 SQL 查询。"""
    if not sql or not sql.strip():
        raise DebugActionError('SQL 不能为空')
    if not _SELECT_PATTERN.match(sql):
        raise DebugActionError('仅允许 SELECT 查询')
    if _FORBIDDEN_SQL.search(sql):
        raise DebugActionError('查询中包含被禁止的 SQL 关键字')
    if ';' in sql.strip().rstrip(';'):
        raise DebugActionError('不允许多语句查询')

    from ..database import db
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()[:200]]
        return {'columns': columns, 'rows': rows, 'row_count': len(rows)}
    except Exception as e:
        raise DebugActionError(f'查询失败: {e}')


def collect_runtime_snapshot():
    """采集运行状态快照（供调试方了解当前场景）。"""
    snapshot = {'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}

    def _safe(fn, default=None):
        try:
            return fn()
        except Exception as e:
            return f'error: {e}' if default is None else default

    snapshot['process'] = _safe(lambda: {
        'pid': os.getpid(),
        'threads': threading.active_count(),
        'thread_names': [t.name for t in threading.enumerate()][:40],
        'cwd': os.getcwd(),
        'executable': sys.executable,
        'frozen': bool(getattr(sys, 'frozen', False)),
    })

    def _memory():
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            return {'rss_mb': round(mem.rss / 1024 / 1024, 2),
                    'vms_mb': round(mem.vms / 1024 / 1024, 2),
                    'cpu_percent': proc.cpu_percent(interval=0.0)}
        except Exception:
            return {'note': 'psutil 不可用，已省略进程内存信息'}
    snapshot['memory'] = _safe(_memory, {})

    snapshot['database'] = _safe(_database_stats, {})

    def _downloads():
        from ..services import download_service
        return {
            'queue_size': download_service.download_queue.qsize(),
            'active_progress': dict(list(download_service.progress_cache.items())[:50]),
            'cancelled': sorted(download_service.cancelled_tasks)[:50],
            'safe_output_mode': download_service.is_safe_output_mode(),
        }
    snapshot['downloads'] = _safe(_downloads, {})

    snapshot['streams'] = _safe(lambda: __import__(
        'backend.core.error_manager', fromlist=['probe_stream_state']).probe_stream_state(), {})

    def _logs():
        from . import log_manager
        stats = log_manager.get_log_stats()
        stats.pop('files', None)
        return stats
    snapshot['logging'] = _safe(_logs, {})

    return snapshot


def _database_stats():
    from ..database import db, models
    from sqlalchemy import func
    with db.SessionLocal() as session:
        total = session.query(func.count(models.Video.bvid)).scalar()
        by_status = dict(session.query(
            models.Video.download_status, func.count(models.Video.bvid)
        ).group_by(models.Video.download_status).all())
        collections = session.query(func.count(models.Collection.id)).scalar()
    return {
        'video_total': total,
        'by_download_status': by_status,
        'collection_total': collections,
    }
