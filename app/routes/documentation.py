"""
Роуты для документации и инструкций
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import get_db
from app.models import User, ReleaseNote
from app.services.auth_service import require_roles

router = APIRouter(prefix="/settings", tags=["documentation"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/docs", response_class=HTMLResponse)
async def documentation_index(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Главная страница документации"""
    # Получаем последние релиз-ноутсы с инструкциями
    release_notes = db.query(ReleaseNote).order_by(desc(ReleaseNote.release_date)).limit(10).all()
    
    return templates.TemplateResponse("documentation_index.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_docs",
        "release_notes": release_notes
    })


@router.get("/docs/notifications", response_class=HTMLResponse)
async def documentation_notifications(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Инструкции по настройке уведомлений"""
    return templates.TemplateResponse("documentation_notifications.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_docs"
    })


@router.get("/docs/updates", response_class=HTMLResponse)
async def documentation_updates(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Инструкции по обновлению системы"""
    return templates.TemplateResponse("documentation_updates.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_docs"
    })


@router.get("/docs/release/{note_id}", response_class=HTMLResponse)
async def documentation_release_note(
    request: Request,
    note_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Документация для конкретного релиза"""
    release_note = db.query(ReleaseNote).filter(ReleaseNote.id == note_id).first()
    
    if not release_note:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Релиз-ноутс не найден")
    
    return templates.TemplateResponse("documentation_release_note.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_docs",
        "release_note": release_note
    })


