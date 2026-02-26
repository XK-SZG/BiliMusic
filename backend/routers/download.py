from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.orm import Session
from ..database import models, db
from ..services import download_service
from ..dependencies import get_downloader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/download", tags=["download"])

@router.post("/add/{bvid}")
def add_to_download_queue(bvid: str, quality: int = 80, downloader = Depends(get_downloader)):
    """加入下载队列，支持指定清晰度"""
    success = downloader.add_to_queue(bvid, quality=quality)
    if not success:
        raise HTTPException(status_code=400, detail="添加失败，可能已在队列中或已下载")
    return {"message": "已加入下载队列"}

@router.get("/status")
def get_download_status(db_session: Session = Depends(db.get_db)):
    """获取下载进度"""
    try:
        processing = db_session.query(models.Video).filter(
            models.Video.download_status.in_(['pending', 'downloading'])
        ).all()
        result = []
        for v in processing:
            item = {
                "bvid": v.bvid,
                "title": v.title,
                "status": v.download_status,
                "progress": download_service.progress_cache.get(v.bvid, 0)
            }
            result.append(item)
        return {"tasks": result, "queue_size": download_service.download_queue.qsize()}
    except Exception as e:
        logger.error(f"查询下载状态失败: {e}")
        return {"tasks": [], "queue_size": 0}
