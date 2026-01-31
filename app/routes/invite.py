from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Invitation, User, Notification, Role, Partner
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

    # Проверяем, является ли приглашение для партнера
    from app.models import Role
    role = db.query(Role).filter(Role.id == invitation.role_id).first()
    is_partner = role and role.name == "PARTNER"
    
    return templates.TemplateResponse("invite_accept.html", {
        "request": request,
        "email": invitation.email,
        "token": token,
        "is_partner": is_partner,
        "invitation": invitation
    })


@router.post("/invite/{token}", response_class=JSONResponse)
async def accept_invitation(
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...),
    email: str = Form(...),
    username: Optional[str] = Form(None),
    partner_full_name: Optional[str] = Form(None),
    partner_phone: Optional[str] = Form(None),
    partner_telegram: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Создание пользователя по приглашению с ожиданием активации администратором."""
    invitation, status, message = _invitation_status(token, db)

    if status != "valid":
        raise HTTPException(status_code=400, detail=message)

    if password != password_confirm:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")

    # Определяем логин: если не указан, используем email
    final_username = username.strip() if username and username.strip() else email.strip()
    
    existing_user = db.query(User).filter(User.username == final_username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Логин уже занят")

    existing_user_by_email = db.query(User).filter(User.email == email).first()
    if existing_user_by_email:
        raise HTTPException(status_code=400, detail="Email уже используется")

    # Проверяем роль
    from app.models import Role
    role = db.query(Role).filter(Role.id == invitation.role_id).first()
    is_partner = role and role.name == "PARTNER"
    
    # Если роль PARTNER, создаем партнера
    partner_id = None
    if is_partner:
        # Используем данные из приглашения или из формы
        partner_name = (partner_full_name or invitation.partner_full_name or "").strip()
        partner_phone_val = (partner_phone or invitation.partner_phone or "").strip()
        partner_telegram_val = (partner_telegram or invitation.partner_telegram or "").strip()
        
        if not partner_name or len(partner_name) < 5:
            raise HTTPException(status_code=400, detail="Укажите ФИО партнёра (минимум 5 символов)")
        
        phone_clean = "".join(ch for ch in partner_phone_val if ch.isdigit())
        if not phone_clean or len(phone_clean) < 10:
            raise HTTPException(status_code=400, detail="Укажите телефон (не меньше 10 цифр)")
        
        if not partner_telegram_val:
            raise HTTPException(status_code=400, detail="Укажите Telegram (ник)")
        
        # Создаем партнера
        from app.models import Partner
        partner = Partner(
            name=partner_name,
            full_name=partner_name,
            phone=partner_phone_val,
            telegram=partner_telegram_val,
            telegram_nick=partner_telegram_val,
            is_active=False,  # Не активен до активации администратором
            status="active"
        )
        db.add(partner)
        db.flush()
        partner_id = partner.id

    user = create_user_from_invitation(
        invitation=invitation,
        username=final_username,
        email=email,
        password=password,
        full_name=None,  # Для партнера full_name будет в партнере
        db=db
    )
    
    # Связываем пользователя с партнером
    if partner_id:
        user.partner_id = partner_id
        partner = db.query(Partner).filter(Partner.id == partner_id).first()
        if partner:
            partner.user_id = user.id
        db.add(user)
        db.add(partner)

    mark_invitation_used(invitation, db)
    
    # Создаем уведомления для всех администраторов о новом пользователе, ожидающем активации
    admin_role = db.query(Role).filter(Role.name == "ADMIN").first()
    if admin_role:
        admin_users = db.query(User).filter(
            User.role_id == admin_role.id,
            User.deleted_at.is_(None)
        ).all()
        
        user_type = "партнёр" if is_partner else "пользователь"
        partner_info = ""
        if is_partner and partner_id:
            partner_obj = db.query(Partner).filter(Partner.id == partner_id).first()
            if partner_obj:
                partner_info = f" ({partner_obj.full_name or partner_obj.name})"
        
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                type="user_pending_activation",
                title=f"Новый {user_type} ожидает активации",
                message=f"{final_username}{partner_info} ({email}) зарегистрировался и ожидает активации",
                related_type="user",
                related_id=user.id,
            )
            db.add(notification)
    
    db.commit()
    
    # Отправляем email и Telegram уведомления администраторам в фоновом режиме
    def send_notifications():
        """Функция для отправки уведомлений в фоновом режиме"""
        try:
            from app.services.email_service import email_service
            from app.services.telegram_service import telegram_service
            import asyncio
            
            # Подготовка данных для уведомлений
            activation_url = "http://194.87.27.103:8000/settings/users"
            
            # Email уведомления
            email_subject = f"Новый {user_type} ожидает активации"
            email_body = f"""Здравствуйте!

Новый {user_type} зарегистрировался в системе и ожидает активации:

Имя пользователя: {final_username}
Email: {email}
{f'Партнёр: {partner_info}' if partner_info else ''}

Пожалуйста, активируйте пользователя в разделе "Настройки" → "Пользователи".

Ссылка: {activation_url}

---
Это автоматическое уведомление от Parfume CRM.
"""
            
            email_html_body = f"""<html>
<body>
    <h2>Новый {user_type} ожидает активации</h2>
    <p>Новый {user_type} зарегистрировался в системе и ожидает активации:</p>
    <ul>
        <li><strong>Имя пользователя:</strong> {final_username}</li>
        <li><strong>Email:</strong> {email}</li>
        {f'<li><strong>Партнёр:</strong> {partner_info}</li>' if partner_info else ''}
    </ul>
    <p><a href="{activation_url}">Активировать пользователя</a></p>
    <hr>
    <p><small>Это автоматическое уведомление от Parfume CRM.</small></p>
</body>
</html>"""
            
            # Telegram уведомления
            telegram_message = f"""🔔 <b>Новый {user_type} ожидает активации</b>

👤 <b>Имя:</b> {final_username}
📧 <b>Email:</b> {email}
{f'🤝 <b>Партнёр:</b> {partner_info}' if partner_info else ''}

🔗 <a href="{activation_url}">Активировать пользователя</a>"""
            
            # Отправка email всем администраторам
            for admin in admin_users:
                if admin.email:
                    asyncio.run(email_service.send_email(
                        to_email=admin.email,
                        subject=email_subject,
                        body=email_body,
                        html_body=email_html_body
                    ))
            
            # Отправка Telegram уведомления всем администраторам
            asyncio.run(telegram_service.notify_admins(telegram_message))
        except Exception as e:
            # Логируем ошибку, но не прерываем процесс регистрации
            auth_logger.error(f"Failed to send email/telegram notifications: {e}", exc_info=True)
    
    # Добавляем задачу в фоновые задачи
    background_tasks.add_task(send_notifications)
    
    auth_logger.info(f"Invitation {invitation.id} accepted by {final_username}")

    return {
        "success": True,
        "message": "Профиль создан и ожидает активации администратором",
        "user_id": user.id
    }
