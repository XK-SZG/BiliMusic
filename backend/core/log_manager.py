import logging
from collections import deque
import threading

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=500):
        super().__init__()
        self.capacity = capacity
        self.logs = deque(maxlen=capacity)

    def emit(self, record):
        try:
            msg = self.format(record)
            # logging.Handler.handle() 在调用 emit() 前已经获取了锁 (self.lock)
            self.logs.append({
                "time": record.created,
                "level": record.levelname,
                "message": msg
            })
        except Exception:
            self.handleError(record)

    def get_logs(self):
        # 使用父类提供的 acquire() 和 release() 保证线程安全
        self.acquire()
        try:
            return list(self.logs)
        finally:
            self.release()

memory_handler = MemoryLogHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
memory_handler.setFormatter(formatter)

def setup_memory_logger():
    root_logger = logging.getLogger()
    if memory_handler not in root_logger.handlers:
        root_logger.addHandler(memory_handler)
