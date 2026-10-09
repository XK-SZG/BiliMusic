# -*- coding: utf-8 -*-
# Path: backend/main.py

import os
import sys
import logging
from datetime import datetime
from threading import Thread
from fastapi import FastAPI, Request, HTTPException

# ============================================================
# DIAGNOSTIC PROBE — direct file write, bypasses logging entirely
# ============================================================
_DIAG_LOG = os.environ.get('BILIMUSIC_CRASH_LOG', '')

def _diag(msg):
    """Write a diagnostic message directly to the crash log file with immediate flush.
    This bypasses the logging system entirely to avoid deadlocks or buffering issues."""
    try:
        if _DIAG_LOG:
            with open(_DIAG_LOG, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] main.py DIAG: {msg}\n")
                f.flush()
    except:
        pass

_diag("Entering backend/main.py module-level code")

# 初始化日志（必须在任何可能失败的导入之前）
# [修复] 统一使用 core.log_manager 装配日志：
#   1. 时间戳与系统时间严格同步（带时区偏移），不再出现「从 1970 开始计时」；
#   2. 同时写入内存环形缓冲与物理文件，支持实时推送与历史回溯；
#   3. 物理文件按「单文件体积 / 文件数量 / 总占用」三级策略自动轮转回收。
try:
    from .core.log_manager import setup_logging as _setup_logging
    _diag("log_manager imported (early), calling setup_logging...")
    _setup_logging()
    _diag("setup_logging complete")
except Exception as _log_err:  # 日志系统装配失败不能阻断启动
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger(__name__).warning(f"统一日志系统装配失败，已回退到 basicConfig: {_log_err}")
logger = logging.getLogger(__name__)
_diag("logging setup done")

# 加载内存日志处理器（兼容旧调用路径，失败不影响启动）
try:
    _diag("Importing log_manager...")
    from .core.log_manager import setup_memory_logger
    _diag("log_manager imported, calling setup...")
    setup_memory_logger()
    logger.info("内存日志处理器已加载")
    _diag("log_manager setup complete")
except Exception as e:
    logger.warning(f"内存日志处理器加载失败（非关键功能）: {e}")
    _diag(f"log_manager FAILED: {e}")

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

_diag("Importing .core.paths ...")
from .core.paths import DATA_DIR, BASE_DIR
_diag(".core.paths imported")

_diag("Importing .core.config ...")
from .core.config import get_config
_diag(".core.config imported")

_diag("Importing .database ...")
from .database import models, db
_diag(".database imported")

_diag("Importing .routers ...")
from .routers import auth, bili, local, play, system, theme, stats, download, logs, debug
_diag(".routers imported")

_diag("Importing .services ...")
from .services import cleanup_service, download_service, clipboard_service
_diag(".services imported")

_diag("Importing .migrate_db ...")
from .migrate_db import run_migrations
_diag(".migrate_db imported")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "covers"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "stickers"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "backgrounds"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "particles"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "fonts"), exist_ok=True)

