# -*- coding: utf-8 -*-
import multiprocessing
import sys
import uvicorn
from backend.main import app, logger
from backend.core.config import get_config

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # 加载配置
    config = get_config()
    server_config = config.get_server_config()
    
    # 从配置文件读取服务器参数
    host = server_config.get('host', '127.0.0.1')
    port = server_config.get('port', 12243)
    debug = server_config.get('debug', False)
    
    # 命令行参数优先级更高
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    
    logger.info(f"Starting BiliMusic backend server on {host}:{port}...")
    if debug:
        logger.warning("⚠️  调试模式已启用，生产环境请关闭")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="debug" if debug else "info"
    )
