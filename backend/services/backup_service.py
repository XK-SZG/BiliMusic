import os
import re
import json
import uuid
import shutil
import tempfile
import zipfile
import io
import logging
from typing import List, Set
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from ..database import models
from . import cleanup_service

logger = logging.getLogger(__name__)

#: 导入会话 id 的合法形态：只允许字母/数字/下划线/连字符，长度有界。
#: 关键约束是「不得含路径分隔符与 `..`」，真正的安全边界由
#: resolve_import_temp_dir() 的路径归属校验保证。
_SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')

#: 导入会话临时目录的前缀
_IMPORT_TEMP_PREFIX = 'bilimusic_import_'


def resolve_import_temp_dir(session_id: str) -> str:
    """把客户端传来的 session_id 解析成**受控**的临时目录路径。

    [修复] 原实现直接拼接：
        temp_dir = os.path.join(tempfile.gettempdir(), f"bilimusic_import_{session_id}")
    session_id 来自请求体且没有任何校验，`os.path.join` 又接受 `/` 与 `..`。
    传 `x/../../../../../../Users/<user>/Documents` 时，Windows 会按词法归一化
    `..`，该路径真实存在，随后 execute_import_logic 的异常分支会调用
    `remove_temp_file()` -> `shutil.rmtree()`，**整目录被删除**（不可恢复）。
    这里强制要求 session_id 不含路径分隔符与 `..`，并再次确认解析结果确实位于
    系统临时目录之内、且目录名带导入前缀，否则一律按「会话无效」拒绝。
    """
    sid = (session_id or '').strip()
    if not _SESSION_ID_RE.match(sid):
        raise HTTPException(status_code=400, detail="导入会话已过期或无效")

    temp_root = os.path.realpath(tempfile.gettempdir())
    temp_dir = os.path.realpath(os.path.join(temp_root, f"{_IMPORT_TEMP_PREFIX}{sid}"))
    # 双重确认：解析后的路径必须仍在临时目录内，且目录名就是期望的那个
    if os.path.dirname(temp_dir) != temp_root:
        raise HTTPException(status_code=400, detail="导入会话已过期或无效")
    if not os.path.basename(temp_dir).startswith(_IMPORT_TEMP_PREFIX):
        raise HTTPException(status_code=400, detail="导入会话已过期或无效")
    return temp_dir


def remove_temp_file(path: str):
    """删除临时文件/目录。

    仅允许删除**系统临时目录之内**的、以导入前缀命名的目录，
    避免任何调用点误传路径导致误删用户数据。
    """
    try:
        if not path:
            return
        target = os.path.realpath(path)
        temp_root = os.path.realpath(tempfile.gettempdir())
        if os.path.dirname(target) != temp_root or \
                not os.path.basename(target).startswith(_IMPORT_TEMP_PREFIX):
            logger.warning(f"拒绝清理非导入临时目录的路径: {path}")
            return
        if os.path.isdir(target):
            shutil.rmtree(target)
        elif os.path.exists(target):
            os.remove(target)
    except Exception as e:
        logger.error(f"清理临时文件失败: {path}, {e}")

