# -*- coding: utf-8 -*-
# Path: backend/main.py

import os
import logging
from threading import Thread
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .database import models, db
from . import migrate_db
from .services import cleanup_service
from .dependencies import bili
from .routers import auth_router, bili_router, local_router, play_router, system_router, theme_router, download_router

# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="BiliMusic API")

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
        logger.info(">>> 已重置未完成的下载任务状态并完成数据库初始化")

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

# --- 图像防盗链代理接口 ---

@app.get("/api/proxy/image")
def proxy_image(url: str):
    import requests
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    allowed_hosts = ["i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com", "static.hdslb.com", "archive.biliimg.com"]
    if parsed.netloc not in allowed_hosts or parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=403, detail="Invalid image source")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        return Response(
            content=resp.content, 
            media_type=resp.headers.get("Content-Type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=31536000"}
        )
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
    Thread(target=watch_clipboard, args=(bili,), daemon=True).start()
    Thread(target=cleanup_service.run_cleanup_scheduler, daemon=True).start()

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

