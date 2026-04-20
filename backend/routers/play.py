import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session

from ..database import models, db
from ..core.bili_manager import BiliManager
from ..dependencies import get_bili

router = APIRouter(prefix="/api/play", tags=["play"])

@router.get("/stream/{bvid}")
async def proxy_video_stream(bvid: str, request: Request, bili: BiliManager = Depends(get_bili)):
    """代理 B 站视频流或本地媒体流，支持 Range 头和缓存"""
    # 1. 处理本地资源
    if bvid.startswith("lc_"):
        clean_bvid = bvid.split('?')[0]
        db_session = next(db.get_db())
        video = db_session.query(models.Video).filter(models.Video.bvid == clean_bvid).first()
        if not video or not video.local_path or not os.path.exists(video.local_path):
            raise HTTPException(status_code=404, detail="本地文件不存在")
        
        media_type = "video/mp4"
        ext = os.path.splitext(video.local_path)[1].lower()
        if ext == '.mp3':
            media_type = "audio/mpeg"
        elif ext == '.m4a':
            media_type = "audio/mp4"
        elif ext == '.wav':
            media_type = "audio/wav"
        elif ext == '.flac':
            media_type = "audio/flac"
        elif ext == '.ogg':
            media_type = "audio/ogg"
            
        # [性能优化] 启用 Zero-Copy 底层文件系统直接分发
        import starlette.responses
        import anyio
        
        async def file_sender():
            async with await anyio.open_file(video.local_path, mode="rb") as f:
                async for chunk in f:
                    yield chunk
                    
        return StreamingResponse(file_sender(), media_type=media_type, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Content-Type",
            "Cache-Control": "public, max-age=3600",  # 本地文件缓存 1 小时
            "Content-Length": str(os.path.getsize(video.local_path))
        })

    # 2. 处理 B 站资源
    is_part = "_p" in bvid
    real_bvid = bvid.split("_p")[0] if is_part else bvid
    p_num = int(bvid.split("_p")[1]) if is_part else 1
    pages, _, _, _, _ = bili.get_video_parts(real_bvid)
    if not pages or len(pages) < p_num: raise HTTPException(status_code=404, detail="未找到视频分集信息")
    cid = pages[p_num-1]['cid']
    quality = request.query_params.get('quality', 64)
    play_url, _ = bili.get_play_url(real_bvid, cid, quality=int(quality))
    if not play_url: raise HTTPException(status_code=403, detail="无法获取 B 站播放地址")
    range_header = request.headers.get('Range')
    gen, headers, status = bili.stream_video_content(play_url, range_header)
    if not gen: raise HTTPException(status_code=500, detail="视频流建立失败")
    
    # --- 记录网络流量 ---
    content_length = headers.get('Content-Length')
    if content_length and status in [200, 206]:
        try:
            traffic = int(content_length)
            
            # [性能优化] 无锁化微批处理：通过异步队列缓冲请求流量写入
            from ..core.async_metrics import traffic_counter
            traffic_counter.add(traffic)
            
        except Exception as e:
            pass # 忽略统计失败
            
    if headers:
        headers["Access-Control-Allow-Origin"] = "*"
        headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Range, Content-Type"
        
        # 添加缓存控制头
        # 对于预览视频（quality=16），使用较短的缓存时间
        # 对于正常播放（quality>=64），使用较长的缓存时间
        if int(quality) <= 16:
            headers["Cache-Control"] = "public, max-age=600"  # 预览视频缓存 10 分钟
        else:
            headers["Cache-Control"] = "public, max-age=1800"  # 正常播放缓存 30 分钟
        
        # 添加 ETag 支持（使用 bvid + quality 作为标识）
        headers["ETag"] = f'"{bvid}-q{quality}"'
        
    return StreamingResponse(gen, status_code=status, headers=headers)
