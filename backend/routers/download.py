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

@router.post("/cancel/{bvid}")
def cancel_download(bvid: str, db_session: Session = Depends(db.get_db)):
    """取消下载任务"""
    try:
        video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
        if not video:
            raise HTTPException(status_code=404, detail="视频不存在")
        
        if video.download_status in ['pending', 'downloading']:
            video.download_status = 'not_downloaded'
            # 添加到取消标志集合
            download_service.cancelled_tasks.add(bvid)
            # 清除进度缓存
            if bvid in download_service.progress_cache:
                del download_service.progress_cache[bvid]
            db_session.commit()
            logger.info(f"已取消下载任务: {bvid}")
            return {"message": "已取消下载"}
        else:
            return {"message": "任务不在下载队列中"}
    except Exception as e:
        logger.error(f"取消下载失败: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cancel-all")
def cancel_all_downloads(db_session: Session = Depends(db.get_db)):
    """取消所有下载任务"""
    try:
        videos = db_session.query(models.Video).filter(
            models.Video.download_status.in_(['pending', 'downloading'])
        ).all()
        
        count = 0
        for video in videos:
            video.download_status = 'not_downloaded'
            # 添加到取消标志集合
            download_service.cancelled_tasks.add(video.bvid)
            # 清除进度缓存
            if video.bvid in download_service.progress_cache:
                del download_service.progress_cache[video.bvid]
            count += 1
        
        # 清空下载队列
        while not download_service.download_queue.empty():
            try:
                download_service.download_queue.get_nowait()
                download_service.download_queue.task_done()
            except:
                break
        
        db_session.commit()
        logger.info(f"已取消 {count} 个下载任务并清空队列")
        return {"message": f"已取消 {count} 个下载任务", "count": count}
    except Exception as e:
        logger.error(f"批量取消下载失败: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

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
