# -*- coding: utf-8 -*-
# Path: backend/main.py

import os
import sys
import logging
from datetime import datetime
from threading import Thread
from fastapi import FastAPI, Request, HTTPException

# ============================================================
# 🔴 DIAGNOSTIC PROBE — direct file write, bypasses logging entirely
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
_diag("logging.basicConfig() done")

# 尝试加载内存日志处理器（非关键功能，失败不影响启动）
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
from .routers import auth, bili, local, play, system, theme, stats, download
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
    logger.info("正在初始化数据库...")
    
    # 1. 执行数据库迁移检查
    try:
        run_migrations()
    except Exception as e:
        logger.error(f"数据库迁移执行失败: {e}")
    models.Base.metadata.create_all(bind=db.engine)
    from .services.clipboard_service import get_thread_safe_db_session
    
    # 2. 启动时校验已下载文件的完整性
    def verify_completed_downloads():
        with get_thread_safe_db_session() as db_session:
            # 使用分页查询避免一次性加载过多数据导致内存溢出
            page_size = 100
            offset = 0
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
                    models.Video.download_status == 'completed'
                ).offset(offset).limit(page_size).all()
                
                if not videos:
                    break
                    
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
                offset += page_size
                
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

# 代理 B 站图片以解决防盗链问题
from fastapi import Response
import httpx

@app.get("/api/proxy/image")
async def proxy_image(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # 检查是否是本地图片
    if url.startswith('/local_covers/'):
        # 重定向到本地静态文件服务
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)
        
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
    except Exception as e:
        logger.error(f"代理图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    from .services.cover_cache_service import get_cover_cache_service
    cover_service = get_cover_cache_service()
    await cover_service.close()
    logger.info("封面缓存服务已关闭")

# 日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 忽略高频轮询请求的日志，并将普通请求降级为 DEBUG
    if not request.url.path.endswith(('/system/events', '/download/status', '/system/clipboard/pending')):
        logger.debug(f"📡 [请求] {request.method} {request.url}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"❌ [错误] {e}")
        raise e

if __name__ == "__main__":
    import uvicorn
    port = server_config.get('port', 12180)
    host = server_config.get('host', "127.0.0.1")
    
    logger.info(f"启动 BiliMusic 后端服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
