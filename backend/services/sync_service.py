import json
from sqlalchemy.orm import Session
from ..database.models import Video, Collection
from ..core.bili_manager import BiliManager


def sync_bili_collection(db: Session, bili: BiliManager, media_id: str):
    """生成器函数：同步收藏夹内容，并逐条返回同步状态（SSE 数据帧）。"""
    # 1. 获取收藏夹元数据并更新/创建本地记录
    # 这里需要先获取该收藏夹的名称等信息
    # 简化处理：假设收藏夹已存在或在此处创建
    col = db.query(Collection).filter(Collection.id == media_id).first()
    if not col:
        # 实际开发中可以从 get_fav_folders 中获取标题
        col = Collection(id=media_id, title=f"B站收藏夹_{media_id}", type="bili")
        db.add(col)
        db.commit()

    # 2. 流式获取 B 站数据
    #
    # [修复] 原实现调用 `bili.stream_fav_content(media_id)`，但 BiliManager 从未定义过
    # 该方法（也没有 __getattr__），生成器在第一次迭代就抛 AttributeError。
    # 由于响应头已经以 200 + text/event-stream 发出，客户端只会看到一个被截断的流，
    # 「收藏夹同步」100% 失败且界面没有任何可见错误。这里改为复用既有的分页接口
    # `get_folder_videos()` 逐页拉取，保持原有的「边取边入库」流式语义。
    page = 1
    page_size = 20

    while True:
        try:
            data = bili.get_folder_videos(media_id, page=page, page_size=page_size)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'获取收藏夹失败: {e}'}, ensure_ascii=False)}\n\n"
            return

        if not data:
            if page == 1:
                # get_folder_videos 在「未登录 / 接口报错」时返回 None，
                # 必须与「收藏夹为空」区分开，否则会静默同步出空结果
                yield f"data: {json.dumps({'status': 'error', 'message': '无法读取收藏夹（登录状态可能已失效）'}, ensure_ascii=False)}\n\n"
            break

        medias = data.get('medias') or []
        if not medias:
            break

        for item in medias:
            real_bvid = item.get('bv_id') or item.get('bvid')
            if not real_bvid:
                continue
            page_count = item.get('page', 1)

            # 准备要入库的视频列表
            videos_to_add = []

            # 情况 A: 单个视频 (绝大多数情况)
            if page_count <= 1:
                videos_to_add.append({
                    "id": real_bvid,  # ID 就是 BV 号
                    "title": item.get('title'),
                    "pic": item.get('cover'),
                    "owner": item.get('upper', {}).get('name', 'Unknown'),
                    "duration": item.get('duration', 0)
                })

            # 情况 B: 多分集视频 (需要额外请求一次详情获取分集标题)
            else:
                # [修复] get_video_parts 返回 5 个值
                # (pages, title, pic, owner_name, owner_face)，原先只解包 4 个，
                # 于是任何含多分集视频的收藏夹都会在此抛
                # ValueError: too many values to unpack，同步中途中断并留下半同步状态。
                parts = bili.get_video_parts(real_bvid)
                pages, main_title, main_pic, owner_name = parts[0], parts[1], parts[2], parts[3]
                if not pages:
                    continue  # 获取失败跳过

                for p in pages:
                    # 构造复合 ID: BVxxx_p1
                    part_id = f"{real_bvid}_p{p['page']}"
                    # 构造组合标题: 主标题 P1: 分集标题
                    part_title = f"{main_title} P{p['page']}: {p['part']}"

                    videos_to_add.append({
                        "id": part_id,
                        "title": part_title,
                        "pic": main_pic,  # 分集通常共用封面
                        "owner": owner_name,
                        "duration": p.get('duration', 0)
                    })

            # --- 执行入库逻辑 ---
            for v_data in videos_to_add:
                # 1. 检查是否存在
                video = db.query(Video).filter(Video.bvid == v_data['id']).first()

                if not video:
                    video = Video(
                        bvid=v_data['id'],  # 注意：这里存的是 BV..._pX
                        title=v_data['title'],
                        owner=v_data['owner'],
                        pic=v_data['pic'],
                        duration=v_data['duration'],
                        download_status='not_downloaded',
                        score=5.0
                    )
                    db.add(video)

                # 2. 建立关联
                if video not in col.videos:
                    col.videos.append(video)
                    # 推送进度日志
                    yield f"data: {json.dumps({'status': 'syncing', 'title': v_data['title']}, ensure_ascii=False)}\n\n"

            db.commit()

        if not data.get('has_more'):
            break
        page += 1

    yield "data: {\"status\": \"completed\"}\n\n"
