import os
import hashlib
import subprocess
import uuid
import logging
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from ..database import models
from . import cleanup_service

logger = logging.getLogger(__name__)

async def process_local_media_import(
    file: UploadFile, 
    title: str = None, 
    owner: str = "本地资源",
    collection_id: str = None,
    db_session: Session = None
):
    """处理本地媒体文件导入逻辑"""
    file_content = await file.read()
    file_hash = hashlib.md5(file_content).hexdigest()
    pseudo_bvid = f"lc_{file_hash[:10]}"
    
    existing = db_session.query(models.Video).filter(models.Video.bvid == pseudo_bvid).first()
    
    if existing:
        if collection_id and collection_id != 'unclassified':
            col = db_session.query(models.Collection).filter(models.Collection.id == collection_id).first()
            if col and existing not in col.videos:
                col.videos.append(existing)
                db_session.commit()
        return {"status": "exists", "bvid": pseudo_bvid}

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.mp3', '.m4a', '.wav', '.flac', '.ogg', '.mp4', '.mkv', '.avi', '.flv']:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
        
    save_filename = f"{pseudo_bvid}{ext}"
    save_path = os.path.abspath(os.path.join(cleanup_service.DOWNLOAD_PATH, save_filename))
    
    if not save_path.startswith(os.path.abspath(cleanup_service.DOWNLOAD_PATH)):
        raise HTTPException(status_code=403, detail="非法文件路径")
    
    with open(save_path, "wb") as f:
        f.write(file_content)

    duration = 0
    cover_filename = f"{pseudo_bvid}_cover.jpg"
    from ..core.paths import DATA_DIR
    cover_path = os.path.join(DATA_DIR, "covers", cover_filename)
    os.makedirs(os.path.dirname(cover_path), exist_ok=True)
    
    is_audio_only = ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg']

    try:
        import platform
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = subprocess.CREATE_NO_WINDOW

        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', save_path
        ]
        duration_out = subprocess.check_output(cmd, creationflags=creationflags).decode().strip()
        duration = int(float(duration_out))
        
        if is_audio_only:
            cmd_img = ['ffmpeg', '-y', '-i', save_path, '-an', '-vcodec', 'copy', cover_path]
        else:
            cmd_img = ['ffmpeg', '-y', '-i', save_path, '-ss', '00:00:01', '-vframes', '1', cover_path]
            
        subprocess.run(cmd_img, capture_output=True, creationflags=creationflags)
        
        if not os.path.exists(cover_path) or os.path.getsize(cover_path) == 0:
            cover_filename = None
            if os.path.exists(cover_path):
                os.remove(cover_path)
    except Exception as e:
        logger.warning(f"FFmpeg 处理失败: {pseudo_bvid}, {e}")
        cover_filename = None

    new_video = models.Video(
        bvid=pseudo_bvid,
        title=title or os.path.splitext(file.filename)[0],
        owner=owner,
        pic=cover_filename,
        duration=duration,
        local_path=save_path,
        download_status='completed',
        is_local=1,
        score=5.0
    )
    db_session.add(new_video)
    
    if collection_id and collection_id != 'unclassified':
        col = db_session.query(models.Collection).filter(models.Collection.id == collection_id).first()
        if col:
            col.videos.append(new_video)

    db_session.commit()
    
    return {"status": "success", "bvid": pseudo_bvid, "title": new_video.title}

async def update_video_metadata_logic(
    bvid: str,
    title: str = None,
    owner: str = None,
    cover: UploadFile = None,
    db_session: Session = None
):
    """更新本地视频的标题、作者或封面图的业务逻辑"""
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    
    if title is not None: video.title = title
    if owner is not None: video.owner = owner
    
    if cover and cover.filename:
        ext = os.path.splitext(cover.filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            safe_filename = f"{bvid}_cover_{uuid.uuid4().hex[:8]}{ext}"
            from ..core.paths import DATA_DIR
            cover_path = os.path.join(DATA_DIR, "covers", safe_filename)
            os.makedirs(os.path.dirname(cover_path), exist_ok=True)
            
            content = await cover.read()
            with open(cover_path, "wb") as f:
                f.write(content)
            
            if video.pic and not video.pic.startswith('http'):
                old_path = os.path.join(DATA_DIR, "covers", video.pic)
                if os.path.exists(old_path):
                    try: os.remove(old_path)
                    except: pass
            
            video.pic = safe_filename
            
    db_session.commit()
    
    pic_url = video.pic
    if pic_url and not pic_url.startswith('http'):
        pic_url = f"/local_covers/{pic_url}"

    return {"status": "success", "title": video.title, "owner": video.owner, "pic": pic_url}
