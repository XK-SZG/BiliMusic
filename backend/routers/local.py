import os
import uuid
import json
import shutil
import tempfile
import zipfile
import io
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from ..database import models, db
from ..services import cleanup_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["local"])

class ImportVideoReq(BaseModel):
    bvid: str
    title: str
    owner: str
    pic: str
    duration: int = 0

@router.get("/api/local/videos")
def get_local_videos(db_session: Session = Depends(db.get_db)):
    """获取本地数据库中的所有视频"""
    try:
        videos = db_session.query(models.Video).options(
            joinedload(models.Video.tags),
            joinedload(models.Video.collections)
        ).order_by(models.Video.order_index.asc()).all()
    except Exception as e:
        logger.error(f"查询本地视频失败: {e}")
        return []
    
    result = []
    for v in videos:
        pic_url = v.pic
        if pic_url and not pic_url.startswith('http') and not pic_url.startswith('/'):
            pic_url = f"/local_covers/{pic_url}"

        result.append({
            "bvid": v.bvid,
            "title": v.title,
            "owner": v.owner,
            "pic": pic_url,
            "duration": v.duration,
            "score": v.score if v.score is not None else 5.0,
            "trim_start": v.trim_start,
            "trim_end": v.trim_end,
            "local_path": v.local_path,
            "added_at": v.added_at.isoformat() if v.added_at else None,
            "download_status": v.download_status,
            "is_local": bool(v.is_local),
            "tags": [{"id": t.id, "name": t.name} for t in (v.tags or [])],
            "collections": [{"id": c.id, "title": c.title} for c in (v.collections or [])]
        })
    return result

@router.get("/api/local/collections")
def list_local_collections(db_session: Session = Depends(db.get_db)):
    """获取本地媒体夹列表"""
    collections = db_session.query(models.Collection).filter(models.Collection.type == "local").order_by(models.Collection.order_index.asc()).all()
    
    has_unclassified = db_session.query(models.Video).filter(
        ~models.Video.collections.any(),
        models.Video.is_local == 1
    ).first() is not None
    
    result = [{"id": c.id, "title": c.title, "type": c.type} for c in collections]
    
    if has_unclassified:
        result.insert(0, {"id": "unclassified", "title": "未分类资源", "type": "virtual"})
        
    return result

@router.post("/api/local/collections")
def create_local_collection(title: str, db_session: Session = Depends(db.get_db)):
    """创建新的本地媒体夹"""
    new_id = str(uuid.uuid4())
    col = models.Collection(id=new_id, title=title, type="local")
    db_session.add(col)
    db_session.commit()
    return {"id": new_id, "title": title}

@router.delete("/api/local/collections/{col_id}")
def delete_collection(col_id: str, db_session: Session = Depends(db.get_db)):
    """删除本地媒体夹"""
    col = db_session.query(models.Collection).filter(models.Collection.id == col_id).first()
    if col:
        db_session.delete(col)
        db_session.commit()
    return {"status": "success"}

@router.post("/api/local/collections/reorder")
def reorder_collections(ids: List[str], db_session: Session = Depends(db.get_db)):
    """重新排序列媒体夹"""
    for index, col_id in enumerate(ids):
        db_session.query(models.Collection).filter(models.Collection.id == col_id).update({"order_index": index})
    db_session.commit()
    return {"status": "success"}

@router.post("/api/local/videos/reorder")
def reorder_videos(bvids: List[str], db_session: Session = Depends(db.get_db)):
    """重新排列视频"""
    for index, bvid in enumerate(bvids):
        db_session.query(models.Video).filter(models.Video.bvid == bvid).update({"order_index": index})
    db_session.commit()
    return {"status": "success"}

