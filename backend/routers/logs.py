# -*- coding: utf-8 -*-
# Path: backend/routers/logs.py
"""日志路由：实时推送、多条件筛选、复制 / 下载、物理日志目录管理。"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from ..core import log_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _parse_levels(levels: Optional[str]):
    """把 ``ERROR,WARNING`` 解析为级别列表。"""
    if not levels:
        return None
    return [item.strip().upper() for item in levels.split(',') if item.strip()]


def _parse_heartbeat_categories(payload):
    """把 ``request,login`` 或列表解析为心跳类别集合。"""
    if not payload:
        return None
    if isinstance(payload, str):
        items = payload.split(',')
    else:
        items = list(payload)
    cleaned = {str(i).strip().lower() for i in items if str(i).strip()}
    return cleaned or None


def _collect_filters(
    levels: Optional[str] = None,
    keyword: Optional[str] = None,
    exclude: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    logger_contains: Optional[str] = None,
    hide_heartbeat: bool = False,
    hide_heartbeat_categories=None,
):
    """统一构造筛选条件（各筛选维度可任意叠加）。"""
    return {
        'levels': _parse_levels(levels),
        'keyword': keyword,
        'exclude': exclude,
        'start_time': start_time,
        'end_time': end_time,
        'logger_contains': logger_contains,
        'hide_heartbeat': hide_heartbeat,
        'heartbeat_categories': _parse_heartbeat_categories(hide_heartbeat_categories),
    }


@router.get("/stats")
def get_log_stats():
    """日志系统状态：内存占用、物理文件数量 / 体积、保留上限、当前时间。"""
    return log_manager.get_log_stats()


@router.get("/list")
def list_logs(
    levels: Optional[str] = Query(None, description="级别筛选，逗号分隔，例如 ERROR,WARNING"),
    keyword: Optional[str] = Query(None, description="包含关键字，支持 | 分隔的多个词（任一命中）"),
    exclude: Optional[str] = Query(None, description="排除关键字，规则同 keyword"),
    start_time: Optional[float] = Query(None, description="起始时间（epoch 秒）"),
    end_time: Optional[float] = Query(None, description="结束时间（epoch 秒）"),
    logger_contains: Optional[str] = Query(None, description="记录器名称包含"),
    hide_heartbeat: bool = Query(False, description="屏蔽心跳类噪声日志"),
    hide_heartbeat_categories: Optional[str] = Query(
        None, description="只屏蔽指定类别的心跳日志：request,login,polling（逗号分隔）"),
    since_seq: Optional[int] = Query(None, description="仅返回序号大于该值的日志（增量拉取）"),
    limit: int = Query(1000, ge=1, le=10000),
    newest_first: bool = Query(True),
):
    """按叠加条件查询内存日志。"""
    filters = _collect_filters(levels, keyword, exclude, start_time, end_time,
                               logger_contains, hide_heartbeat,
                               hide_heartbeat_categories)
    records = log_manager.query_logs(
        since_seq=since_seq, limit=limit, newest_first=newest_first, **filters)
    return {
        'logs': records,
        'count': len(records),
        'latest_seq': log_manager.latest_seq(),
        'filters': filters,
    }


@router.get("/meta")
def get_log_meta():
    """返回筛选器可选项（级别、记录器列表、时间范围、心跳分类计数等）。"""
    records = log_manager.query_logs(limit=100000, newest_first=False)
    levels = {}
    loggers = {}
    min_ts = max_ts = None
    heartbeat = 0
    heartbeat_categories = {}
    for rec in records:
        levels[rec['level']] = levels.get(rec['level'], 0) + 1
        loggers[rec['logger']] = loggers.get(rec['logger'], 0) + 1
        ts = rec.get('ts')
        if ts:
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
        if rec.get('heartbeat'):
            heartbeat += 1
            category = rec.get('heartbeat_category') or 'unknown'
            heartbeat_categories[category] = heartbeat_categories.get(category, 0) + 1
    return {
        'levels': sorted(levels.keys(), key=lambda x: _level_order(x)),
        'level_counts': levels,
        'loggers': sorted(loggers.items(), key=lambda kv: -kv[1])[:50],
        'time_range': {'min': min_ts, 'max': max_ts},
        'heartbeat_count': heartbeat,
        'heartbeat_categories': heartbeat_categories,
        'total': len(records),
        'heartbeat_patterns': list(log_manager.HEARTBEAT_PATTERNS),
        'server_time': log_manager.get_log_stats().get('time'),
    }


def _level_order(name):
    order = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}
    return order.get(str(name).upper(), 99)


@router.post("/clear")
def clear_logs(memory_only: bool = Query(True, description="是否只清空内存日志")):
    """清空内存日志（可选同时清空物理文件）。"""
    log_manager.clear_memory_logs()
    removed = 0
    if not memory_only:
        removed = log_manager.purge_log_files(include_active=True)
    log_manager.get_logger(__name__).info(
        f'[日志系统] 日志已清空（内存=True，物理文件删除 {removed} 个）')
    return {'status': 'success', 'removed_files': removed}


@router.get("/export")
def export_logs(
    fmt: str = Query('txt', description="导出格式：txt / json / jsonl"),
    download: bool = Query(False, description="是否作为文件下载"),
    levels: Optional[str] = None,
    keyword: Optional[str] = None,
    exclude: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    logger_contains: Optional[str] = None,
    hide_heartbeat: bool = False,
    hide_heartbeat_categories: Optional[str] = None,
    limit: int = Query(5000, ge=1, le=100000),
):
    """导出筛选后的日志（一键复制 / 下载）。"""
    filters = _collect_filters(levels, keyword, exclude, start_time, end_time,
                               logger_contains, hide_heartbeat,
                               hide_heartbeat_categories)
    records = log_manager.query_logs(limit=limit, newest_first=False, **filters)
    payload = log_manager.export_records(records, fmt=fmt.lower())

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    ext = {'json': 'json', 'jsonl': 'jsonl'}.get(fmt.lower(), 'txt')
    filename = f'bilimusic-logs-{stamp}.{ext}'
    headers = {}
    if download:
        headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    else:
        headers['X-Log-Count'] = str(len(records))
    media_type = {
        'json': 'application/json',
        'jsonl': 'application/x-ndjson',
    }.get(fmt.lower(), 'text/plain')
    return Response(content=payload, media_type=f'{media_type}; charset=utf-8', headers=headers)


@router.get("/stream")
async def stream_logs(
    request_timeout: int = Query(1800, ge=10, le=7200,
                                 description="单次连接的最长存活秒数"),
    hide_heartbeat: bool = Query(False, description="屏蔽心跳类噪声日志"),
    hide_heartbeat_categories: Optional[str] = Query(
        None, description="只屏蔽指定类别的心跳日志：request,login,polling"),
    levels: Optional[str] = Query(None, description="只推送指定级别"),
    keyword: Optional[str] = Query(None),
    exclude: Optional[str] = Query(None),
):
    """实时日志推送（SSE）。

    采用「序号增量拉取 + 条件过滤」的方式，因此筛选条件变化只需要重连，
    不会丢失日志；心跳噪声可在服务端直接屏蔽，减少前端负担。
    """
    filters = _collect_filters(levels, keyword, exclude, None, None, None,
                               hide_heartbeat, hide_heartbeat_categories)

    async def event_publisher():
        last_seq = log_manager.latest_seq()
        yield f"event: ready\ndata: {json.dumps({'latest_seq': last_seq, 'server_time': log_manager.get_log_stats().get('time')})}\n\n"
        idle = 0
        elapsed = 0
        while elapsed < request_timeout:
            records = log_manager.query_logs(
                since_seq=last_seq, limit=500, newest_first=False, **filters)
            if records:
                last_seq = records[-1]['seq']
                for rec in records:
                    yield f"event: log\ndata: {json.dumps(rec, ensure_ascii=False)}\n\n"
                idle = 0
            else:
                idle += 1
                # 每 5 秒发送一次注释帧，保持连接不被中间层回收
                if idle % 5 == 0:
                    yield ": keepalive\n\n"
            await asyncio.sleep(1)
            elapsed += 1

    return StreamingResponse(
        event_publisher(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive',
                 'X-Accel-Buffering': 'no'})


# ============================================================
# 物理日志管理
# ============================================================

@router.get("/files")
def list_log_files():
    """列出物理日志文件（含体积与修改时间）。"""
    stats = log_manager.get_log_stats()
    return {
        'log_dir': stats.get('log_dir'),
        'files': stats.get('files', []),
        'file_count': stats.get('file_count', 0),
        'total_bytes': stats.get('total_bytes', 0),
        'max_files': stats.get('max_files'),
        'max_file_bytes': stats.get('max_file_bytes'),
        'max_total_bytes': stats.get('max_total_bytes'),
    }


@router.get("/files/{filename}")
def read_log_file(filename: str, max_bytes: int = Query(512 * 1024, ge=1024, le=8 * 1024 * 1024)):
    """读取某个物理日志文件的尾部内容。"""
    try:
        content = log_manager.read_file_tail(filename, max_bytes=max_bytes)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='日志文件不存在')
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {'filename': filename, 'content': content, 'truncated': len(content) >= max_bytes}


@router.post("/open-dir")
def open_log_directory():
    """在系统资源管理器中打开物理日志目录。"""
    ok, detail = log_manager.open_log_dir()
    if not ok:
        raise HTTPException(status_code=500, detail=f'无法打开日志目录: {detail}')
    logger.info(f'[日志系统] 已在资源管理器中打开日志目录: {detail}')
    return {'status': 'success', 'log_dir': detail}


@router.post("/retention")
def update_retention(
    max_files: Optional[int] = Query(None, ge=1, le=200, description="日志文件数量上限"),
    max_file_mb: Optional[float] = Query(None, gt=0, le=1024, description="单文件体积上限(MB)"),
    max_total_mb: Optional[float] = Query(None, gt=0, le=10240, description="日志总占用上限(MB)"),
):
    """调整日志保留策略并立即回收超限文件。"""
    stats = log_manager.update_retention(
        max_files=max_files, max_file_mb=max_file_mb, max_total_mb=max_total_mb)
    logger.info(f'[日志系统] 保留策略已更新: 文件数<={stats.get("max_files")}, '
                f'单文件<={stats.get("max_file_bytes")}, 总量<={stats.get("max_total_bytes")}')
    return stats


@router.post("/purge")
def purge_log_files(
    include_active: bool = Query(False, description="是否同时清空正在写入的日志文件"),
    confirmed: bool = Query(False, description="危险操作确认标记"),
):
    """删除物理日志文件（需确认）。"""
    if not confirmed:
        raise HTTPException(status_code=400, detail='该操作会删除磁盘上的日志文件，需要确认后执行')
    removed = log_manager.purge_log_files(include_active=include_active)
    logger.warning(f'[日志系统] 已删除 {removed} 个物理日志文件（include_active={include_active}）')
    return {'status': 'success', 'removed_files': removed, **log_manager.get_log_stats()}
