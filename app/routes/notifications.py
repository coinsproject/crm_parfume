"""Роуты для управления уведомлениями"""
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import get_db
from app.models import User, Notification
from app.services.auth_service import get_current_user_from_cookie

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def notifications_list(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    """Список уведомлений пользователя"""
    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(desc(Notification.created_at)).limit(100).all()
    
    unread_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    
    return templates.TemplateResponse("notifications_list.html", {
        "request": request,
        "current_user": current_user,
        "notifications": notifications,
        "unread_count": unread_count,
        "active_menu": "notifications",
    })


@router.post("/{notification_id}/read", response_class=JSONResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    """Отметить уведомление как прочитанное"""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    
    return {"status": "ok"}


@router.post("/read_all", response_class=JSONResponse)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    """Отметить все уведомления как прочитанные"""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({
        "is_read": True,
        "read_at": datetime.utcnow()
    })
    db.commit()
    
    return {"status": "ok"}


@router.get("/api/unread_count", response_class=JSONResponse)
async def get_unread_count(
    request: Request,
    db: Session = Depends(get_db),
):
    """Получить количество непрочитанных уведомлений"""
    # Пытаемся получить пользователя из cookie, но не выбрасываем ошибку если не авторизован
    from app.services.auth_service import get_current_user_from_request
    current_user = await get_current_user_from_request(request, db)
    
    if not current_user:
        return {"count": 0}
    
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    
    return {"count": count}







