"""Роуты для управления релиз-ноутсами"""
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import get_db
from app.models import User, ReleaseNote, Notification
from app.services.auth_service import require_permission, require_roles, get_current_user_from_cookie
from app.version import __version__

router = APIRouter(prefix="/release_notes", tags=["release_notes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def release_notes_list(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    """Список релиз-ноутсов"""
    release_notes = db.query(ReleaseNote).filter(
        ReleaseNote.is_published == True
    ).order_by(desc(ReleaseNote.release_date)).all()
    
    return templates.TemplateResponse("release_notes_list.html", {
        "request": request,
        "current_user": current_user,
        "release_notes": release_notes,
        "current_version": __version__,
        "active_menu": "release_notes",
    })


@router.get("/{note_id}", response_class=HTMLResponse)
async def release_note_detail(
    request: Request,
    note_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    """Детали релиз-ноутса"""
    release_note = db.query(ReleaseNote).filter(ReleaseNote.id == note_id).first()
    if not release_note:
        raise HTTPException(status_code=404, detail="Релиз-ноутс не найден")
    
    if not release_note.is_published:
        # Проверяем права доступа для неопубликованных
        is_admin = getattr(current_user, "role", None) and current_user.role.name == "ADMIN"
        if not is_admin:
            raise HTTPException(status_code=403, detail="Нет доступа")
    
    return templates.TemplateResponse("release_note_detail.html", {
        "request": request,
        "current_user": current_user,
        "release_note": release_note,
        "current_version": __version__,
        "active_menu": "release_notes",
    })


@router.get("/admin/new", response_class=HTMLResponse)
async def new_release_note_form(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Форма создания нового релиз-ноутса"""
    return templates.TemplateResponse("release_note_form.html", {
        "request": request,
        "current_user": current_user,
        "release_note": None,
        "current_version": __version__,
        "active_menu": "release_notes",
    })


@router.post("/admin/new", response_class=RedirectResponse)
async def create_release_note(
    version: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    release_type: str = Form("minor"),
    release_date: str = Form(...),
    changes: Optional[str] = Form(None),
    is_published: bool = Form(False),
    is_important: bool = Form(False),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Создание нового релиз-ноутса"""
    # Проверяем, что версия уникальна
    existing = db.query(ReleaseNote).filter(ReleaseNote.version == version).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Версия {version} уже существует")
    
    try:
        release_date_obj = datetime.strptime(release_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")
    
    release_note = ReleaseNote(
        version=version,
        title=title,
        description=description,
        release_type=release_type,
        release_date=release_date_obj,
        changes=changes,
        is_published=is_published,
        is_important=is_important,
        created_by_user_id=current_user.id,
    )
    db.add(release_note)
    db.commit()
    db.refresh(release_note)
    
    # Если это важное обновление и опубликовано, создаём уведомления для всех пользователей
    if is_published and is_important:
        users = db.query(User).all()
        for user in users:
            notification = Notification(
                user_id=user.id,
                type="system_update",
                title=f"Новая версия {version}",
                message=title,
                related_type="release_note",
                related_id=release_note.id,
            )
            db.add(notification)
        db.commit()
    
    return RedirectResponse(url=f"/release_notes/{release_note.id}", status_code=303)


@router.get("/admin/{note_id}/edit", response_class=HTMLResponse)
async def edit_release_note_form(
    request: Request,
    note_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Форма редактирования релиз-ноутса"""
    release_note = db.query(ReleaseNote).filter(ReleaseNote.id == note_id).first()
    if not release_note:
        raise HTTPException(status_code=404, detail="Релиз-ноутс не найден")
    
    return templates.TemplateResponse("release_note_form.html", {
        "request": request,
        "current_user": current_user,
        "release_note": release_note,
        "current_version": __version__,
        "active_menu": "release_notes",
    })


@router.post("/admin/{note_id}/edit", response_class=RedirectResponse)
async def update_release_note(
    note_id: int,
    version: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    release_type: str = Form("minor"),
    release_date: str = Form(...),
    changes: Optional[str] = Form(None),
    is_published: bool = Form(False),
    is_important: bool = Form(False),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Обновление релиз-ноутса"""
    release_note = db.query(ReleaseNote).filter(ReleaseNote.id == note_id).first()
    if not release_note:
        raise HTTPException(status_code=404, detail="Релиз-ноутс не найден")
    
    # Проверяем уникальность версии (если изменилась)
    if release_note.version != version:
        existing = db.query(ReleaseNote).filter(ReleaseNote.version == version).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Версия {version} уже существует")
    
    try:
        release_date_obj = datetime.strptime(release_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")
    
    # Проверяем, было ли это важное обновление до изменения
    was_important = release_note.is_important and release_note.is_published
    
    release_note.version = version
    release_note.title = title
    release_note.description = description
    release_note.release_type = release_type
    release_note.release_date = release_date_obj
    release_note.changes = changes
    release_note.is_published = is_published
    release_note.is_important = is_important
    
    # Если стало важным и опубликовано, создаём уведомления
    if is_published and is_important and not was_important:
        users = db.query(User).all()
        for user in users:
            notification = Notification(
                user_id=user.id,
                type="system_update",
                title=f"Новая версия {version}",
                message=title,
                related_type="release_note",
                related_id=release_note.id,
            )
            db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/release_notes/{release_note.id}", status_code=303)




