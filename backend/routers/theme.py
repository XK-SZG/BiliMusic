import json
import uuid
import io
import zipfile
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import models, db
from ..services import theme_service

router = APIRouter(prefix="/api/themes", tags=["themes"])

class ThemeItem(BaseModel):
    id: str
    name: str
    is_default: int
    settings: dict

class SyncThemeReq(BaseModel):
    themes: List[ThemeItem]
    active_theme_id: str

@router.post("/sync")
def sync_themes(req: SyncThemeReq, db_session: Session = Depends(db.get_db)):
    server_themes = db_session.query(models.Theme).all()
    if not server_themes:
        for t in req.themes:
            new_theme = models.Theme(
                id=t.id,
                name=t.name,
                is_default=t.is_default,
                settings=json.dumps(t.settings)
            )
            db_session.add(new_theme)
        db_session.commit()
        return {"status": "success", "mismatch": False}
    
    server_list = []
    has_bilibili = any(st.id == 'theme_bilibili' for st in server_themes)
    if not has_bilibili:
        for frontend_theme in req.themes:
            if frontend_theme.id == 'theme_bilibili':
                new_theme = models.Theme(
                    id=frontend_theme.id,
                    name=frontend_theme.name,
                    is_default=frontend_theme.is_default,
                    settings=json.dumps(frontend_theme.settings)
                )
                db_session.add(new_theme)
                server_themes.append(new_theme)
        db_session.commit()
    
    for st in server_themes:
        server_list.append({
            "id": st.id,
            "name": st.name,
            "is_default": st.is_default,
            "settings": json.loads(st.settings)
        })
    
    return {
        "status": "success",
        "mismatch": True,
        "server_themes": server_list
    }

@router.post("")
def save_theme(theme: ThemeItem, db_session: Session = Depends(db.get_db)):
    t = db_session.query(models.Theme).filter(models.Theme.id == theme.id).first()
    if t:
        t.name = theme.name
        t.settings = json.dumps(theme.settings)
    else:
        t = models.Theme(
            id=theme.id,
            name=theme.name,
            is_default=theme.is_default,
            settings=json.dumps(theme.settings)
        )
        db_session.add(t)
    db_session.commit()
    return {"status": "success"}

@router.delete("/{theme_id}")
def delete_theme(theme_id: str, db_session: Session = Depends(db.get_db)):
    t = db_session.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if t and t.is_default == 0:
        db_session.delete(t)
        db_session.commit()
    return {"status": "success"}

@router.get("/export/{theme_id}")
def export_theme(theme_id: str, db_session: Session = Depends(db.get_db)):
    zip_data = theme_service.export_theme_to_zip(theme_id, db_session)
    return Response(
        zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=theme_{theme_id}.zip"}
    )

@router.post("/import")
async def import_theme(file: UploadFile = File(...), db_session: Session = Depends(db.get_db)):
    theme_data = await theme_service.import_theme_from_zip(file, db_session)
    return {"status": "success", "theme": theme_data}
