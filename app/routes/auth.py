from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import pyotp
from jose import jwt, JWTError
from app.db import get_db
from app.models import User, BackupCode
from app.services.auth_service import verify_password, create_access_token, require_roles, get_current_user_from_cookie
from app.config import settings
from app.services.rate_limit_service import rate_limit_service, check_auth_rate_limit
from app.services.two_fa_service import verify_totp_code, verify_backup_code_for_user, check_2fa_attempts_limit, increment_2fa_failed_attempts, reset_2fa_attempts
from app.logging_config import auth_logger

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.post("/register")
async def register_user(
    username: str,
    email: str,
    password: str,
    role_name: str = "MANAGER",  # по умолчанию создаем менеджеров
    current_user: User = Depends(require_roles(["ADMIN"])),  # Только администратор может регистрировать пользователей
    db: Session = Depends(get_db)
):
    """
    Регистрация нового пользователя (только администратором)
    """
    # Проверяем, существует ли пользователь с таким username или email
    existing_user = db.query(User).filter(
        ((User.username == username) | (User.email == email))
        & (User.deleted_at.is_(None))
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    from app.models import Role
    
    # Проверяем, существует ли роль
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_40_BAD_REQUEST,
            detail=f"Role '{role_name}' does not exist"
        )
    
    from app.services.auth_service import hash_password
    hashed_password = hash_password(password)
    
    new_user = User(
        username=username,
        email=email,
        password_hash=hashed_password,
        role_id=role.id,
        is_active=True,
        is_2fa_enabled=True  # По умолчанию 2FA включена для новых пользователей
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "user_id": new_user.id}


from fastapi import Form

