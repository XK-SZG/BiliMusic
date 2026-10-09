# -*- coding: utf-8 -*-
# Path: backend/routers/debug.py
"""调试系统路由（远程调试组件）。

所有接口都需要 ``X-Debug-Token`` 请求头，且调试模式必须处于开启状态。
面向使用 Vibe Coding 的开发者，可被本机脚本 / AI 助手直接调用。
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from ..core import debug_service, error_manager, log_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


def require_debug_token(x_debug_token: Optional[str] = Header(None, alias='X-Debug-Token')):
    """令牌鉴权依赖。"""
    session = debug_service.get_debug_session()
    if not session.enabled:
        raise HTTPException(status_code=403, detail='调试模式未开启')
    if not session.verify(x_debug_token):
        session.audit('auth_failed', '令牌校验失败', ok=False)
        raise HTTPException(status_code=403, detail='调试令牌无效')
    session.touch()
    return session


# ============================================================
# 协议与开关（无需令牌：用于界面自行管理）
# ============================================================

@router.get('/status')
def debug_status(include_token: bool = Query(False, description='是否返回当前令牌（仅界面使用）')):
    """查询调试系统状态。"""
    session = debug_service.get_debug_session()
    return session.status(include_token=include_token)


@router.get('/agreement')
def get_agreement():
    """获取协议全文与确认项。"""
    session = debug_service.get_debug_session()
    state = session.consent_state()
    return {
        'version': state['version'],
        'agreement': state['agreement'],
        'checklist': state['checklist'],
        'confirmed': state['confirmed'],
        'confirmed_at': state['confirmed_at'],
        'stale': state['stale'],
    }


@router.post('/consent')
def accept_consent(payload: dict = Body(default={})):
    """提交协议确认（必须逐项勾选）。"""
    session = debug_service.get_debug_session()
    ok, message = session.accept_consent(
        checklist=payload.get('checklist') or [], source=payload.get('source', 'ui'))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {'status': 'success', 'message': message, **session.consent_state()}


@router.delete('/consent')
def revoke_consent():
    """撤回协议确认（同时关闭调试模式）。"""
    session = debug_service.get_debug_session()
    session.revoke_consent()
    return {'status': 'success', 'message': '已撤回协议确认并关闭调试模式'}


@router.post('/enable')
def enable_debug(payload: dict = Body(default={})):
    """开启调试模式并返回访问令牌。"""
    session = debug_service.get_debug_session()
    ok, message, token = session.enable(
        allow_python=bool(payload.get('allow_python', False)),
        allow_shell=bool(payload.get('allow_shell', False)),
        source=payload.get('source', 'ui'),
    )
    if not ok:
        raise HTTPException(status_code=403, detail=message)
    return {'status': 'success', 'message': message, 'token': token,
            **session.status(include_token=False), 'token_issued': True}


@router.post('/disable')
def disable_debug(payload: dict = Body(default={})):
    """关闭调试模式并销毁令牌。"""
    session = debug_service.get_debug_session()
    session.disable(reason=payload.get('reason', '用户关闭'))
    return {'status': 'success', 'message': '调试模式已关闭，访问令牌已销毁'}


@router.post('/token/rotate')
def rotate_token():
    """轮换访问令牌。"""
    session = debug_service.get_debug_session()
    ok, message, token = session.rotate_token()
    if not ok:
        raise HTTPException(status_code=403, detail=message)
    return {'status': 'success', 'message': message, 'token': token}


# ============================================================
# 远程调试接口（需要令牌）
# ============================================================

@router.get('/ping')
def debug_ping(session=Depends(require_debug_token)):
    """连通性探测：调试脚本的第一步。"""
    session.audit('ping', '连通性探测')
    return {
        'ok': True,
        'message': 'pong',
        'enabled_at': session.enabled_at,
        'capabilities': {
            'python': session.allow_python,
            'shell': session.allow_shell,
            'db_query': True,
            'logs': True,
            'scene': True,
        },
    }


@router.get('/scene')
def debug_scene(session=Depends(require_debug_token)):
    """获取运行场景快照（进程、内存、数据库、下载、日志、流状态）。"""
    started = time.time()
    try:
        snapshot = debug_service.collect_runtime_snapshot()
    except Exception as e:
        session.audit('scene', f'采集失败: {e}', ok=False)
        raise HTTPException(status_code=500, detail=f'场景采集失败: {e}')
    duration = int((time.time() - started) * 1000)
    session.audit('scene', '获取运行场景快照', duration_ms=duration)
    snapshot['duration_ms'] = duration
    return snapshot


@router.get('/logs')
def debug_logs(
    limit: int = Query(200, ge=1, le=5000),
    levels: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    exclude: Optional[str] = Query(None),
    hide_heartbeat: bool = Query(False),
    since_seq: Optional[int] = Query(None),
    session=Depends(require_debug_token),
):
    """读取后台日志（支持与界面一致的叠加筛选）。"""
    from .logs import _collect_filters
    filters = _collect_filters(levels, keyword, exclude, None, None, None, hide_heartbeat)
    records = log_manager.query_logs(
        since_seq=since_seq, limit=limit, newest_first=True, **filters)
    session.audit('logs', f'读取日志 {len(records)} 条', duration_ms=None)
    return {'logs': records, 'count': len(records), 'latest_seq': log_manager.latest_seq()}


@router.get('/errors')
def debug_errors(
    status: Optional[str] = Query(None, description='pending / resolved / bypassed / viewed'),
    limit: int = Query(50, ge=1, le=500),
    session=Depends(require_debug_token),
):
    """查看错误系统的错误记录。"""
    manager = error_manager.get_error_manager()
    items = manager.list_errors(status=status, limit=limit)
    session.audit('errors', f'读取错误记录 {len(items)} 条')
    return {'errors': items, 'pending': manager.pending_count(),
            'catalog': error_manager.catalog_as_list()}


@router.post('/errors/{error_id}/bypass')
def debug_bypass_error(error_id: str, payload: dict = Body(default={}),
                       session=Depends(require_debug_token)):
    """绕过某条错误继续业务逻辑。"""
    manager = error_manager.get_error_manager()
    record = manager.bypass(error_id, note=payload.get('note') or '调试方选择绕过')
    if record is None:
        raise HTTPException(status_code=404, detail='错误记录不存在')
    session.audit('error_bypass', f'绕过错误 {error_id}')
    return {'status': 'success', 'error': record.to_dict()}


@router.post('/errors/{error_id}/repair')
def debug_repair_error(error_id: str, session=Depends(require_debug_token)):
    """对某条错误执行一键修复。"""
    manager = error_manager.get_error_manager()
    ok, message, record = manager.repair(error_id)
    session.audit('error_repair', f'修复错误 {error_id}: {message}', ok=ok)
    if record is None:
        raise HTTPException(status_code=404, detail='错误记录不存在')
    return {'status': 'success' if ok else 'failed', 'message': message,
            'error': record.to_dict()}


@router.post('/action')
def debug_action(payload: dict = Body(...), session=Depends(require_debug_token)):
    """执行一个受限调试动作。

    请求体::

        {"action": "python" | "shell" | "db_query", "payload": {...}}

    - ``python``    ：执行受限表达式，需要开启「表达式执行」能力
    - ``shell``     ：执行白名单内的只读诊断命令，需要开启「命令执行」能力
    - ``db_query``  ：执行只读 SELECT 查询
    """
    action = str(payload.get('action') or '').strip().lower()
    data = payload.get('payload') or {}
    started = time.time()

    if action not in debug_service.ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f'不支持的调试动作: {action}；可用动作: python / shell / db_query')

    try:
        if action == 'python':
            if not session.allow_python:
                raise debug_service.DebugActionError(
                    '「表达式执行」能力未开启，请在设置 → 调试系统中开启后重试')
            expression = data.get('expression') or data.get('code') or ''
            result = debug_service.run_python_expression(expression)
            response = {'action': action, 'result': result}

        elif action == 'shell':
            if not session.allow_shell:
                raise debug_service.DebugActionError(
                    '「命令执行」能力未开启，请在设置 → 调试系统中开启后重试')
            response = {'action': action,
                        **debug_service.run_shell_command(data.get('command') or '')}

        elif action == 'db_query':
            sql = data.get('sql') or data.get('query') or ''
            response = {'action': action, **debug_service.run_db_query(sql)}

        else:  # pragma: no cover - 上面的白名单已拦截
            raise debug_service.DebugActionError(f'动作 {action} 暂未实现')

    except debug_service.DebugActionError as e:
        session.audit(f'action:{action}', f'被拒绝: {e}', ok=False)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.audit(f'action:{action}', f'执行异常: {e}', ok=False)
        logger.error(f'[调试系统] 动作 {action} 执行失败: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=f'执行失败: {e}')

    duration = int((time.time() - started) * 1000)
    response['duration_ms'] = duration
    session.audit(f'action:{action}', f'执行成功（{duration}ms）', duration_ms=duration)
    return response


@router.get('/audit')
def debug_audit(limit: int = Query(200, ge=1, le=1000), session=Depends(require_debug_token)):
    """查看调试审计日志。"""
    session.audit('audit_read', '读取审计日志')
    return {'audit': session.get_audit(limit=limit)}


@router.post('/report-test-error')
def debug_report_test_error(payload: dict = Body(default={}),
                            session=Depends(require_debug_token)):
    """向错误系统注入一条测试错误（用于验证前端弹窗 / SSE 链路）。

    仅在调试模式下可用，且会写入审计日志，便于排查「弹窗没出来」这类问题。
    """
    code = str(payload.get('code') or 'UNKNOWN_ERROR')
    message = str(payload.get('message') or '调试系统注入的测试错误')
    manager = error_manager.get_error_manager()
    record = manager.report(
        code, message,
        detail=payload.get('detail') or '由 /api/debug/report-test-error 注入',
        context={'scope': 'debug', 'source': 'debug_api'},
        popup=bool(payload.get('popup', True)),
    )
    session.audit('report_test_error', f'注入测试错误 {code}: {message}')
    return {'status': 'success', 'error': record.to_dict() if record else None}


@router.delete('/audit')
def clear_audit(session=Depends(require_debug_token)):
    """清空调试审计日志。"""
    session.clear_audit()
    return {'status': 'success', 'message': '审计日志已清空'}


@router.get('/help')
def debug_help(session=Depends(require_debug_token)):
    """返回调试 API 的自描述文档（便于 AI 助手自动发现能力）。"""
    session.audit('help', '读取调试接口文档')
    return {
        'base': '/api/debug',
        'auth': {'header': 'X-Debug-Token', 'value': '（在设置 → 调试系统中查看）'},
        'endpoints': [
            {'method': 'GET', 'path': '/ping', 'desc': '连通性与能力探测'},
            {'method': 'GET', 'path': '/help', 'desc': '本接口文档'},
            {'method': 'GET', 'path': '/scene', 'desc': '运行场景快照'},
            {'method': 'GET', 'path': '/logs', 'desc': '读取日志，支持 levels/keyword/exclude/hide_heartbeat/since_seq'},
            {'method': 'GET', 'path': '/errors', 'desc': '错误记录与错误目录'},
            {'method': 'POST', 'path': '/errors/{id}/repair', 'desc': '一键修复指定错误'},
            {'method': 'POST', 'path': '/errors/{id}/bypass', 'desc': '绕过指定错误'},
            {'method': 'POST', 'path': '/action', 'desc': '执行受限动作 python / shell / db_query'},
            {'method': 'GET', 'path': '/audit', 'desc': '调试审计日志'},
            {'method': 'POST', 'path': '/report-test-error', 'desc': '注入测试错误以验证弹窗链路'},
        ],
        'actions': {
            'python': {'body': {'action': 'python', 'payload': {'expression': 'platform.python_version()'}},
                       'note': '仅允许白名单模块的表达式，禁止私有属性与危险调用'},
            'shell': {'body': {'action': 'shell', 'payload': {'command': 'ipconfig /all'}},
                      'note': '仅允许只读诊断命令白名单，最长 20 秒'},
            'db_query': {'body': {'action': 'db_query', 'payload': {'sql': 'SELECT bvid, download_status FROM videos LIMIT 10'}},
                         'note': '仅允许单条 SELECT 查询'},
        },
        'capabilities': {
            'python': session.allow_python,
            'shell': session.allow_shell,
        },
    }
