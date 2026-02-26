import argparse
import multiprocessing
import sys
import uvicorn
import webbrowser
import time
from threading import Thread
from backend.main import app, logger

def open_browser(port, with_titlebar):
    # 等待几秒钟确保后端启动
    time.sleep(2)
    url = f"http://127.0.0.1:{port}"
    if with_titlebar:
        url += "/?titlebar=1"
    logger.info(f"Opening browser at {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    parser = argparse.ArgumentParser(description="Run BiliMusic Backend Server")
    parser.add_argument("--port", type=int, default=12243, help="Port to run the server on")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    parser.add_argument("--with-titlebar", action="store_true", help="Force show custom titlebar in browser")
    
    args = parser.parse_args()
    
    if not args.no_browser:
        Thread(target=open_browser, args=(args.port, args.with_titlebar), daemon=True).start()
        
    logger.info(f"Starting BiliMusic backend server on port {args.port}...")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
