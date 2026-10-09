import logging
import threading
import time
from datetime import datetime
from sqlalchemy.orm import Session
from ..database import db, models

logger = logging.getLogger(__name__)

class AsyncTrafficCounter:
    """
    [性能优化] 微批聚合（Micro-batching）流量统计缓冲池
    目的：将原本流代理路由中上百次的独立写锁竞争，聚合为每 2 秒一次的批量更新。
    完全消除了在高并发（如同时缓冲 10 首大视频）时的 SQLite 'Database is locked' 风险。
    """
    def __init__(self, batch_interval=2.0):
        self._buffer = 0
        self._lock = threading.Lock()
        self._interval = batch_interval
        
        # 启动消费守护线程
        self._consumer_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._consumer_thread.start()
        
    def add(self, byte_size: int):
        with self._lock:
            self._buffer += byte_size
            
    def _flush_loop(self):
        while True:
            time.sleep(self._interval)

            # 安全地抽取当前的流量缓冲
            with self._lock:
                if self._buffer == 0:
                    continue
                traffic_to_write = self._buffer
                self._buffer = 0

            # 执行落盘
            try:
                with db.SessionLocal() as session:
                    # [修复] 统一使用本地时间：stats.py 的 record_network_traffic 等接口
                    # 都按 datetime.now() 归属日期，此处若用 utcnow()，在 UTC+8 等时区
                    # 会导致凌晨 0-8 点的流量被记到前一天，日统计与排行榜对不上。
                    today = datetime.now().strftime('%Y-%m-%d')
                    stat = session.query(models.DailyStat).filter(models.DailyStat.date == today).first()
                    if not stat:
                        stat = models.DailyStat(date=today, network_traffic=0, uncached_traffic=0)
                        session.add(stat)

                    # [修复] 历史行可能因 create_all 建表后补列而为 NULL，直接 += 会抛 TypeError
                    stat.network_traffic = (stat.network_traffic or 0) + traffic_to_write
                    stat.uncached_traffic = (stat.uncached_traffic or 0) + traffic_to_write
                    session.commit()
            except Exception as e:
                # 写入失败时，补偿回滚到缓冲中，交由下一轮重试
                logger.warning(f"[流量统计] 批量写入失败，已回滚到缓冲待重试: {e}")
                with self._lock:
                    self._buffer += traffic_to_write

# 暴露单例给所有的路由
traffic_counter = AsyncTrafficCounter()
