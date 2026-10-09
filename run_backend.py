# -*- coding: utf-8 -*-
import multiprocessing
import sys
import os
import logging
import traceback
from datetime import datetime

# ============================================================
# CRASH DIAGNOSTIC LOGGING — MUST BE SET UP BEFORE ANY IMPORT
# ============================================================
# In frozen (PyInstaller) environment, if `from backend.main import app`
# fails, we need to capture the traceback in a log file AND on stderr.
# This block runs first, before anything else that could potentially crash.

def _setup_crash_logging():
    """Configure file logging as early as possible for crash diagnosis."""
    try:
        # Determine log directory
        if getattr(sys, 'frozen', False):
            if sys.platform == 'win32':
                log_dir = os.path.join(os.environ.get('APPDATA', ''), 'BiliMusic', 'logs')
            else:
                log_dir = os.path.expanduser('~/.config/BiliMusic/logs')
        else:
            log_dir = os.path.join(os.getcwd(), 'logs')
            
        os.makedirs(log_dir, exist_ok=True)
        crash_log_file = os.path.join(log_dir, 'backend_crash.log')
        
        # Write a startup marker to both the crash log and stderr
        startup_marker = f"\n{'='*60}\n[{datetime.now().isoformat()}] BACKEND STARTUP\n{'='*60}\n"
        
        # Try to write to the crash log file even before logging is configured
        try:
            with open(crash_log_file, 'a', encoding='utf-8') as f:
                f.write(startup_marker)
        except:
            pass
        
        # Also print to stderr so it appears in Electron's main.cjs log
        print(startup_marker, file=sys.stderr, flush=True)
        
        return crash_log_file
    except Exception:
        pass
    return None

# Capture crash log path as early as possible
_CRASH_LOG_FILE = _setup_crash_logging()

# Now configure Python logging with both file and stderr handlers
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),  # Goes to Electron's main.cjs log
    ]
)

# Add file handler if we have a crash log path
if _CRASH_LOG_FILE:
    try:
        file_handler = logging.FileHandler(_CRASH_LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(file_handler)
    except Exception:
        pass

logger = logging.getLogger('run_backend')

# Log system information immediately
logger.info("=" * 60)
logger.info(f"Python version: {sys.version}")
logger.info(f"Executable: {sys.executable}")
logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"sys.path: {sys.path[:3]}")
if _CRASH_LOG_FILE:
    logger.info(f"Crash log file: {_CRASH_LOG_FILE}")

# Export crash log path for diagnostic probes in sub-modules
if _CRASH_LOG_FILE:
    os.environ['BILIMUSIC_CRASH_LOG'] = _CRASH_LOG_FILE

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    if _CRASH_LOG_FILE:
        try:
            with open(_CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n[{datetime.now().isoformat()}] UNHANDLED EXCEPTION\n")
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        except:
            pass

sys.excepthook = handle_unhandled_exception

# ============================================================
# SAFE IMPORT OF app — with full traceback logging
# ============================================================

_app = None
_app_logger = None
_import_error = None

# Direct-to-file diagnostic probe (bypasses logging in case of hang)
if _CRASH_LOG_FILE:
    try:
        with open(_CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] run_backend: about to import backend.main\n")
            f.flush()
    except:
        pass

try:
    logger.info("Importing backend.main:app ...")
    from backend.main import app as _app_obj, logger as _app_logger_obj
    _app = _app_obj
    _app_logger = _app_logger_obj
    logger.info("Successfully imported backend.main:app")
    
    if _CRASH_LOG_FILE:
        try:
            with open(_CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] run_backend: import complete, app={_app is not None}\n")
                f.flush()
        except:
            pass
except Exception as e:
    _import_error = traceback.format_exc()
    logger.critical(f"CRITICAL: Failed to import backend.main:app:\n{_import_error}")
    # Write directly to crash log file as well (redundancy)
    if _CRASH_LOG_FILE:
        try:
            with open(_CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n[CRITICAL IMPORT FAILURE]\n{_import_error}\n")
        except:
            pass
    print(f"\n[CRITICAL IMPORT FAILURE]\n{_import_error}\n", file=sys.stderr, flush=True)

# Only continue with the rest if import succeeded
if _app is not None:
    app = _app
    # Patch the logger reference to use our crash-protected logger if needed
    if _app_logger is None:
        _app_logger = logger

    import uvicorn
    from backend.core.config import get_config
    from backend.core.paths import BASE_DIR

    def find_config_file():
        """查找配置文件，优先级：打包目录 > 工作目录 > 基础目录"""
        search_paths = []
        
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            search_paths.append(os.path.join(exe_dir, 'config.yaml'))
            if hasattr(sys, '_MEIPASS'):
                search_paths.append(os.path.join(sys._MEIPASS, 'config.yaml'))
        
        search_paths.append(os.path.join(os.getcwd(), 'config.yaml'))
        search_paths.append(os.path.join(BASE_DIR, 'config.yaml'))
        
        for config_path in search_paths:
            if os.path.exists(config_path):
                logger.info(f"Found config file: {config_path}")
                return config_path
        
        logger.warning(f"Config file not found, searched: {search_paths}")
        return None

    if __name__ == "__main__":
        multiprocessing.freeze_support()
        
        config_path = find_config_file()
        if config_path:
            os.environ['BILIMUSIC_CONFIG_PATH'] = config_path
        
        config = get_config()
        server_config = config.get_server_config()
        
        host = server_config.get('host', '127.0.0.1')
        port = server_config.get('port', 12180)
        debug = server_config.get('debug', False)
        
        if len(sys.argv) > 1:
            try:
                port = int(sys.argv[1])
                logger.info(f"Port overridden from command line: {port}")
            except ValueError:
                logger.warning(f"Invalid port argument: {sys.argv[1]}")
        
        logger.info(f"Starting uvicorn on {host}:{port} (debug={debug})")
        
        try:
            uvicorn.run(
                app,
                host=host,
                port=port,
                log_level="debug" if debug else "info"
            )
            logger.info("uvicorn.run() exited normally.")
        except Exception as e:
            logger.critical(f"Failed to start uvicorn: {traceback.format_exc()}")
            raise
        finally:
            logger.info("Backend process is terminating.")
            if _CRASH_LOG_FILE:
                try:
                    with open(_CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().isoformat()}] Backend process is terminating.\n")
                except:
                    pass
else:
    # Import failed — log and exit cleanly
    if __name__ == "__main__":
        multiprocessing.freeze_support()
        logger.critical("Backend cannot start due to import failure. Exiting.")
        print("\n[FATAL] Backend cannot start due to import failure.\n", file=sys.stderr, flush=True)
        sys.exit(1)
