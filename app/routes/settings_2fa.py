from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, BackupCode
from app.services.auth_service import get_current_user_from_cookie, verify_password, require_roles
from app.services.two_fa_service import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
    generate_qr_code,
    enable_2fa_for_user,
    disable_2fa_for_user
)
from app.logging_config import two_fa_logger, auth_logger
import secrets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings/security", response_class=HTMLResponse)
async def get_security_settings(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Страница настройки безопасности (2FA) - только для администраторов
    """
    return templates.TemplateResponse("settings_2fa.html", {
        "request": request,
        "current_user": current_user,
        "is_2fa_enabled": current_user.is_2fa_enabled,
        "active_menu": "settings_security"
    })


@router.get("/settings/2fa", response_class=HTMLResponse)
async def get_2fa_settings(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Страница настроек 2FA - только для администраторов
    """
    if current_user.is_2fa_enabled:
        # Если 2FA уже включена, показываем статус
        # Получаем резервные коды для отображения
        backup_codes = db.query(BackupCode).filter(
            BackupCode.user_id == current_user.id,
            BackupCode.is_used == False
        ).all()
        backup_codes_list = [code.code_hash for code in backup_codes]
        return templates.TemplateResponse("settings_2fa_enabled.html", {
            "request": request,
            "current_user": current_user,
            "backup_codes": backup_codes_list
        })
    else:
        # Если 2FA не включена, показываем страницу настройки
        return templates.TemplateResponse("settings_2fa_disabled.html", {
            "request": request,
            "current_user": current_user
        })

@router.post("/settings/2fa/setup")
async def setup_2fa(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Инициализация настройки 2FA - только для администраторов
    """
    
    if current_user.is_2fa_enabled:
        from app.logging_config import two_fa_logger
        two_fa_logger.warning(f"User {current_user.username} attempted to setup 2FA when already enabled")
        raise HTTPException(status_code=400, detail="2FA already enabled")

    # Генерируем новый временный секрет
    secret = generate_totp_secret()
    current_user.totp_secret_temp = secret
    db.commit()

    # Генерируем URI для QR-кода
    totp_uri = get_totp_uri(secret, current_user.username)
    qr_data = generate_qr_code(totp_uri)

    from app.logging_config import two_fa_logger
    two_fa_logger.info(f"2FA setup initiated for user: {current_user.username}")
    return {
        "message": "2FA setup initialized",
        "totp_uri": totp_uri,
        "qr_data": qr_data
    }


@router.post("/settings/2fa/enable")
async def enable_2fa(
    request: Request,
    code: str = Form(...),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Включение 2FA после проверки кода - только для администраторов
    """
    
    if current_user.is_2fa_enabled:
        auth_logger.warning(f"User {current_user.username} attempted to enable 2FA when already enabled")
        raise HTTPException(status_code=400, detail="2FA already enabled")
    
    if not current_user.totp_secret_temp:
        auth_logger.warning(f"User {current_user.username} attempted to enable 2FA without temporary secret")
        raise HTTPException(status_code=400, detail="No temporary secret found. Please restart setup.")
    
    # Проверяем код с временным секретом
    # Проверяем код с временным секретом
    if verify_totp_code(current_user.totp_secret_temp, code):
        # Если код верен, включаем 2FA и генерируем резервные коды
        backup_codes = enable_2fa_for_user(current_user, current_user.totp_secret_temp, db)
        auth_logger.info(f"2FA enabled for user: {current_user.username}")
        
        # Создаем новый токен с признаком 2FA-верификации, чтобы пользователь не был разлогинен
        from app.services.auth_service import create_access_token
        access_token_data = {
            "sub": str(current_user.id),
            "username": current_user.username,
            "role_id": current_user.role_id
        }
        new_access_token = create_access_token(
            data=access_token_data,
            is_2fa_verified=True # Отмечаем, что 2FA пройдена
        )
        
        # Возвращаем JSON-ответ с новым токеном
        response_data = {
            "success": True,
            "message": "2FA successfully enabled",
            "backup_codes": backup_codes,
            "access_token": new_access_token  # Новый токен с 2FA-верификацией
        }
        return response_data
    else:
        auth_logger.warning(f"Invalid 2FA code provided by user: {current_user.username}")
        raise HTTPException(status_code=400, detail="Неверный код. Пожалуйста, проверьте приложение и попробуйте снова.")

@router.post("/settings/2fa/disable")
async def disable_2fa(
    request: Request,
    password: str = Form(...),  # Для безопасности требуем повторный ввод пароля
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Отключение 2FA - только для администраторов
    """
    
    if not current_user.is_2fa_enabled:
        auth_logger.warning(f"User {current_user.username} attempted to disable 2FA when not enabled")
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    # Проверяем пароль пользователя
    if not verify_password(password, current_user.password_hash):
        auth_logger.warning(f"User {current_user.username} provided wrong password to disable 2FA")
        raise HTTPException(status_code=400, detail="Неверный пароль")

    # Отключаем 2FA
    disable_2fa_for_user(user=current_user, db=db)
    auth_logger.info(f"2FA successfully disabled for user: {current_user.username}")

    return {"message": "2FA successfully disabled"}
