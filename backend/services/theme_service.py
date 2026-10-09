import os
import json
import io
import logging
import zipfile
import uuid
from fastapi import HTTPException, UploadFile, Response
from sqlalchemy.orm import Session
from ..database import models
from ..core.paths import DATA_DIR

logger = logging.getLogger(__name__)

#: 主题包内单个成员文件的体积上限（防 zip 炸弹，50 MB）
MAX_THEME_MEMBER_BYTES = 50 * 1024 * 1024

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

        # [修复] 原实现用 `os.path.dirname(os.path.dirname(__file__)) + "/data"` 拼路径。
        # 打包版（build.bat 使用 --onefile --add-data "backend/data;data"）中模块 __file__
        # 位于 sys._MEIPASS 下，该表达式解析到 <MEIPASS>/backend/data —— 该目录并不存在
        # （数据被放到了 <MEIPASS>/data），而真实用户数据在 DATA_DIR（<exe目录>/data）。
        # 结果：导出主题时所有自定义贴纸/背景/粒子/字体都找不到，zip 里只剩 theme.json，
        # 导入回来主题就是残缺的；开发环境下路径恰好正确，因此该缺陷被长期掩盖。
        base_data_dir = DATA_DIR
        
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
                # [修复] 主题包是不可信输入（用户会互相分享 .zip），原先只按 "/" 拆两段，
                # 且校验的是「段数」而不是「名字」：
                #   - `stickers/..\..\evil.exe` 拆分后 filename 为 `..\..\evil.exe`，
                #     Windows 下会解析到 <DATA_DIR>/stickers 之外，写入任意文件；
                #   - 未做体积限制，超大成员会撑爆内存（zip 炸弹）。
                # 现在只取纯文件名、剥掉任何目录成分，并做规范化前缀二次校验 + 体积上限。
                normalized = item.replace("\\", "/")
                parts = [p for p in normalized.split("/") if p not in ("", ".")]
                if len(parts) != 2:
                    continue
                folder, filename = parts[0], parts[1]
                filename = os.path.basename(filename)
                if not filename or filename in (".", ".."):
                    logger.warning(f"[主题导入] 跳过非法成员名: {item}")
                    continue

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
                    target_path = os.path.abspath(os.path.join(target_dir, filename))
                    # 双重确认：解析后的绝对路径必须仍位于目标目录之内
                    if os.path.dirname(target_path) != os.path.abspath(target_dir):
                        logger.warning(f"[主题导入] 跳过越界成员: {item}")
                        continue
                    if not os.path.exists(target_path):
                        info = zf.getinfo(item)
                        if info.file_size > MAX_THEME_MEMBER_BYTES:
                            logger.warning(
                                f"[主题导入] 跳过超大成员（{info.file_size} 字节）: {item}")
                            continue
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
    except HTTPException:
        # [修复] 原实现的兜底 except 会把上面主动抛出的 400
        # （"missing theme.json"）重新包装成 500 "Theme import failed: 400: ..."，
        # 用户看到的变成「服务器内部错误」而不是「这个文件不是有效的主题包」。
        # HTTPException 必须原样透传（与 backend/main.py 的 /api/proxy/image 一致）。
        db_session.rollback()
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(500, f"Theme import failed: {str(e)}")