@router.post("/login")
async def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Аутентификация пользователя
    """
    # Проверяем рейт-лимит для IP-адреса
    client_ip = request.client.host
    if not check_auth_rate_limit(client_ip, db):
        auth_logger.warning(f"Rate limit exceeded for IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа с вашего IP-адреса. Пожалуйста, попробуйте позже."
        )
    
    auth_logger.info(f"Login attempt for user: {username} from IP {client_ip}")
    
    # Находим пользователя по username
    user = db.query(User).filter(User.username == username, User.deleted_at.is_(None)).first()
    
    # Проверяем, существует ли пользователь
    if not user:
        auth_logger.warning(f"Failed login attempt for non-existent user: {username} from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем, активен ли пользователь
    if not user.is_active:
        auth_logger.warning(f"Login attempt for deactivated user: {username} from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.pending_activation:
        auth_logger.warning(f"Login attempt for pending activation user: {username} from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is awaiting activation by administrator",
        )

    # Проверяем пароль
    if not verify_password(password, user.password_hash):
        auth_logger.warning(f"Failed login attempt with wrong password for user: {username} from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Обновляем время последнего входа
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    # Проверяем, включена ли 2FA
    if user.is_2fa_enabled:
        # Проверяем, не заблокирован ли пользователь для 2FA
        if not check_2fa_attempts_limit(user, db):
            auth_logger.warning(f"2FA attempts limit exceeded for user: {user.username}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток ввода 2FA. Пожалуйста, попробуйте позже."
            )
        
        # Создаем временный токен для 2FA с коротким сроком действия
        temp_token_data = {
            "sub": str(user.id),
            "two_factor_pending": True,
            "username": user.username
        }
        temp_token = create_access_token(
            data=temp_token_data,
            expires_delta=timedelta(minutes=10),  # 10 минут для ввода 2FA
            is_2fa_verified=False  # Временный токен для прохождения 2FA, не прошел проверку
        )
        
        # Возвращаем JSON с требованием 2FA и устанавливаем временный токен в cookie
        response = JSONResponse(content={
            "requires_2fa": True,
            "message": "Two-factor authentication required"
        })
        response.set_cookie(key="temp_token", value=temp_token, httponly=True, samesite="lax", max_age=600)  # 10 минут
        auth_logger.info(f"Login successful for user: {user.username}, 2FA required")
        return response
    else:
        # Создаем токен доступа
        access_token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role_id": user.role_id
        }
        access_token = create_access_token(
            data=access_token_data,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        response = {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user.id,
            "username": user.username
        }
        # Возвращаем токен в виде cookie для веб-браузера
        json_response = JSONResponse(content=response)
        json_response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
        auth_logger.info(f"Login successful for user: {username}")
        return json_response



# Шаблоны для страниц авторизации
templates = Jinja2Templates(directory="app/templates")

# Маршруты для отображения страниц авторизации
@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    return templates.TemplateResponse("auth_login.html", {"request": request})


@router.get("/2fa", response_class=HTMLResponse)
async def get_2fa_page(request: Request):
    return templates.TemplateResponse("auth_2fa.html", {"request": request})


@router.post("/2fa/verify")
async def verify_2fa(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Проверка 2FA кода (TOTP или резервный код)
    """
    try:
        # Получаем временный токен из cookie
        temp_token = request.cookies.get("temp_token")
        if not temp_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No temporary token found. Please restart the login process."
            )
            
        # Декодируем временный токен
        payload = jwt.decode(temp_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        two_factor_pending: bool = payload.get("two_factor_pending")
        
        if user_id is None or two_factor_pending is not True:
            auth_logger.warning(f"Invalid 2FA token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Находим пользователя
        user = db.query(User).filter(User.id == int(user_id), User.deleted_at.is_(None)).first()
        if not user:
            auth_logger.warning(f"User not found for 2FA verification: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Проверяем, что 2FA действительно включена у пользователя
        if not user.is_2fa_enabled:
            auth_logger.warning(f"2FA not enabled for user: {user.username}, but 2FA verification was attempted")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-factor authentication is not enabled for this user"
            )
        
        # Проверяем лимит попыток 2FA
        if not check_2fa_attempts_limit(user, db):
            auth_logger.warning(f"2FA attempts limit exceeded for user: {user.username}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток ввода 2FA. Пожалуйста, попробуйте позже."
            )
        
        # Проверяем TOTP-код
        totp_verification = verify_totp_code(user.totp_secret, code)
        
        if totp_verification:
            # Сбрасываем счетчик неудачных попыток при успешной аутентификации
            reset_2fa_attempts(user, db)
            
            # Создаем основной токен
            access_token_data = {
                "sub": str(user.id),
                "username": user.username,
                "role_id": user.role_id
            }
            access_token = create_access_token(
                data=access_token_data,
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
                is_2fa_verified=True
            )
            
            response_body = {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user.id,
                "username": user.username
            }
            json_response = JSONResponse(content=response_body)
            json_response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
            # Удаляем временный токен
            json_response.set_cookie(key="temp_token", value="", httponly=True, samesite="lax", max_age=0)
            auth_logger.info(f"2FA verification successful for user: {user.username}")
            return json_response
        
        # Если TOTP не прошёл, проверяем резервные коды
        backup_code_verified = verify_backup_code_for_user(user.id, code, db)
        
        if backup_code_verified:
            # Сбрасываем счетчик неудачных попыток при успешной аутентификации
            reset_2fa_attempts(user, db)
            
            # Создаем основной токен
            access_token_data = {
                "sub": str(user.id),
                "username": user.username,
                "role_id": user.role_id
            }
            access_token = create_access_token(
                data=access_token_data,
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
                is_2fa_verified=True
            )
            
            response_body = {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user.id,
                "username": user.username
            }
            json_response = JSONResponse(content=response_body)
            json_response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
            # Удаляем временный токен
            json_response.set_cookie(key="temp_token", value="", httponly=True, samesite="lax", max_age=0)
            auth_logger.info(f"2FA verification successful using backup code for user: {user.username}")
            return json_response
        
        # При неудачной проверке увеличиваем счетчик неудачных попыток
        increment_2fa_failed_attempts(user, db)
        auth_logger.warning(f"2FA verification failed for user: {user.username}, invalid code: {code[:3]}...")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный 2FA код. Пожалуйста, проверьте приложение-аутентификатор или используйте резервный код."
        )
        
    except JWTError as e:
        auth_logger.error(f"JWT error during 2FA verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

@router.post("/logout")
async def logout_user_post(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    """
    Выход пользователя - удаление токена из cookie (POST)
    """
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.set_cookie(key="access_token", value="", httponly=True, samesite="lax", max_age=0)
    auth_logger.info(f"User {current_user.username} logged out via POST from IP {request.client.host if request.client else 'unknown'}")
    return response


@router.get("/logout")
async def logout_user_get(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    """
    Выход пользователя - удаление токена из cookie (GET)
    """
    response = RedirectResponse(url="/auth/login")
    response.set_cookie(key="access_token", value="", httponly=True, samesite="lax", max_age=0)
    auth_logger.info(f"User {current_user.username} logged out via GET")
    return response

# Зависимость для получения текущего пользователя
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id), User.deleted_at.is_(None)).first()
    if user is None:
        raise credentials_exception
    return user
