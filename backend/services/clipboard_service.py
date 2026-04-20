import time
import re
import threading
import pyperclip
from contextlib import contextmanager
from sqlalchemy.orm import Session
from ..database.db import SessionLocal
from ..database.models import Video
import logging

# 全局变量：存储待确认的 BV 号队列
pending_bvids = []
pending_lock = threading.Lock()
is_clipboard_paused = False

@contextmanager
def get_thread_safe_db_session():
    """为后台线程提供一个安全的、独立的数据库会-话上下文"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        logging.error(f"数据库会话出错，正在回滚: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def watch_clipboard(bili_manager):
    """
    [性能优化] 后台监听剪贴板任务，使用指数退避算法降低 CPU 占用
    """
    logging.info("[剪贴板监听] 监听器已启动...")
    last_content = ""
    # 更新正则表达式，支持分集视频格式：BV号 或 BV号?...&p=数字 或 BV号?p=数字
    bv_regex = re.compile(r"BV[a-zA-Z0-9]{10}")
    # 单独的正则用于提取 p 参数（支持 ?p=N 或 &p=N）
    p_param_regex = re.compile(r"[?&]p=(\d+)")

    # [性能优化] 指数退避算法参数
    base_interval = 2  # 基础轮询间隔（秒）
    max_interval = 10  # 最大轮询间隔（秒）
    current_interval = base_interval
    idle_count = 0  # 连续空闲次数

    global is_clipboard_paused
    while True:
        try:
            if is_clipboard_paused:
                time.sleep(1)
                continue
                
            content = pyperclip.paste().strip()
            if content and content != last_content:
                last_content = content
                bv_match = bv_regex.search(content)
                if bv_match:
                    # [性能优化] 检测到活动，重置轮询间隔
                    current_interval = base_interval
                    idle_count = 0
                    
                    bvid = bv_match.group(0)  # 纯 BV 号
                    
                    # 尝试提取分集参数
                    p_match = p_param_regex.search(content)
                    part_num = p_match.group(1) if p_match else None
                    
                    # 构造标准化的 bvid 格式
                    # 如果是分集视频，格式为 BV号_pN，否则就是纯 BV号
                    if part_num:
                        normalized_bvid = f"{bvid}_p{part_num}"
                    else:
                        normalized_bvid = bvid
                    
                    # 检查视频是否已在数据库中
                    with get_thread_safe_db_session() as db:
                        existing = db.query(Video).filter(Video.bvid == normalized_bvid).first()
                        if existing:
                            logging.info(f"[剪贴板监听] 视频 {normalized_bvid} 已在媒体库中，自动忽略")
                            continue
                    
                    # 不再直接添加，而是加入待确认队列
                    with pending_lock:
                        if normalized_bvid not in pending_bvids:
                            pending_bvids.append(normalized_bvid)
                            if part_num:
                                logging.info(f"[剪贴板监听] 检测到分集视频: {normalized_bvid}（第 {part_num} 集），等待用户确认")
                            else:
                                logging.info(f"[剪贴板监听] 检测到 BV 号: {normalized_bvid}，等待用户确认")
                else:
                    # [性能优化] 无 BV 号但内容变化，适度增加间隔
                    idle_count += 1
                    if idle_count > 3:
                        current_interval = min(current_interval * 1.5, max_interval)
            else:
                # [性能优化] 剪贴板无变化，使用指数退避
                idle_count += 1
                if idle_count > 5:
                    current_interval = min(current_interval * 1.5, max_interval)
            
            time.sleep(current_interval)
            
        except Exception:
            # 使用 exception 可以捕获完整的 traceback
            logging.exception("[剪贴板监听] 线程发生严重错误")
            time.sleep(5)


def save_video_by_bvid(bili, bvid):
    """根据BV号获取信息并存入数据库（线程安全版，支持分集视频）"""
    try:
        # 使用 with 语句确保会话管理
        with get_thread_safe_db_session() as db:
            # 检查是否已存在
            existing = db.query(Video).filter(Video.bvid == bvid).first()
            if existing:
                logging.info(f"视频 {bvid} 已在数据库中，跳过")
                return
            
            # 解析 bvid，判断是否为分集视频
            is_part = "_p" in bvid
            if is_part:
                clean_bvid, part_str = bvid.split("_p")
                part_num = int(part_str)
            else:
                clean_bvid = bvid
                part_num = None
            
            # 如果不是分集视频，检查是否存在该视频的分P版本
            if not is_part:
                existing_parts = db.query(Video).filter(Video.bvid.like(f"{bvid}_p%")).first()
                if existing_parts:
                    logging.info(f"视频 {bvid} 的分P版本已存在，跳过添加主视频")
                    return

            # 调用B站API获取信息
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
                        logging.warning(f"分集编号 {part_num} 超出范围，使用主视频信息")
                else:
                    title = data['title']
                    duration = data['duration']
                
                new_video = Video(
                    bvid=bvid,
                    title=title,
                    owner=data['owner']['name'],
                    pic=data['pic'],
                    duration=duration
                )
                db.add(new_video)
                # commit() 会在 with 语句结束时自动调用
                logging.info(f"发现新视频并成功添加入库: {title}")
            else:
                logging.warning(f"无法获取 {clean_bvid} 的视频信息: {res.get('message')}")

    except Exception:
        logging.exception(f"处理BV号 {bvid} 时发生错误")