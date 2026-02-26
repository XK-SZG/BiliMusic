import time
import re
import threading
import pyperclip
from contextlib import contextmanager
from sqlalchemy.orm import Session
from ..database.db import SessionLocal
from ..database.models import Video
import logging


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
    """后台监听剪贴板任务"""
    logging.info("剪贴板监听器已启动...")
    last_content = ""
    bv_regex = re.compile(r"BV[a-zA-Z0-9]{10}")

    while True:
        try:
            content = pyperclip.paste().strip()
            if content and content != last_content:
                last_content = content
                match = bv_regex.search(content)
                if match:
                    bvid = match.group()
                    save_video_by_bvid(bili_manager, bvid)
            time.sleep(2)
        except Exception:
            # 使用 exception 可以捕获完整的 traceback
            logging.exception("剪贴板监听线程发生严重错误")
            time.sleep(5)


def save_video_by_bvid(bili, bvid):
    """根据BV号获取信息并存入数据库（线程安全版）"""
    try:
        # 使用 with 语句确保会话管理
        with get_thread_safe_db_session() as db:
            # 检查是否已存在
            if db.query(Video).filter(Video.bvid == bvid).first():
                logging.info(f"视频 {bvid} 已在数据库中，跳过")
                return

            # 调用B站API获取信息
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            res = bili.session.get(url).json()

            if res.get('code') == 0:
                data = res['data']
                new_video = Video(
                    bvid=bvid,
                    title=data['title'],
                    owner=data['owner']['name'],
                    pic=data['pic'],
                    duration=data['duration']
                )
                db.add(new_video)
                # commit() 会在 with 语句结束时自动调用
                logging.info(f"发现新视频并成功添加入库: {data['title']}")
            else:
                logging.warning(f"无法获取 {bvid} 的视频信息: {res.get('message')}")

    except Exception:
        logging.exception(f"处理BV号 {bvid} 时发生错误")