from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Invitation, User
from app.services.invitation_service import (
    create_user_from_invitation,
    mark_invitation_used
)
from app.logging_config import auth_logger

router = APIRouter(tags=["invites"])

templates = Jinja2Templates(directory="app/templates")


def _invitation_status(token: str, db: Session) -> Tuple[Optional[Invitation], str, str]:
    """Return invitation, status code and human-friendly message."""
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if not invitation:
        return None, "not_found", "Приглашение не найдено или ссылка некорректна."
    if invitation.is_used:
        return invitation, "used", "Ссылка уже использована."
    if invitation.expires_at < datetime.utcnow():
        return invitation, "expired", "Срок действия приглашения истёк. Запросите новую ссылку у администратора."
    return invitation, "valid", ""


@router.get("/invite/{token}", response_class=HTMLResponse)
async def get_invite_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """Страница для ввода данных по приглашению."""
    invitation, status, message = _invitation_status(token, db)

    if status != "valid":
        return templates.TemplateResponse("invite_invalid.html", {
            "request": request,
            "message": message
        })

    return templates.TemplateResponse("invite_accept.html", {
        "request": request,
        "email": invitation.email,
        "token": token
    })


@router.post("/invite/{token}", response_class=JSONResponse)
async def accept_invitation(
    token: str,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    full_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Создание пользователя по приглашению с ожиданием активации администратором."""
    invitation, status, message = _invitation_status(token, db)

    if status != "valid":
        raise HTTPException(status_code=400, detail=message)

    if password != password_confirm:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Логин уже занят")

    if email:
        existing_user_by_email = db.query(User).filter(User.email == email).first()
        if existing_user_by_email:
            raise HTTPException(status_code=400, detail="Email уже используется")

    final_email = email if email else invitation.email

    user = create_user_from_invitation(
        invitation=invitation,
        username=username,
        email=final_email,
        password=password,
        full_name=full_name,
        db=db
    )

    mark_invitation_used(invitation, db)
    auth_logger.info(f"Invitation {invitation.id} accepted by {username}")

    return {
        "success": True,
        "message": "Профиль создан и ожидает активации администратором",
        "user_id": user.id
    }
