from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from ..core.bili_manager import BiliManager
from ..database import db
from ..services.sync_service import sync_bili_collection
from ..dependencies import get_bili

router = APIRouter(prefix="/api/bili", tags=["bili"])

@router.get("/folders")
def get_bili_folders(bili: BiliManager = Depends(get_bili)):
    """获取B站收藏夹列表"""
    folders = bili.get_fav_folders()
    return {"code": 0, "data": folders}

@router.get("/folder/{media_id}/videos")
def get_folder_videos_api(media_id: str, page: int = 1, bili: BiliManager = Depends(get_bili)):
    """获取B站收藏夹内的视频列表"""
    try:
        data = bili.get_folder_videos(media_id, page)
        if not data:
            return {"medias": [], "has_more": False}
        
        medias = data.get("medias", [])
        has_more = data.get("has_more", False)
        if len(medias) >= 20:
            has_more = True
            
        return {
            "medias": medias,
            "has_more": has_more
        }
    except Exception as e:
        return {"medias": [], "has_more": False}

@router.get("/sync/{media_id}")
async def sync_folder(media_id: str, bili: BiliManager = Depends(get_bili), database: Session = Depends(db.get_db)):
    """流式同步收藏夹到本地数据库"""
    return StreamingResponse(
        sync_bili_collection(database, bili, media_id),
        media_type="text/event-stream"
    )

@router.get("/video/{bvid}/parts")
def get_video_parts_endpoint(bvid: str, bili: BiliManager = Depends(get_bili)):
    """获取视频的分P信息"""
    pages, main_title, main_pic, owner_name = bili.get_video_parts(bvid)
    if not pages:
        return {"parts": []}
    result = []
    for p in pages:
        result.append({
            "id": f"{bvid}_p{p['page']}",
            "title": f"{main_title} P{p['page']}: {p['part']}",
            "page": p['page'],
            "duration": p.get('duration', 0)
        })
    return {"parts": result}
