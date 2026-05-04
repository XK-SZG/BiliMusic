import logging
from collections import deque
import threading

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=500):
        super().__init__()
        self.capacity = capacity
        self.logs = deque(maxlen=capacity)
        self.lock = threading.Lock()

    def emit(self, record):
        try:
            msg = self.format(record)
            with self.lock:
                self.logs.append({
                    "time": record.created,
                    "level": record.levelname,
                    "message": msg
                })
        except Exception:
            self.handleError(record)

    def get_logs(self):
        with self.lock:
            return list(self.logs)

memory_handler = MemoryLogHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
memory_handler.setFormatter(formatter)

def setup_memory_logger():
    root_logger = logging.getLogger()
    if memory_handler not in root_logger.handlers:
        root_logger.addHandler(memory_handler)
