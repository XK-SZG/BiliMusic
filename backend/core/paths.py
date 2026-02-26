import os
import sys

def is_compiled():
    return getattr(sys, 'frozen', False) or "__compiled__" in globals() or sys.argv[0].endswith('.exe')

def get_base_dir():
    """获取应用程序的根目录"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    elif is_compiled():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_data_dir():
    """获取数据存储目录"""
    if is_compiled():
        exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.join(exe_dir, "data")
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

DATA_DIR = get_data_dir()
BASE_DIR = get_base_dir()

# 确保基础数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "stickers"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "backgrounds"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "covers"), exist_ok=True)

# 复制默认资源到数据目录
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    import shutil
    default_stickers = os.path.join(sys._MEIPASS, "data", "stickers")
    target_stickers = os.path.join(DATA_DIR, "stickers")
    if os.path.exists(default_stickers):
        for item in os.listdir(default_stickers):
            s = os.path.join(default_stickers, item)
            d = os.path.join(target_stickers, item)
            if not os.path.exists(d):
                try:
                    shutil.copy2(s, d)
                except Exception:
                    pass
