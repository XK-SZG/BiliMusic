import os
import json
import base64
import logging
import platform
import subprocess
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..database import models, db
from ..services import cleanup_service, download_service
from ..dependencies import get_bili, get_downloader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

from ..core.log_manager import memory_handler

@router.get("/logs")
def get_system_logs():
    """获取系统运行日志"""
    return {"logs": memory_handler.get_logs()}

@router.get("/events")
async def system_events(request: Request):
    """SSE 全局事件总线（替代前端轮询）"""
    import asyncio
    
    async def event_publisher():
        from ..services.clipboard_service import pending_bvids, pending_lock
        from ..services import download_service
        from ..database import db, models
        
        last_clipboard_bvids = []
        last_download_state = None
        
        while True:
            if await request.is_disconnected():
                break
                
            # 1. 剪贴板状态检测
            with pending_lock:
                current_bvids = list(pending_bvids)
            if current_bvids != last_clipboard_bvids:
                last_clipboard_bvids = current_bvids
                if current_bvids:
                    # 通知前端有新的剪贴板数据
                    yield f"event: clipboard_pending\ndata: {json.dumps({'count': len(current_bvids)})}\n\n"
            
            # 2. 下载状态检测
            try:
                # 使用瞬时 session 避免长事务阻塞
                with db.SessionLocal() as session:
                    processing = session.query(models.Video).filter(
                        models.Video.download_status.in_(['pending', 'downloading'])
                    ).all()
                    
                    tasks = []
                    for v in processing:
                        tasks.append({
                            "bvid": v.bvid,
                            "title": v.title,
                            "status": v.download_status,
                            "progress": download_service.progress_cache.get(v.bvid, 0)
                        })
                    
                    current_download_state = {
                        "tasks": tasks,
                        "queue_size": download_service.download_queue.qsize()
                    }
                    
                    if current_download_state != last_download_state:
                        last_download_state = current_download_state
                        yield f"event: download_status\ndata: {json.dumps(current_download_state)}\n\n"
            except Exception as e:
                logger.error(f"SSE 下载状态查询异常: {e}")
                
            yield ": ping\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_publisher(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

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
    """重置软件，清空所有数据但保留默认主题的静态资源"""
    from ..services import system_service
    try:
        system_service.execute_factory_reset(db_session, bili)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"重置软件失败: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clipboard/pending")
def get_pending_bvids(bili = Depends(get_bili)):
    """获取剪贴板检测到的待确认 BV 号列表（包含视频信息）"""
    from ..services.clipboard_service import pending_bvids, pending_lock
    with pending_lock:
        bvids = list(pending_bvids)
    
    # 获取每个 BV 号的详细信息
    videos = []
    for bvid in bvids:
        try:
            # 检查是否为分集视频（格式：BV号_pN）
            is_part = "_p" in bvid
            if is_part:
                clean_bvid, part_str = bvid.split("_p")
                part_num = int(part_str)
            else:
                clean_bvid = bvid
                part_num = None
            
            # 获取视频基本信息
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={clean_bvid}"
            res = bili.session.get(url).json()
            if res.get('code') == 0:
                data = res['data']
                
                # 如果是分集视频，获取对应分集的信息
                if is_part and part_num:
                    pages = data.get('pages', [])
                    if part_num <= len(pages):
                        part_info = pages[part_num - 1]
                        title = f"{data['title']} - P{part_num}: {part_info['part']}"
                        duration = part_info['duration']
                    else:
                        title = f"{data['title']} - P{part_num}"
                        duration = data['duration']
                else:
                    title = data['title']
                    duration = data['duration']
                
                videos.append({
                    'bvid': bvid,
                    'title': title,
                    'owner': data['owner']['name'],
                    'owner_face': data['owner']['face'],
                    'pic': data['pic'],
                    'duration': duration,
                    'is_part': is_part,
                    'part_num': part_num if is_part else None,
                    'clean_bvid': clean_bvid
                })
        except Exception as e:
            logger.error(f"获取 {bvid} 信息失败: {e}")
            # 如果获取失败，仍然返回基本信息
            videos.append({
                'bvid': bvid,
                'title': '获取信息失败',
                'owner': '未知',
                'owner_face': '',
                'pic': '',
                'duration': 0,
                'is_part': False,
                'part_num': None,
                'clean_bvid': bvid
            })
    
    return {"videos": videos}

