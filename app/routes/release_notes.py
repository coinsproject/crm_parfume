"""Роуты для управления релиз-ноутсами"""
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.db import get_db
from app.models import User, ReleaseNote, Notification, Partner
from app.services.auth_service import require_permission, require_roles, get_current_user_from_cookie
from app.services.version_service import (
    create_version_and_release_note,
    get_next_version,
    get_latest_release_note,
    increment_version,
)
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
    # Для администратора показываем все релиз-ноуты, для остальных - только опубликованные
    is_admin = False
    if current_user and hasattr(current_user, "role") and current_user.role:
        is_admin = current_user.role.name == "ADMIN"
    
    if is_admin:
        # Для админа показываем все, но проверяем наличие полей
        try:
            release_notes = db.query(ReleaseNote).order_by(desc(ReleaseNote.release_date)).all()
        except Exception as e:
            # Если миграция не применена, используем безопасный запрос
            from sqlalchemy import text
            try:
                # Проверяем наличие колонок
                result = db.execute(text("PRAGMA table_info(release_notes)"))
                columns = [row[1] for row in result.fetchall()]
                if 'is_published_to_partners' not in columns:
                    # Миграция не применена, используем только базовые поля
                    release_notes = db.query(ReleaseNote).with_entities(
                        ReleaseNote.id, ReleaseNote.version, ReleaseNote.title,
                        ReleaseNote.description, ReleaseNote.release_type,
                        ReleaseNote.release_date, ReleaseNote.changes,
                        ReleaseNote.is_published, ReleaseNote.is_important,
                        ReleaseNote.created_at, ReleaseNote.updated_at,
                        ReleaseNote.created_by_user_id
                    ).order_by(desc(ReleaseNote.release_date)).all()
                else:
                    release_notes = db.query(ReleaseNote).order_by(desc(ReleaseNote.release_date)).all()
            except Exception:
                # В крайнем случае возвращаем пустой список
                release_notes = []
    else:
        # Для партнеров показываем только опубликованные для них
        # Проверяем наличие поля is_published_to_partners (на случай, если миграция еще не применена)
        try:
            release_notes = db.query(ReleaseNote).filter(
                ReleaseNote.is_published_to_partners == True
            ).order_by(desc(ReleaseNote.release_date)).all()
        except Exception:
            # Если поле не существует, показываем только опубликованные для всех
            release_notes = db.query(ReleaseNote).filter(
                ReleaseNote.is_published == True
            ).order_by(desc(ReleaseNote.release_date)).all()
    
    return templates.TemplateResponse("release_notes_list.html", {
        "request": request,
        "current_user": current_user,
        "release_notes": release_notes,
        "current_version": __version__,
        "active_menu": "release_notes",
        "is_admin": is_admin,
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
    
    # Проверяем права доступа
    is_admin = False
    if current_user and hasattr(current_user, "role") and current_user.role:
        is_admin = current_user.role.name == "ADMIN"
    
    # Проверяем доступ: если не опубликовано ни для всех, ни для партнеров - только админ
    is_published_to_partners = getattr(release_note, "is_published_to_partners", False)
    if not release_note.is_published and not is_published_to_partners:
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
    from datetime import date
    # Получаем следующую версию для подсказки
    try:
        next_version = get_next_version(db, "minor")
    except:
        next_version = __version__
    
    latest_note = get_latest_release_note(db)
    
    return templates.TemplateResponse("release_note_form.html", {
        "request": request,
        "current_user": current_user,
        "release_note": None,
        "current_version": __version__,
        "next_version": next_version,
        "latest_release_note": latest_note,
        "active_menu": "release_notes",
        "current_date": date.today().strftime('%Y-%m-%d'),
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
    is_published_to_partners: bool = Form(False),
    is_important: bool = Form(False),
    max_partner_views: Optional[int] = Form(None),
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
    
    # Обработка max_partner_views
    max_views = None
    if max_partner_views is not None:
        try:
            max_views = int(max_partner_views) if max_partner_views else None
        except (ValueError, TypeError):
            max_views = None
    
    release_note = ReleaseNote(
        version=version,
        title=title,
        description=description,
        release_type=release_type,
        release_date=release_date_obj,
        changes=changes,
        is_published=is_published,
        is_published_to_partners=is_published_to_partners,
        is_important=is_important,
        max_partner_views=max_views,
        created_by_user_id=current_user.id,
    )
    db.add(release_note)
    db.commit()
    db.refresh(release_note)
    
    # Если опубликовано для партнеров, создаём уведомления только для партнеров
    if is_published_to_partners:
        partners = db.query(Partner).filter(Partner.is_active == True).all()
        for partner in partners:
            if partner.user_id:
                notification = Notification(
                    user_id=partner.user_id,
                    type="system_update",
                    title=f"Новая версия {version}",
                    message=title,
                    related_type="release_note",
                    related_id=release_note.id,
                )
                db.add(notification)
        db.commit()
    # Если это важное обновление и опубликовано для всех, создаём уведомления для всех пользователей
    elif is_published and is_important:
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
    from datetime import date
    release_note = db.query(ReleaseNote).filter(ReleaseNote.id == note_id).first()
    if not release_note:
        raise HTTPException(status_code=404, detail="Релиз-ноутс не найден")
    
    return templates.TemplateResponse("release_note_form.html", {
        "request": request,
        "current_user": current_user,
        "release_note": release_note,
        "current_version": __version__,
        "active_menu": "release_notes",
        "current_date": date.today().strftime('%Y-%m-%d'),
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
    is_published_to_partners: bool = Form(False),
    is_important: bool = Form(False),
    max_partner_views: Optional[int] = Form(None),
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
    
    # Обработка max_partner_views
    max_views = None
    if max_partner_views is not None:
        try:
            max_views = int(max_partner_views) if max_partner_views else None
        except (ValueError, TypeError):
            max_views = None
    
    # Проверяем, было ли это опубликовано для партнеров до изменения
    was_published_to_partners = release_note.is_published_to_partners
    was_important = release_note.is_important and release_note.is_published
    
    release_note.version = version
    release_note.title = title
    release_note.description = description
    release_note.release_type = release_type
    release_note.release_date = release_date_obj
    release_note.changes = changes
    release_note.is_published = is_published
    release_note.is_published_to_partners = is_published_to_partners
    release_note.is_important = is_important
    release_note.max_partner_views = max_views
    
    # Если стало опубликовано для партнеров и раньше не было, создаём уведомления для партнеров
    if is_published_to_partners and not was_published_to_partners:
        partners = db.query(Partner).filter(Partner.is_active == True).all()
        for partner in partners:
            if partner.user_id:
                notification = Notification(
                    user_id=partner.user_id,
                    type="system_update",
                    title=f"Новая версия {version}",
                    message=title,
                    related_type="release_note",
                    related_id=release_note.id,
                )
                db.add(notification)
    # Если стало важным и опубликовано для всех, создаём уведомления
    elif is_published and is_important and not was_important:
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




