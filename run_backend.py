# -*- coding: utf-8 -*-
import multiprocessing
import sys
import uvicorn
from backend.main import app, logger

if __name__ == "__main__":
    multiprocessing.freeze_support()
    port = 12243
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    logger.info(f"Starting BiliMusic backend server on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