@router.post("/clipboard/confirm")
def confirm_bvid(request_data: dict, db_session: Session = Depends(db.get_db), bili = Depends(get_bili)):
    """确认添加剪贴板检测到的 BV 号（仅从待确认列表移除，不直接入库）"""
    from ..services.clipboard_service import pending_bvids, pending_lock
    bvid = request_data.get("bvid")
    collection_id = request_data.get("collection_id")  # 可选的媒体库 ID
    client_title = request_data.get("title")  # 前端传入的标题（可能是用户选择的分集）
    client_duration = request_data.get("duration")  # 前端传入的时长
    
    if not bvid:
        raise HTTPException(status_code=400, detail="缺少 bvid 参数")
    
    # 从待确认列表中移除
    with pending_lock:
        if bvid in pending_bvids:
            pending_bvids.remove(bvid)
    
    # 如果提供了 collection_id，则直接导入到指定媒体库
    if collection_id:
        try:
            # 解析 bvid，判断是否为分集视频
            is_part = "_p" in bvid
            if is_part:
                clean_bvid, part_str = bvid.split("_p")
                part_num = int(part_str)
            else:
                clean_bvid = bvid
                part_num = None
            
            # 获取视频信息
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={clean_bvid}"
            res = bili.session.get(url).json()
            
            if res.get('code') != 0:
                raise HTTPException(status_code=400, detail=f"无法获取视频信息: {res.get('message')}")
            
            bili_data = res['data']
            
            # 如果是分集视频，获取对应分集的信息
            if is_part and part_num:
                pages = bili_data.get('pages', [])
                if part_num <= len(pages):
                    part_info = pages[part_num - 1]
                    title = f"{bili_data['title']} - P{part_num}: {part_info['part']}"
                    duration = part_info['duration']
                else:
                    title = f"{bili_data['title']} - P{part_num}"
                    duration = bili_data['duration']
            else:
                title = bili_data['title']
                duration = bili_data['duration']
            
            # 优先使用前端传入的标题和时长（如果用户在预览弹窗中切换了分集）
            if client_title:
                title = client_title
            if client_duration is not None:
                duration = client_duration

            # 检查视频是否已存在
            video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
            if not video:
                video = models.Video(
                    bvid=bvid,
                    title=title,
                    owner=bili_data['owner']['name'],
                    pic=bili_data['pic'],
                    duration=duration,
                    download_status='not_downloaded',
                    score=5.0
                )
                db_session.add(video)
            
            # 添加到指定媒体库
            target_col = db_session.query(models.Collection).filter(models.Collection.id == collection_id).first()
            if not target_col:
                raise HTTPException(status_code=404, detail="目标媒体库不存在")
            
            if video not in target_col.videos:
                target_col.videos.append(video)
            
            db_session.commit()
            return {"status": "success", "message": f"视频已添加到媒体库", "need_select": False}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"添加视频失败: {e}")
            db_session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # 没有提供 collection_id，返回需要选择媒体库的标识
        return {"status": "success", "message": "请选择媒体库", "need_select": True, "bvid": bvid}

@router.post("/clipboard/dismiss")
def dismiss_bvid(data: dict):
    """忽略剪贴板检测到的 BV 号"""
    from ..services.clipboard_service import pending_bvids, pending_lock
    bvid = data.get("bvid")
    if not bvid:
        raise HTTPException(status_code=400, detail="缺少 bvid 参数")
    
    with pending_lock:
        if bvid in pending_bvids:
            pending_bvids.remove(bvid)
    
    return {"status": "success", "message": f"已忽略 {bvid}"}

@router.post("/clipboard/pause")
def pause_clipboard():
    """暂停剪贴板监听"""
    from ..services import clipboard_service
    clipboard_service.is_clipboard_paused = True
    logger.info("剪贴板监听已暂停")
    return {"status": "success", "message": "剪贴板监听已暂停"}

@router.post("/clipboard/resume")
def resume_clipboard():
    """恢复剪贴板监听"""
    from ..services import clipboard_service
    clipboard_service.is_clipboard_paused = False
    logger.info("剪贴板监听已恢复")
    return {"status": "success", "message": "剪贴板监听已恢复"}

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
