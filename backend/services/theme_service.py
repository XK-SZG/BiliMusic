import os
import json
import io
import zipfile
import uuid
from fastapi import HTTPException, UploadFile, Response
from sqlalchemy.orm import Session
from ..database import models

def export_theme_to_zip(theme_id: str, db_session: Session):
    t = db_session.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not t:
        raise HTTPException(404, "Theme not found")
    
    settings = json.loads(t.settings)
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        theme_data = {
            "id": t.id,
            "name": t.name,
            "is_default": 0,
            "settings": settings
        }
        zf.writestr("theme.json", json.dumps(theme_data, ensure_ascii=False, indent=2))
        
        # Helper to add files to zip
        def add_to_zip(url_prefix, local_dir, config_key, is_list=False):
            items = settings.get(config_key, [])
            if not is_list: # stickers is a dict of lists
                for container, slist in items.items():
                    for s in slist:
                        url = s.get("url", "")
                        if url.startswith(url_prefix):
                            filename = url.split("/")[-1]
                            fpath = os.path.join(local_dir, filename)
                            if os.path.exists(fpath):
                                zf.write(fpath, f"{config_key}/{filename}")
            else:
                for item in items:
                    url = item.get("url", "") if isinstance(item, dict) else item
                    if url.startswith(url_prefix):
                        filename = url.split("/")[-1]
                        fpath = os.path.join(local_dir, filename)
                        if os.path.exists(fpath):
                            zf.write(fpath, f"{config_key}/{filename}")

        base_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        
        # Stickers
        add_to_zip("/local_stickers/", os.path.join(base_data_dir, "stickers"), "stickers")
        
        # Backgrounds
        add_to_zip("/local_backgrounds/", os.path.join(base_data_dir, "backgrounds"), "customBackgrounds", True)
        
        # Particles
        add_to_zip("/api/system/particles/raw/", os.path.join(base_data_dir, "particles"), "particleCustomUrls", True)
        
        # Fonts
        font_name = settings.get("uiFontCustom")
        if settings.get("uiFontFamily") == "custom" and font_name:
            font_dir = os.path.join(base_data_dir, "fonts")
            if os.path.exists(font_dir):
                for f in os.listdir(font_dir):
                    if f.startswith(font_name):
                        zf.write(os.path.join(font_dir, f), f"fonts/{f}")
        
        # Card Image
        card_image = settings.get("cardImage", "")
        if card_image.startswith("/local_stickers/"):
            filename = card_image.split("/")[-1]
            fpath = os.path.join(base_data_dir, "stickers", filename)
            if os.path.exists(fpath):
                zf.write(fpath, f"stickers/{filename}")
                        
    memory_file.seek(0)
    return memory_file.read()

async def import_theme_from_zip(file: UploadFile, db_session: Session):
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Only ZIP files are supported")
    
    content = await file.read()
    memory_file = io.BytesIO(content)
    from ..core.paths import DATA_DIR
    base_dir = DATA_DIR
    
    try:
        with zipfile.ZipFile(memory_file, 'r') as zf:
            if "theme.json" not in zf.namelist():
                raise HTTPException(400, "Invalid theme package: missing theme.json")
                
            theme_data = json.loads(zf.read("theme.json").decode("utf-8"))
            new_id = "theme_" + uuid.uuid4().hex[:8]
            theme_data["id"] = new_id
            theme_data["is_default"] = 0
            
            for item in zf.namelist():
                if item == "theme.json" or item.endswith("/"):
                    continue
                parts = item.split("/")
                if len(parts) != 2: continue
                folder, filename = parts[0], parts[1]
                
                # Map zip folders to data folders
                folder_map = {
                    "stickers": "stickers",
                    "customBackgrounds": "backgrounds",
                    "particleCustomUrls": "particles",
                    "fonts": "fonts"
                }
                
                target_folder = folder_map.get(folder)
                if target_folder:
                    target_dir = os.path.join(base_dir, target_folder)
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, filename)
                    if not os.path.exists(target_path):
                        with open(target_path, "wb") as f:
                            f.write(zf.read(item))
                            
            new_theme = models.Theme(
                id=new_id,
                name=theme_data.get("name", "导入的主题"),
                is_default=0,
                settings=json.dumps(theme_data.get("settings", {}))
            )
            db_session.add(new_theme)
            db_session.commit()
            
        return theme_data
    except Exception as e:
        raise HTTPException(500, f"Theme import failed: {str(e)}")