def export_library_to_zip(
    db_session: Session,
    export_library: bool,
    collection_ids: List[str],
    export_type: str,
    export_queue: bool,
    queue_data: list,
    save_path: str = None
):
    col_data = []
    video_data = []
    export_bvids = set()
    local_bvids = set()
    
    if export_library:
        if "all" in collection_ids:
            collections = db_session.query(models.Collection).filter(models.Collection.type == "local").all()
        else:
            collections = db_session.query(models.Collection).filter(models.Collection.id.in_(collection_ids)).all()
            
        col_data = [{"id": c.id, "title": c.title, "type": c.type} for c in collections]
        
        videos_query = db_session.query(models.Video).options(
            joinedload(models.Video.tags),
            joinedload(models.Video.collections)
        )
        
        if "all" in collection_ids:
            videos = videos_query.filter(
                or_(models.Video.is_local == 1, models.Video.download_status == 'completed')
            ).all()
        else:
            valid_col_ids = [c.id for c in collections]
            videos = videos_query.filter(
                models.Video.collections.any(models.Collection.id.in_(valid_col_ids))
            ).all()

        for v in videos:
            video_data.append({
                "bvid": v.bvid, "title": v.title, "owner": v.owner, "pic": v.pic,
                "duration": v.duration, "score": v.score, "trim_start": v.trim_start,
                "trim_end": v.trim_end, "download_status": v.download_status,
                "is_local": getattr(v, 'is_local', 0), "local_mimetype": v.local_mimetype,
                "tags": [t.name for t in v.tags],
                "collections": [c.id for c in v.collections]
            })
            
            if export_type == "full":
                export_bvids.add(v.bvid)
            if getattr(v, 'is_local', 0) == 1:
                local_bvids.add(v.bvid)

    if export_queue:
        for qv in queue_data:
            bvid = qv.get("bvid") or qv.get("bv_id")
            if bvid:
                if export_type == "full":
                    export_bvids.add(bvid)
                if qv.get("is_local"):
                    local_bvids.add(bvid)

    metadata = {
        "collections": col_data,
        "videos": video_data,
        "queue": queue_data if export_queue else []
    }

    import time
    import traceback
    import tracemalloc
    
    tracemalloc.start()
    logger.info(f"开始执行全量打包任务, export_library={export_library}, export_type={export_type}, 目标集合数: {len(collection_ids)}")
    start_time = time.time()

    # [修复] save_path 来自请求体，原先被直接当成 ZIP 输出路径：
    #   - `zipfile.ZipFile(temp_path, 'w')` 会**截断任何已存在的文件**（例如用户文档）；
    #   - 打包失败时 `os.remove(temp_path)` 会把那个文件直接删掉。
    # 正常界面走 Electron 保存对话框，这里补上基本校验，避免把服务端接口变成
    # 「覆盖/删除任意文件」的入口。
    if save_path:
        if os.path.isdir(save_path):
            raise HTTPException(status_code=400, detail="保存路径不能是目录")
        if not save_path.lower().endswith('.zip'):
            raise HTTPException(status_code=400, detail="保存路径必须以 .zip 结尾")
        if os.path.exists(save_path):
            raise HTTPException(status_code=409, detail="目标文件已存在，请另选保存路径")
        temp_path = save_path
        logger.info(f"使用用户指定的保存路径: {temp_path}")
    else:
        temp_fd, temp_path = tempfile.mkstemp(prefix="BiliMusic_Backup_", suffix=".zip")
        os.close(temp_fd)
        logger.info(f"已分配临时文件路径: {temp_path}")
    
    try:
        # 优化点 1：压缩策略优化
        # 针对高熵视频文件强制切换至 ZIP_STORED（仅打包不压缩）
        # 避免无意义的二次压缩，将 CPU 消耗降至最低，彻底解决长时阻塞问题
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            logger.debug("成功写入 metadata.json")
            
            from ..core.paths import DATA_DIR
            covers_dir = os.path.join(DATA_DIR, "covers")
            media_dir = cleanup_service.DOWNLOAD_PATH
            target_bvids = export_bvids.union(local_bvids)
            
            if target_bvids:
                db_videos = db_session.query(models.Video).filter(models.Video.bvid.in_(target_bvids)).all()
                written_files = set()
                total_videos = len(db_videos)
                logger.info(f"共需处理 {total_videos} 个视频文件")
                
                for idx, v in enumerate(db_videos, 1):
                    video_start_time = time.time()
                    logger.debug(f"[{idx}/{total_videos}] 开始处理视频: {v.bvid} ({v.title})")
                    
                    if v.pic and not v.pic.startswith("http"):
                        cover_path = os.path.join(covers_dir, v.pic)
                        zip_cover_path = f"covers/{v.pic}"
                        if os.path.exists(cover_path) and zip_cover_path not in written_files:
                            zf.write(cover_path, zip_cover_path)
                            written_files.add(zip_cover_path)
                    
                    local_path = v.local_path
                    if getattr(v, 'is_local', 0) == 0 and not local_path:
                        default_path = os.path.join(media_dir, f"{v.bvid}.mp4")
                        if os.path.exists(default_path):
                            local_path = default_path
                            
                    if local_path and os.path.exists(local_path):
                        filename = os.path.basename(local_path)
                        zip_media_path = f"media/{v.bvid}_{filename}"
                        if zip_media_path not in written_files:
                            file_size = os.path.getsize(local_path)
                            current_mem, peak_mem = tracemalloc.get_traced_memory()
                            logger.debug(f"[{idx}/{total_videos}] 准备写入文件: {local_path}, 大小: {file_size / (1024*1024):.2f} MB, 当前内存: {current_mem / (1024*1024):.2f} MB, 峰值内存: {peak_mem / (1024*1024):.2f} MB")
                            
                            # 优化点 2：核心流处理
                            # zipfile.write 内部采用分块读取写入，实现 O(1) 内存复杂度
                            try:
                                zf.write(local_path, zip_media_path)
                                written_files.add(zip_media_path)
                            except BaseException as write_e:
                                logger.error(f"[{idx}/{total_videos}] 写入文件 {local_path} 时发生异常: {type(write_e).__name__} - {write_e}")
                                logger.error(traceback.format_exc())
                                raise write_e
                            
                            video_cost = time.time() - video_start_time
                            logger.info(f"[{idx}/{total_videos}] 成功写入视频: {v.bvid}, 耗时: {video_cost:.2f}s")
                    else:
                        logger.warning(f"[{idx}/{total_videos}] 视频文件不存在: {local_path}")

        total_cost = time.time() - start_time
        final_mem, final_peak = tracemalloc.get_traced_memory()
        logger.info(f"全量打包任务执行完毕, 总耗时: {total_cost:.2f}s, 最终内存: {final_mem / (1024*1024):.2f} MB, 峰值内存: {final_peak / (1024*1024):.2f} MB, 临时文件路径: {temp_path}")
        tracemalloc.stop()
        return temp_path
    except BaseException as e:
        # 优化点 3：防泄漏生命周期管理 (第一级防御)
        # 基于 try-except 结构的强制兜底清理策略，确保在任务异常中断时 Temp 目录被绝对抹除
        # 捕获 BaseException 以拦截 asyncio.CancelledError 等底层异常
        logger.error(f"打包过程发生严重异常: {type(e).__name__} - {e}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        # [修复] tracemalloc 原先只在成功路径 stop()。导出失败一次后，内存分配追踪
        # 会在整个进程生命周期内保持开启：每个请求都额外付出追踪开销，
        # 且下次导出打印的「峰值内存」不再代表真实峰值。
        try:
            tracemalloc.stop()
        except Exception:
            pass
        if not save_path:
            remove_temp_file(temp_path)
        else:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        raise e

def analyze_import_zip(file_content: bytes, db_session: Session):
    session_id = uuid.uuid4().hex
    # 复用同一套解析逻辑，保证「生成」与「消费」两侧对临时目录的约束完全一致
    temp_dir = resolve_import_temp_dir(session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    zip_path = os.path.join(temp_dir, "upload.zip")
    with open(zip_path, "wb") as f:
        f.write(file_content)
        
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if "metadata.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="压缩包中缺失 metadata.json")
            
            for member in zf.infolist():
                target_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not target_path.startswith(os.path.abspath(temp_dir)):
                    logger.warning(f"跳过非法路径文件: {member.filename}")
                    continue
                zf.extract(member, temp_dir)
            
        with open(os.path.join(temp_dir, "metadata.json"), "r", encoding="utf-8") as f:
            metadata = json.load(f)
            
        existing_bvids = {v[0] for v in db_session.query(models.Video.bvid).all()}
        
        conflicts = []
        new_videos = []
        for v in metadata.get("videos", []):
            if v["bvid"] in existing_bvids:
                conflicts.append(v)
            else:
                new_videos.append(v)
                
        return {
            "session_id": session_id,
            "collections": metadata.get("collections", []),
            "new_videos": new_videos,
            "conflicts": conflicts,
            "has_queue": len(metadata.get("queue", [])) > 0,
            "temp_dir": temp_dir
        }
    except Exception as e:
        remove_temp_file(temp_dir)
        raise e

def execute_import_logic(
    session_id: str,
    resolutions: dict,
    import_queue: bool,
    db_session: Session
):
    # [修复] session_id 必须经 resolve_import_temp_dir() 校验，理由见该函数注释
    temp_dir = resolve_import_temp_dir(session_id)
    if not os.path.exists(temp_dir):
        raise HTTPException(status_code=400, detail="导入会话已过期或无效")
        
    try:
        with open(os.path.join(temp_dir, "metadata.json"), "r", encoding="utf-8") as f:
            metadata = json.load(f)
            
        col_map = {}
        existing_cols = {c.title: c for c in db_session.query(models.Collection).all()}
        
        for c in metadata.get("collections", []):
            if c["title"] in existing_cols:
                col_map[c["id"]] = existing_cols[c["title"]].id
            else:
                # [修复] 原实现直接复用压缩包里的 id 作为主键。c["id"] 是不可信字符串，
                # 若该 id 恰好已被另一个**同名之外**的媒体夹占用，commit() 会抛
                # IntegrityError：此时媒体文件可能已经拷贝进来，导入中断且临时目录被清理。
                # 改为始终分配新主键，旧 id 仅用于 col_map 映射。
                new_id = uuid.uuid4().hex[:8]
                new_col = models.Collection(id=new_id, title=c["title"], type="local")
                db_session.add(new_col)
                col_map[c["id"]] = new_id
        db_session.commit()
        
        from ..core.paths import DATA_DIR
        covers_dir = os.path.join(DATA_DIR, "covers")
        os.makedirs(covers_dir, exist_ok=True)
        media_dir = cleanup_service.DOWNLOAD_PATH
        
        for v in metadata.get("videos", []):
            bvid = v["bvid"]
            res = resolutions.get(bvid, "skip")
            
            existing_v = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
            if existing_v and res == "skip":
                continue
                
            if not existing_v:
                existing_v = models.Video(bvid=bvid)
                db_session.add(existing_v)
                
            existing_v.title = v["title"]
            existing_v.owner = v["owner"]
            existing_v.duration = v["duration"]
            existing_v.score = v.get("score", 5.0)
            existing_v.trim_start = v.get("trim_start", 0.0)
            existing_v.trim_end = v.get("trim_end", 0.0)
            existing_v.is_local = v.get("is_local", 0)
            existing_v.local_mimetype = v.get("local_mimetype", None)
            
            if v.get("pic"):
                # [修复] v["pic"] 来自压缩包内的 metadata.json，属于**不可信输入**。
                # 原实现直接把它当路径分量拼接：绝对路径会让 os.path.join 丢弃
                # covers_dir（源与目标相同还会抛 SameFileError 导致导入中断并被清理），
                # 含 ".." 的取值还能把 covers/ 之外的文件拷进来，并把穿越字符串写进数据库。
                # 这里只取纯文件名，任何目录成分一律丢弃。
                pic_name = os.path.basename(str(v.get("pic") or "").replace("\\", "/"))
                if pic_name and pic_name not in ('.', '..'):
                    temp_cover = os.path.join(temp_dir, "covers", pic_name)
                    if os.path.exists(temp_cover):
                        shutil.copy2(temp_cover, os.path.join(covers_dir, pic_name))
                    existing_v.pic = pic_name
                
            has_media_in_zip = False
            if os.path.exists(os.path.join(temp_dir, "media")):
                for f in os.listdir(os.path.join(temp_dir, "media")):
                    if f.startswith(f"{bvid}_"):
                        original_filename = f.replace(f"{bvid}_", "", 1)
                        target_path = os.path.join(media_dir, original_filename)
                        shutil.copy2(os.path.join(temp_dir, "media", f), target_path)
                        existing_v.local_path = target_path
                        has_media_in_zip = True
                        break
            
            target_status = v.get("download_status", "not_downloaded")
            if existing_v.is_local == 1:
                existing_v.download_status = "completed"
            else:
                if target_status == "completed":
                    expected_mp4 = os.path.join(media_dir, f"{bvid}.mp4")
                    if has_media_in_zip or os.path.exists(expected_mp4):
                        existing_v.download_status = "completed"
                    else:
                        existing_v.download_status = "not_downloaded"
                else:
                    existing_v.download_status = target_status
            
            existing_v.tags = []
            for tag_name in v.get("tags", []):
                tag = db_session.query(models.Tag).filter(models.Tag.name == tag_name).first()
                if not tag:
                    tag = models.Tag(name=tag_name)
                    db_session.add(tag)
                existing_v.tags.append(tag)
                
            existing_v.collections = []
            for old_cid in v.get("collections", []):
                new_cid = col_map.get(old_cid)
                if new_cid:
                    col = db_session.query(models.Collection).filter(models.Collection.id == new_cid).first()
                    if col and col not in existing_v.collections:
                        existing_v.collections.append(col)
                        
        db_session.commit()
        
        queue_data = metadata.get("queue", []) if import_queue else []
        if queue_data:
            all_video_status = {v.bvid: v.download_status for v in db_session.query(models.Video).all()}
            for qv in queue_data:
                bvid = qv.get("bvid") or qv.get("bv_id")
                if bvid in all_video_status:
                    qv["download_status"] = all_video_status[bvid]
                else:
                    qv["download_status"] = "not_downloaded"
        
        return queue_data, temp_dir
    except Exception as e:
        remove_temp_file(temp_dir)
        raise e