# 获取配置
config = get_config()
server_config = config.get_server_config()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    # [新增] 安装全局异常钩子：未捕获异常会完整落入日志与错误系统
    try:
        from .core.log_manager import install_excepthook
        install_excepthook()
    except Exception as e:
        logger.debug(f"安装全局异常钩子失败（忽略）: {e}")

    logger.info("正在初始化数据库...")
    
    # 1. 执行数据库迁移检查
    try:
        run_migrations()
    except Exception as e:
        logger.error(f"数据库迁移执行失败: {e}")
        try:
            from .core.error_manager import get_error_manager
            get_error_manager().report_exception(
                e, scope='database', message='数据库迁移执行失败',
                dedupe_key='migration')
        except Exception:
            pass
    models.Base.metadata.create_all(bind=db.engine)
    from .services.clipboard_service import get_thread_safe_db_session
    
    # 2. 启动时校验已下载文件的完整性
    def verify_completed_downloads():
        with get_thread_safe_db_session() as db_session:
            # [修复] 原实现用 LIMIT/OFFSET 分页遍历「download_status == 'completed'」的结果集，
            # 但循环体本身会把校验失败的记录改写成 'not_downloaded'，结果集在翻页过程中不断变短：
            # 已改写的行退出结果集后，其后面的行会整体前移，offset 再递增就会整段跳过，
            # 表现为「部分已丢失的文件永远不会被重置」，界面长期显示已下载却播放无声。
            # 现改为按主键推进的游标分页：过滤条件（bvid > 游标）不随状态改写而变化，逐行且不遗漏。
            page_size = 100
            last_bvid = ''
            fixed_count = 0
            reset_count = 0

            # 获取总数用于日志
            total_count = db_session.query(models.Video).filter(
                models.Video.download_status == 'completed'
            ).count()

            if total_count == 0:
                logger.info("[启动校验] 无需校验的下载文件")
                return

            logger.info(f"[启动校验] 开始校验 {total_count} 个已下载文件...")

            while True:
                videos = db_session.query(models.Video).filter(
                    models.Video.download_status == 'completed',
                    models.Video.bvid > last_bvid
                ).order_by(models.Video.bvid.asc()).limit(page_size).all()

                if not videos:
                    break

                # 游标推进：始终大于本批最后一条的主键
                last_bvid = videos[-1].bvid

                for video in videos:
                    # 检查 local_path 是否存在
                    if video.local_path and os.path.exists(video.local_path):
                        continue

                    # 如果 local_path 不存在，尝试在默认下载目录查找
                    expected_path = os.path.join(cleanup_service.DOWNLOAD_PATH, f"{video.bvid}.mp4")
                    if os.path.exists(expected_path):
                        video.local_path = expected_path
                        fixed_count += 1
                    else:
                        # 文件确实丢失，重置状态
                        video.download_status = 'not_downloaded'
                        video.local_path = None
                        reset_count += 1

                # 每批次提交一次，避免长事务
                db_session.commit()

            logger.info(f"[启动校验] 完成，修复了 {fixed_count} 个 local_path，重置了 {reset_count} 个无效状态")

    # 在后台线程执行校验，不阻塞启动
    Thread(target=verify_completed_downloads, daemon=True, name="VerifyDownloadsThread").start()
    
    # 3. 重置未完成的下载任务状态
    with get_thread_safe_db_session() as db_session:
        db_session.query(models.Video).filter(
            models.Video.download_status.in_(['pending', 'downloading'])
        ).update({models.Video.download_status: 'not_downloaded'}, synchronize_session=False)
        db_session.commit()
        logger.info(">>> 已重置未完成的下载任务状态")
        logger.info(">>> 数据库初始化完成")

    # 启动后台服务
    logger.info("正在启动后台服务...")
    
    # 启动清理服务
    cleanup_thread = Thread(target=cleanup_service.run_cleanup_scheduler, daemon=True, name="CleanupThread")
    cleanup_thread.start()
    
    
    # 启动剪贴板监听服务
    from .dependencies import get_bili
    clipboard_thread = Thread(target=clipboard_service.watch_clipboard, args=(get_bili(),), daemon=True, name="ClipboardThread")
    clipboard_thread.start()
    
    logger.info(">>> 后台服务启动完成")
    
    yield
    
    # 关闭时执行
    logger.info("正在关闭应用...")
    # [修复] 原实现用已废弃的 @app.on_event("shutdown") 关闭封面缓存服务，
    # FastAPI 新版本会发出 DeprecationWarning 且存在被移除的风险，
    # 一旦不再触发，httpx.AsyncClient 会带着未关闭的连接池退出。
    # 现统一收敛到 lifespan 的收尾段（与应用启动对称）。
    try:
        from .services.cover_cache_service import get_cover_cache_service
        await get_cover_cache_service().close()
        logger.info("封面缓存服务已关闭")
    except Exception as e:
        logger.warning(f"关闭封面缓存服务失败（忽略）: {e}")
    logger.info(">>> 应用已关闭")

app = FastAPI(title="BiliMusic API", lifespan=lifespan)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/local_covers", StaticFiles(directory=os.path.join(DATA_DIR, "covers")), name="local_covers")
app.mount("/local_stickers", StaticFiles(directory=os.path.join(DATA_DIR, "stickers")), name="local_stickers")
app.mount("/local_backgrounds", StaticFiles(directory=os.path.join(DATA_DIR, "backgrounds")), name="local_backgrounds")
app.mount("/downloads", StaticFiles(directory=cleanup_service.DOWNLOAD_PATH), name="downloads")

