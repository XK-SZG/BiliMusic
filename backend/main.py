# -*- coding: utf-8 -*-
# Path: backend/main.py

import os
import logging
from threading import Thread
from fastapi import FastAPI, Request, HTTPException

from .core.log_manager import setup_memory_logger
setup_memory_logger()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .database import models, db
from . import migrate_db
from .services import cleanup_service
from .dependencies import bili
from .routers import auth_router, bili_router, local_router, play_router, system_router, theme_router, download_router, stats_router

# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="BiliMusic API")

def verify_completed_downloads(db_session, download_path):
    """
    [性能优化] 启动时校验所有 completed 状态的视频文件
    使用分页查询避免大数据量时的内存占用和启动延迟
    """
    from sqlalchemy import func
    
    # 先统计总数
    total_count = db_session.query(func.count(models.Video.bvid)).filter(
        models.Video.download_status == 'completed',
        models.Video.is_local != 1  # 排除本地导入的文件
    ).scalar()
    
    if total_count == 0:
        logger.info("[启动校验] 无需校验的下载文件")
        return
    
    logger.info(f"[启动校验] 开始校验 {total_count} 个已下载文件...")
    
    reset_count = 0
    fixed_count = 0
    page_size = 100  # 每次处理 100 条
    
    # [性能优化] 分页查询，避免一次性加载所有数据
    for offset in range(0, total_count, page_size):
        videos = db_session.query(models.Video).filter(
            models.Video.download_status == 'completed',
            models.Video.is_local != 1
        ).limit(page_size).offset(offset).all()
        
        for video in videos:
            # 1. 如果 local_path 存在且文件存在，跳过
            if video.local_path and os.path.exists(video.local_path):
                # 检查文件大小
                if os.path.getsize(video.local_path) < 0.5 * 1024 * 1024:
                    logger.warning(f"[启动校验] 文件过小，重置状态: {video.bvid}")
                    video.download_status = 'not_downloaded'
                    video.local_path = None
                    reset_count += 1
                continue
            
            # 2. 如果 local_path 为空或文件不存在，尝试查找文件
            expected_path = os.path.join(download_path, f"{video.bvid}.mp4")
            
            if os.path.exists(expected_path):
                # 检查文件大小
                if os.path.getsize(expected_path) < 0.5 * 1024 * 1024:
                    logger.warning(f"[启动校验] 文件过小，重置状态: {video.bvid}")
                    video.download_status = 'not_downloaded'
                    video.local_path = None
                    reset_count += 1
                else:
                    # 文件在默认位置，更新 local_path
                    if not video.local_path:
                        video.local_path = expected_path
                        fixed_count += 1
            else:
                # 文件不存在，重置状态
                logger.warning(f"[启动校验] 文件不存在，重置状态: {video.bvid}")
                video.download_status = 'not_downloaded'
                video.local_path = None
                reset_count += 1
        
        # [性能优化] 每批次提交一次，避免长事务
        db_session.commit()
    
    logger.info(f"[启动校验] 完成，修复了 {fixed_count} 个 local_path，重置了 {reset_count} 个无效状态")

def async_verify_completed_downloads():
    """在后台线程中执行文件校验，防止阻塞启动"""
    from .services.clipboard_service import get_thread_safe_db_session
    from .services.cleanup_service import DOWNLOAD_PATH
    import time
    time.sleep(2)  # 延迟 2 秒后开始校验，避免刚启动时抢占资源
    with get_thread_safe_db_session() as db_session:
        verify_completed_downloads(db_session, DOWNLOAD_PATH)

def init_db_and_reset_tasks():
    try:
        migrate_db.run_migrations()
    except Exception as e:
        logger.error(f"数据库迁移执行失败: {e}")
    models.Base.metadata.create_all(bind=db.engine)
    from .services.clipboard_service import get_thread_safe_db_session
    with get_thread_safe_db_session() as db_session:
        db_session.query(models.Video).filter(models.Video.download_status.in_(['pending', 'downloading'])).update({"download_status": "not_downloaded"}, synchronize_session=False)
        db_session.commit()
        logger.info(">>> 已重置未完成的下载任务状态")
        logger.info(">>> 数据库初始化完成")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:12243",
        "http://127.0.0.1:12243"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
app.include_router(auth_router)
app.include_router(bili_router)
app.include_router(local_router)
app.include_router(play_router)
app.include_router(system_router)
app.include_router(theme_router)
app.include_router(download_router)
app.include_router(stats_router)

# --- 图像防盗链代理接口 ---

from backend.services.cover_cache_service import get_cover_cache_service

@app.get("/api/proxy/image")
async def proxy_image(url: str):
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    allowed_hosts = ["i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com", "static.hdslb.com", "archive.biliimg.com"]
    if parsed.netloc not in allowed_hosts or parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=403, detail="Invalid image source")

    try:
        cover_service = get_cover_cache_service()
        image_data = await cover_service.get_cover(url)
        
        if image_data is None:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # 根据 URL 推断 Content-Type
        content_type = "image/jpeg"
        if url.endswith(".png"):
            content_type = "image/png"
        elif url.endswith(".webp"):
            content_type = "image/webp"
        
        return Response(
            content=image_data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=31536000"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image proxy failed: {e}")
        raise HTTPException(status_code=404, detail="Image not found")

# 静态文件挂载
from .core.paths import DATA_DIR
app.mount("/local_stickers", StaticFiles(directory=os.path.join(DATA_DIR, "stickers")), name="local_stickers")

BACKGROUNDS_DIR = os.path.join(DATA_DIR, "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)
app.mount("/local_backgrounds", StaticFiles(directory=BACKGROUNDS_DIR), name="local_backgrounds")

COVERS_DIR = os.path.join(DATA_DIR, "covers")
os.makedirs(COVERS_DIR, exist_ok=True)
app.mount("/local_covers", StaticFiles(directory=COVERS_DIR), name="local_covers")

class StaticFileCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/downloads"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        return response

app.add_middleware(StaticFileCORSMiddleware)
app.mount("/downloads", StaticFiles(directory=cleanup_service.DOWNLOAD_PATH), name="downloads")

# 挂载前端静态文件 (如果存在)
from .core.paths import BASE_DIR
from fastapi.responses import FileResponse

frontend_dist = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="frontend_assets")
    
    @app.get("/{catchall:path}")
    async def serve_frontend(catchall: str):
        if catchall.startswith("api/") or catchall.startswith("local_") or catchall.startswith("downloads/"):
            raise HTTPException(status_code=404)
        file_path = os.path.join(frontend_dist, catchall)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

# 生命周期管理
@app.on_event("startup")
async def startup_event():
    from .services.clipboard_service import watch_clipboard
    # 同步执行数据库初始化，确保表创建完成
    init_db_and_reset_tasks()
    
    # 启动后台异步文件校验任务，实现毫秒级启动
    Thread(target=async_verify_completed_downloads, daemon=True).start()
    
    Thread(target=watch_clipboard, args=(bili,), daemon=True).start()
    Thread(target=cleanup_service.run_cleanup_scheduler, daemon=True).start()

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
    logger.info(f"📡 [请求] {request.method} {request.url}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"❌ [错误] {e}")
        raise e