@router.post("/api/local/collections/{col_id}/import")
def import_bili_videos(col_id: str, videos: List[ImportVideoReq], db_session: Session = Depends(db.get_db)):
    """将B站视频导入到本地媒体夹"""
    try:
        target_col = db_session.query(models.Collection).filter(models.Collection.id == col_id).first()
        if not target_col:
            raise HTTPException(status_code=404, detail="目标媒体夹不存在")
        for v_data in videos:
            video = db_session.query(models.Video).filter(models.Video.bvid == v_data.bvid).first()
            if not video:
                video = models.Video(
                    bvid=v_data.bvid,
                    title=v_data.title,
                    owner=v_data.owner,
                    pic=v_data.pic,
                    duration=v_data.duration,
                    download_status='not_downloaded',
                    score=5.0
                )
                db_session.add(video)
            if video not in target_col.videos:
                target_col.videos.append(video)
        db_session.commit()
        return {"status": "success", "count": len(videos)}
    except Exception as e:
        logger.error(f"导入视频失败: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/local/collections/{col_id}/add")
def add_video_to_collection(col_id: str, bvid: str, db_session: Session = Depends(db.get_db)):
    """将已存在的视频关联到另一个媒体夹"""
    col = db_session.query(models.Collection).filter(models.Collection.id == col_id).first()
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if col and video and video not in col.videos:
        col.videos.append(video)
        db_session.commit()
    return {"status": "success"}

@router.post("/api/local/collections/{col_id}/remove")
def remove_video_from_collection(col_id: str, bvid: str, db_session: Session = Depends(db.get_db)):
    """从媒体夹中移除视频关联"""
    col = db_session.query(models.Collection).filter(models.Collection.id == col_id).first()
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if col and video and video in col.videos:
        col.videos.remove(video)
        db_session.commit()
    return {"status": "success"}

from ..services import media_service

@router.post("/api/local/import-file")
async def import_local_media(
    file: UploadFile = File(...),
    title: str = None,
    owner: str = "本地资源",
    collection_id: str = None,
    db_session: Session = Depends(db.get_db)
):
    """导入本地媒体文件"""
    return await media_service.process_local_media_import(
        file=file,
        title=title,
        owner=owner,
        collection_id=collection_id,
        db_session=db_session
    )

@router.post("/api/local/batch/delete-videos")
def batch_delete_permanently(bvids: List[str], db_session: Session = Depends(db.get_db)):
    """彻底删除视频记录及物理文件"""
    videos = db_session.query(models.Video).filter(models.Video.bvid.in_(bvids)).all()
    for v in videos:
        if v.local_path and os.path.exists(v.local_path):
            try: os.remove(v.local_path)
            except: pass
        if v.is_local and v.pic:
            from ..core.paths import DATA_DIR
            cover_path = os.path.join(DATA_DIR, "covers", v.pic)
            if os.path.exists(cover_path):
                try: os.remove(cover_path)
                except: pass
                
        db_session.delete(v)
    db_session.commit()
    return {"status": "success"}

class TagBatchReq(BaseModel):
    bvids: List[str]
    tag_name: str
    videos: List[ImportVideoReq] = []

@router.post("/api/batch/tags")
def batch_add_tags(req: TagBatchReq, db_session: Session = Depends(db.get_db)):
    """批量添加标签"""
    tag = db_session.query(models.Tag).filter(models.Tag.name == req.tag_name).first()
    if not tag:
        tag = models.Tag(name=req.tag_name)
        db_session.add(tag)
        db_session.commit()
    
    meta_map = {v.bvid: v for v in req.videos}
    for bvid in req.bvids:
        video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
        if not video:
            if bvid in meta_map:
                m = meta_map[bvid]
                video = models.Video(
                    bvid=bvid, title=m.title, owner=m.owner, pic=m.pic,
                    duration=m.duration, download_status='not_downloaded', score=5.0
                )
                db_session.add(video)
            else: continue
        if tag not in video.tags:
            video.tags.append(tag)
    db_session.commit()
    return {"status": "success", "tag": {"id": tag.id, "name": tag.name}}

@router.delete("/api/videos/{bvid}/tags/{tag_id}")
def remove_tag_from_video(bvid: str, tag_id: int, db_session: Session = Depends(db.get_db)):
    """移除单个视频的某个标签"""
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if video:
        tag_to_remove = next((t for t in video.tags if t.id == tag_id), None)
        if tag_to_remove:
            video.tags.remove(tag_to_remove)
            db_session.commit()
    return {"status": "success"}

