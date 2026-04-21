# -*- coding: utf-8 -*-
import multiprocessing
import sys
import os
import logging
import uvicorn
from backend.main import app, logger
from backend.core.config import get_config
from backend.core.paths import BASE_DIR

# 配置文件日志处理器
def setup_file_logging():
    """为打包后的应用添加文件日志"""
    try:
        # 判断是否为打包后的环境
        if getattr(sys, 'frozen', False):
            # 打包后的环境，日志写入用户数据目录
            if sys.platform == 'win32':
                log_dir = os.path.join(os.environ.get('APPDATA', ''), 'BiliMusic', 'logs')
            else:
                log_dir = os.path.expanduser('~/.config/BiliMusic/logs')
            
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'backend.log')
            
            # 添加文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            
            # 获取根日志记录器并添加处理器
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)
            
            logger.info(f"📝 日志文件路径: {log_file}")
            return log_file
    except Exception as e:
        logger.error(f"设置文件日志失败: {e}")
    return None

def find_config_file():
    """查找配置文件，优先级：打包目录 > 工作目录 > 基础目录"""
    search_paths = []
    
    # 打包后的环境
    if getattr(sys, 'frozen', False):
        # 1. exe 所在目录
        exe_dir = os.path.dirname(sys.executable)
        search_paths.append(os.path.join(exe_dir, 'config.yaml'))
        
        # 2. resources 目录（Electron 打包）
        if hasattr(sys, '_MEIPASS'):
            search_paths.append(os.path.join(sys._MEIPASS, 'config.yaml'))
    
    # 3. 当前工作目录
    search_paths.append(os.path.join(os.getcwd(), 'config.yaml'))
    
    # 4. 基础目录
    search_paths.append(os.path.join(BASE_DIR, 'config.yaml'))
    
    for config_path in search_paths:
        if os.path.exists(config_path):
            logger.info(f"✅ 找到配置文件: {config_path}")
            return config_path
    
    logger.warning(f"⚠️  未找到配置文件，搜索路径: {search_paths}")
    return None

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # 设置文件日志
    log_file_path = setup_file_logging()
    
    # 查找并加载配置文件
    config_path = find_config_file()
    if config_path:
        os.environ['BILIMUSIC_CONFIG_PATH'] = config_path
    
    # 加载配置
    config = get_config()
    server_config = config.get_server_config()
    
    # 从配置文件读取服务器参数
    host = server_config.get('host', '127.0.0.1')
    port = server_config.get('port', 12280)
    debug = server_config.get('debug', False)
    
    # 命令行参数优先级更高
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            logger.info(f"📌 从命令行参数读取端口: {port}")
        except ValueError:
            logger.warning(f"⚠️  无效的端口参数: {sys.argv[1]}")
    
    logger.info("=" * 60)
    logger.info(f"🚀 BiliMusic 后端服务启动中...")
    logger.info(f"📍 监听地址: {host}:{port}")
    logger.info(f"🔧 调试模式: {'开启' if debug else '关闭'}")
    logger.info(f"📦 打包环境: {'是' if getattr(sys, 'frozen', False) else '否'}")
    logger.info(f"📂 工作目录: {os.getcwd()}")
    logger.info(f"📂 基础目录: {BASE_DIR}")
    if config_path:
        logger.info(f"⚙️  配置文件: {config_path}")
    if log_file_path:
        logger.info(f"📝 日志文件: {log_file_path}")
    logger.info("=" * 60)
    
    if debug:
        logger.warning("⚠️  调试模式已启用，生产环境请关闭")
    
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="debug" if debug else "info"
        )
    except Exception as e:
        logger.error(f"❌ 服务器启动失败: {e}", exc_info=True)
        raise
