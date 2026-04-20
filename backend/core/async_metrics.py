import threading
import time
from datetime import datetime
from sqlalchemy.orm import Session
from ..database import db, models

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
                    today = datetime.utcnow().strftime('%Y-%m-%d')
                    stat = session.query(models.DailyStat).filter(models.DailyStat.date == today).first()
                    if not stat:
                        stat = models.DailyStat(date=today, network_traffic=0, uncached_traffic=0)
                        session.add(stat)
                        
                    stat.network_traffic += traffic_to_write
                    stat.uncached_traffic += traffic_to_write
                    session.commit()
            except Exception as e:
                # 写入失败时，补偿回滚到缓冲中
                with self._lock:
                    self._buffer += traffic_to_write

# 暴露单例给所有的路由
traffic_counter = AsyncTrafficCounter()
