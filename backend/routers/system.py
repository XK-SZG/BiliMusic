import os
import json
import base64
import logging
import platform
import subprocess
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..database import models, db
from ..services import cleanup_service, download_service
from ..dependencies import get_bili, get_downloader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

@router.post("/shutdown")
def system_shutdown():
    """执行系统关机指令"""
    from ..services import system_service
    try:
        system_service.execute_system_shutdown()
        return {"status": "success", "message": "指令已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/factory-reset")
def factory_reset(db_session: Session = Depends(db.get_db), bili = Depends(get_bili)):
    """恢复出厂设置，清空所有数据但保留默认主题的静态资源"""
    from ..services import system_service
    try:
        system_service.execute_factory_reset(db_session, bili)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"恢复出厂设置失败: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/fonts")
def get_system_fonts():
    """获取本地系统已安装字体列表"""
    import platform
    fonts = []
    if platform.system() == "Windows":
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
            for i in range(0, winreg.QueryInfoKey(key)[1]):
                name, value, _ = winreg.EnumValue(key, i)
                clean_name = name.replace(" (TrueType)", "").replace(" (OpenType)", "")
                
                if not os.path.isabs(value):
                    path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', value)
                else:
                    path = value
                    
                if path.lower().endswith(('.ttf', '.otf', '.ttc')):
                    fonts.append({"name": clean_name, "path": path})
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"获取系统字体失败: {e}")
    else:
        font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts")
        ]
        for d in font_dirs:
            if os.path.exists(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(('.ttf', '.otf', '.ttc')):
                            fonts.append({"name": os.path.splitext(f)[0], "path": os.path.join(root, f)})
                            
    unique_fonts = {f['name']: f for f in fonts}.values()
    sorted_fonts = sorted(unique_fonts, key=lambda x: x['name'])
    return {"fonts": sorted_fonts}

@router.post("/fonts/upload")
async def upload_font_file(file: UploadFile = File(...)):
    """上传自定义字体文件"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.ttf', '.woff', '.woff2', '.otf']:
        raise HTTPException(status_code=400, detail="不支持的字体格式")
    
    from ..core.paths import DATA_DIR
    fonts_dir = os.path.join(DATA_DIR, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    
    file_path = os.path.join(fonts_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    return {"status": "success", "filename": file.filename, "url": f"/api/system/fonts/raw/{file.filename}"}

@router.get("/fonts/raw/{filename}")
async def get_font_raw(filename: str):
    """读取已上传的原始字体文件"""
    from ..core.paths import DATA_DIR
    fonts_dir = os.path.abspath(os.path.join(DATA_DIR, "fonts"))
    file_path = os.path.abspath(os.path.join(fonts_dir, filename))
    
    if not file_path.startswith(fonts_dir):
        raise HTTPException(status_code=403, detail="Illegal file path")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    def iterfile():
        with open(file_path, mode="rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type="application/x-font-ttf")

@router.get("/stickers")
def get_system_stickers():
    """获取本地系统已上传的贴画列表"""
    from ..core.paths import DATA_DIR
    stickers_dir = os.path.join(DATA_DIR, "stickers")
    os.makedirs(stickers_dir, exist_ok=True)
    
    try:
        files = os.listdir(stickers_dir)
        stickers = []
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                stickers.append({
                    "name": f,
                    "url": f"/local_stickers/{f}"
                })
        stickers.sort(key=lambda x: os.path.getmtime(os.path.join(stickers_dir, x['name'])), reverse=True)
        return {"stickers": stickers}
    except Exception as e:
        return {"error": str(e), "stickers": []}

@router.post("/stickers/upload")
async def upload_sticker_file(file: UploadFile = File(...)):
    import uuid
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        raise HTTPException(status_code=400, detail="不支持的图片格式")
    
    from ..core.paths import DATA_DIR
    stickers_dir = os.path.join(DATA_DIR, "stickers")
    os.makedirs(stickers_dir, exist_ok=True)
    
    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(stickers_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    return {
        "status": "success", 
        "filename": safe_filename, 
        "url": f"/local_stickers/{safe_filename}"
    }

@router.get("/stickers/bundle")
def get_stickers_bundle():
    """将所有本地贴画一次性打包为 Base64 束"""
    from ..core.paths import DATA_DIR
    stickers_dir = os.path.join(DATA_DIR, "stickers")
    if not os.path.exists(stickers_dir):
        return {}
    
    bundle = {}
    for filename in os.listdir(stickers_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            path = os.path.join(stickers_dir, filename)
            try:
                with open(path, "rb") as f:
                    content = f.read()
                    ext = filename.split('.')[-1].lower()
                    mime = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                    b64_data = base64.b64encode(content).decode()
                    bundle[f"/local_stickers/{filename}"] = f"data:{mime};base64,{b64_data}"
            except: continue
    return bundle

@router.get("/backgrounds")
def get_system_backgrounds():
    """获取本地系统已上传的背景图列表"""
    from ..core.paths import DATA_DIR
    bg_dir = os.path.join(DATA_DIR, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    
    try:
        files = os.listdir(bg_dir)
        backgrounds = []
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                backgrounds.append({
                    "name": f,
                    "url": f"/local_backgrounds/{f}"
                })
        backgrounds.sort(key=lambda x: os.path.getmtime(os.path.join(bg_dir, x['name'])), reverse=True)
        return {"backgrounds": backgrounds}
    except Exception as e:
        return {"error": str(e), "backgrounds": []}

@router.post("/backgrounds/upload")
async def upload_background_file(file: UploadFile = File(...)):
    import uuid
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
        raise HTTPException(status_code=400, detail="不支持的图片格式")
    
    from ..core.paths import DATA_DIR
    bg_dir = os.path.join(DATA_DIR, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    
    safe_filename = f"bg_{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(bg_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    return {
        "status": "success", 
        "filename": safe_filename, 
        "url": f"/local_backgrounds/{safe_filename}"
    }

@router.delete("/backgrounds/{filename}")
async def delete_background_file(filename: str):
    from ..core.paths import DATA_DIR
    bg_dir = os.path.abspath(os.path.join(DATA_DIR, "backgrounds"))
    file_path = os.path.abspath(os.path.join(bg_dir, filename))
    
    if not file_path.startswith(bg_dir):
        raise HTTPException(status_code=403, detail="Illegal file path")
        
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="文件不存在")

@router.post("/particles/upload")
async def upload_particle_file(file: UploadFile = File(...)):
    import uuid
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']:
        raise HTTPException(status_code=400, detail="不支持的图片格式")
    
    from ..core.paths import DATA_DIR
    particles_dir = os.path.join(DATA_DIR, "particles")
    os.makedirs(particles_dir, exist_ok=True)
    
    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(particles_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    return {
        "status": "success", 
        "filename": safe_filename, 
        "url": f"/api/system/particles/raw/{safe_filename}"
    }

@router.get("/particles/raw/{filename}")
async def get_particle_raw(filename: str):
    """读取已上传的粒子图片"""
    from ..core.paths import DATA_DIR
    particles_dir = os.path.abspath(os.path.join(DATA_DIR, "particles"))
    file_path = os.path.abspath(os.path.join(particles_dir, filename))
    
    if not file_path.startswith(particles_dir):
        raise HTTPException(status_code=403, detail="Illegal file path")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    ext = os.path.splitext(filename)[1].lower()
    media_type = "image/png"
    if ext in ['.jpg', '.jpeg']: media_type = "image/jpeg"
    elif ext == '.gif': media_type = "image/gif"
    elif ext == '.webp': media_type = "image/webp"
    elif ext == '.svg': media_type = "image/svg+xml"

    def iterfile():
        with open(file_path, mode="rb") as f:
            yield from f

    headers = {"Cache-Control": "public, max-age=31536000"}
    if ext == '.svg':
        headers["Content-Security-Policy"] = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'"

    return StreamingResponse(iterfile(), media_type=media_type, headers=headers)