# 注册路由
app.include_router(auth.router)
app.include_router(bili.router)
app.include_router(local.router)
app.include_router(play.router)
app.include_router(system.router)
app.include_router(theme.router)
app.include_router(stats.router)
app.include_router(download.router)
app.include_router(logs.router)
app.include_router(debug.router)

# 代理 B 站图片以解决防盗链问题
from fastapi import Response
import httpx

@app.get("/api/proxy/image")
async def proxy_image(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # [修复] 先净化地址：
    #   - 剥离可能存在的代理自引用包装（历史脏数据会把本接口地址又存回数据库）；
    #   - 丢弃形如 https:///api/proxy/image?... 的畸形地址（三斜杠、无主机名），
    #     否则 httpx 会抛 “Request URL is missing an 'http://' or 'https://' protocol”，
    #     并被下面的 except 包装成 500。
    from .core.cover_utils import sanitize_cover_url
    original_url = url
    cleaned_url = sanitize_cover_url(url)
    if cleaned_url != original_url:
        logger.warning(f"[封面代理] 检测到异常封面地址，已净化: {original_url} -> {cleaned_url or '(无法还原)'}")
        url = cleaned_url
    if not url:
        raise HTTPException(
            status_code=404,
            detail="封面地址无效（无法从代理地址中还原出原始链接）")

    # 检查是否是本地图片
    if url.startswith('/local_covers/'):
        # 重定向到本地静态文件服务
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)

    if not url.lower().startswith(('http://', 'https://')):
        logger.warning(f"[封面代理] 非远程直链，返回 404: {url}")
        raise HTTPException(status_code=404, detail="封面地址不是可请求的远程直链")

    # 使用封面缓存服务
    from .services.cover_cache_service import get_cover_cache_service
    try:
        cover_service = get_cover_cache_service()
        image_data = await cover_service.get_cover(url)

        if image_data is None:
            raise HTTPException(status_code=404, detail="Image not found")

        # 确定 Content-Type
        content_type = "image/jpeg"
        if url.endswith(".png"):
            content_type = "image/png"
        elif url.endswith(".webp"):
            content_type = "image/webp"
        elif url.endswith(".gif"):
            content_type = "image/gif"

        return Response(
            content=image_data,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400", # 浏览器缓存 1 天
                "Access-Control-Allow-Origin": "*"
            }
        )
    except HTTPException:
        # [修复] HTTPException 必须原样透传，否则 404 会被下面包装成 500
        raise
    except Exception as e:
        logger.error(f"代理图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 日志中间件
#
# 说明：这里排除的路径都是「高频轮询」或「会自身产生日志查询」的接口。
# 尤其是 /api/logs/list、/api/logs/export 这类日志查询接口——
# 如果记录它们自身的请求 URL，被查询的关键字会出现在它自己的日志里，
# 造成「搜索结果里永远有它自己」的干扰（用户会误以为筛选没生效）。
_NOISY_PATH_SUFFIXES = (
    '/system/events',
    '/download/status',
    '/system/clipboard/pending',
    '/logs/stream',
    '/logs/list',
    '/logs/export',
    '/logs/stats',
    '/logs/meta',
    '/logs/files',
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 忽略高频轮询与日志查询请求，并将其余请求降级为 DEBUG
    if not request.url.path.endswith(_NOISY_PATH_SUFFIXES):
        logger.debug(f"[请求] {request.method} {request.url}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"[错误] {e}")
        # [新增] 未处理的 HTTP 层异常统一进入错误系统
        try:
            from .core.error_manager import get_error_manager
            get_error_manager().report_exception(
                e, scope='api',
                message=f'接口处理失败: {request.method} {request.url.path}',
                context={'path': request.url.path, 'method': request.method},
                dedupe_key=f'api:{request.url.path}', popup=False)
        except Exception:
            pass
        # [修复] 原写法 `raise e` 会重置异常链，丢失原始 traceback（只剩重新抛出的位置），
        # 排障时看不到真正的出错点。裸 raise 才能保留完整栈。
        raise

if __name__ == "__main__":
    import uvicorn
    port = server_config.get('port', 12180)
    host = server_config.get('host', "127.0.0.1")
    
    logger.info(f"启动 BiliMusic 后端服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
