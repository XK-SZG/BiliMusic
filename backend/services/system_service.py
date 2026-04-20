import os
import platform
import subprocess
import json
import logging
from sqlalchemy.orm import Session
from ..database import models

logger = logging.getLogger(__name__)

def execute_system_shutdown():
    """执行系统关机指令"""
    if platform.system() == "Windows":
        os.system("shutdown /s /t 0")
    else:
        result = subprocess.run(["sudo", "-n", "shutdown", "-h", "now"], capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"关机指令执行失败: {result.stderr}")

def execute_factory_reset(db_session: Session, bili):
    """重置软件，清空所有数据但保留默认主题的静态资源"""
    keep_files = set()
    default_themes = db_session.query(models.Theme).filter(models.Theme.is_default == 1).all()
    for t in default_themes:
        try:
            settings = json.loads(t.settings)
            for container, slist in settings.get('stickers', {}).items():
                for s in slist:
                    if s.get('url'): keep_files.add(os.path.basename(s['url']))
            for bg in settings.get('customBackgrounds', []):
                if bg.get('url'): keep_files.add(os.path.basename(bg['url']))
            for p in settings.get('particleCustomUrls', []):
                keep_files.add(os.path.basename(p))
            card_img = settings.get('cardImage', '')
            if card_img: keep_files.add(os.path.basename(card_img))
            font = settings.get('uiFontCustom', '')
            if font: keep_files.add(font)
        except: pass
        
    keep_files.add("90dfd622_2233.png")

    from ..core.paths import DATA_DIR
    base_dir = DATA_DIR
    directories = ["stickers", "backgrounds", "particles", "covers", "downloads", "fonts", "img_cache"]
    
    for d in directories:
        d_path = os.path.join(base_dir, d)
        if os.path.exists(d_path):
            for f in os.listdir(d_path):
                if d == "fonts":
                    if not any(f.startswith(kf) for k in keep_files if kf):
                        try: os.remove(os.path.join(d_path, f))
                        except: pass
                else:
                    if f not in keep_files:
                        try: os.remove(os.path.join(d_path, f))
                        except: pass

    db_session.query(models.Video).delete()
    db_session.query(models.Collection).delete()
    db_session.query(models.Tag).delete()
    db_session.query(models.Theme).filter(models.Theme.is_default == 0).delete()
    # P3 阶段新增：清空统计数据表
    db_session.query(models.PlayRecord).delete()
    db_session.query(models.DailyStat).delete()
    db_session.commit()

    for af in ["bili_cookies.json", "bili_user_info.json"]:
        p = os.path.join(base_dir, af)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
    
    bili.session.cookies.clear()
    bili.csrf = None
    bili.mid = None
    bili.uname = None
    bili.face = None
    bili.vip_status = 0
    bili.vip_type = 0
    bili._avatar_b64 = None
    bili.vip_icon_b64 = ""