@router.put("/api/videos/{bvid}/score")
def update_video_score(
    bvid: str, 
    score: float, 
    title: str = None, 
    owner: str = None, 
    pic: str = None, 
    duration: int = 0,
    db_session: Session = Depends(db.get_db)
):
    """更新视频评分"""
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if not video:
        if title:
            video = models.Video(
                bvid=bvid, title=title, owner=owner, pic=pic,
                duration=duration, download_status='not_downloaded',
                score=max(1.0, min(10.0, score))
            )
            db_session.add(video)
        else: return {"status": "ignored", "message": "视频未归档且缺失元数据"}
    else: video.score = max(1.0, min(10.0, score))
    db_session.commit()
    return {"bvid": bvid, "new_score": video.score, "status": "success"}

@router.post("/api/videos/{bvid}/metadata")
async def update_video_metadata(
    bvid: str,
    title: str = Form(None),
    owner: str = Form(None),
    cover: UploadFile = File(None),
    db_session: Session = Depends(db.get_db)
):
    """更新本地视频的标题、作者或封面图"""
    return await media_service.update_video_metadata_logic(
        bvid=bvid,
        title=title,
        owner=owner,
        cover=cover,
        db_session=db_session
    )

class TrimReq(BaseModel):
    start: float
    end: float

@router.post("/api/videos/{bvid}/trim")
def update_video_trim(bvid: str, req: TrimReq, db_session: Session = Depends(db.get_db)):
    """更新视频软裁剪区间"""
    video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频未在本地库中，请先归档")
    
    video.trim_start = req.start
    video.trim_end = req.end
    db_session.commit()
    return {"status": "success", "trim_start": video.trim_start, "trim_end": video.trim_end}

# --- 媒体库跨设备同步与备份 ---

class ExportLibraryReq(BaseModel):
    export_library: bool = True
    collection_ids: List[str]
    export_type: str
    export_queue: bool = True
    queue_data: list = []

def remove_temp_file(path: str):
    try:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    except Exception as e:
        logger.error(f"清理临时文件失败: {path}, {e}")

from ..services import backup_service

@router.post("/api/library/export")
def export_library(req: ExportLibraryReq, background_tasks: BackgroundTasks, db_session: Session = Depends(db.get_db)):
    try:
        temp_path = backup_service.export_library_to_zip(
            db_session=db_session,
            export_library=req.export_library,
            collection_ids=req.collection_ids,
            export_type=req.export_type,
            export_queue=req.export_queue,
            queue_data=req.queue_data
        )
        background_tasks.add_task(backup_service.remove_temp_file, temp_path)
        return FileResponse(
            temp_path,
            media_type="application/zip",
            filename=f"BiliMusic_Backup_{uuid.uuid4().hex[:8]}.zip"
        )
    except Exception as e:
        logger.error(f"导出媒体库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/library/import/analyze")
async def analyze_library_import(file: UploadFile = File(...), db_session: Session = Depends(db.get_db)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="必须上传 ZIP 文件")
    
    file_content = await file.read()
    try:
        result = backup_service.analyze_import_zip(file_content, db_session)
        return result
    except Exception as e:
        logger.error(f"解析导入文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ImportExecuteReq(BaseModel):
    session_id: str
    resolutions: dict # {"bvid": "overwrite" | "skip"}
    import_queue: bool

@router.post("/api/library/import/execute")
def execute_library_import(req: ImportExecuteReq, background_tasks: BackgroundTasks, db_session: Session = Depends(db.get_db)):
    try:
        queue_data, temp_dir = backup_service.execute_import_logic(
            session_id=req.session_id,
            resolutions=req.resolutions,
            import_queue=req.import_queue,
            db_session=db_session
        )
        background_tasks.add_task(backup_service.remove_temp_file, temp_dir)
        return {
            "status": "success",
            "queue_data": queue_data
        }
    except Exception as e:
        logger.error(f"执行导入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
