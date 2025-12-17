from datetime import datetime, timedelta
from typing import Optional, List, Iterable, Union
import bcrypt
import pyotp
import secrets
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi import Security
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User

# Определяем oauth2_scheme здесь, чтобы избежать циклических импортов
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def hash_password(plain_password: str) -> str:
    """Хеширование пароля с использованием bcrypt"""
    pwd_bytes = plain_password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверка соответствия пароля хешу"""
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, is_2fa_verified: bool = False) -> str:
    """Создание JWT токена доступа"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    # Если 2FA пройдена, добавляем признак в токен
    if is_2fa_verified:
        to_encode.update({"2fa_verified": True})
        from app.logging_config import auth_logger
        username = data.get("username", "unknown")
        auth_logger.info(f"Created access token with 2FA verification for user: {username}")
    else:
        from app.logging_config import auth_logger
        username = data.get("username", "unknown")
        auth_logger.info(f"Created access token without 2FA verification for user: {username}")
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def generate_totp_secret() -> str:
    """Генерация TOTP-секрета"""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Формирование otpauth URI"""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="ParfumeCRM"
    )


def verify_totp_code(secret: str, code: str) -> bool:
    """Проверка TOTP-кода"""
    totp = pyotp.TOTP(secret)
    # valid_window=1 позволяет +/- один 30-секундный шаг для уменьшения проблем с рассинхронизацией
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Генерация резервных кодов"""
    codes = []
    for _ in range(count):
        # Генерируем 8-символьный код из букв и цифр
        code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567') for _ in range(8))
        codes.append(code)
    return codes


def hash_backup_code(plain_code: str) -> str:
    """Хеширование резервного кода с использованием bcrypt"""
    pwd_bytes = plain_code.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_backup_code(plain_code: str, hashed_code: str) -> bool:
    """Проверка соответствия резервного кода хешу"""
    pwd_bytes = plain_code.encode('utf-8')
    hash_bytes = hashed_code.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def get_current_user(
    token: str = Security(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Получение текущего пользователя из токена"""
    print(f"get_current_user called with token: {token[:20] if token else 'None'}...")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        print(f"Decoded user_id: {user_id}")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        print(f"JWT decode error: {e}")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    print(f"User from DB: {user.username if user else 'None'}")
    if user is None:
        raise credentials_exception
    return user


def get_current_user_optional(
    token: str = Security(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Получение текущего пользователя (опционально, без обязательной аутентификации)
    """
    print(f"get_current_user_optional called with token: {token[:20] if token else 'None'}...")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        print(f"Decoded user_id in optional: {user_id}")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == int(user_id)).first()
        print(f"User from DB in optional: {user.username if user else 'None'}")
        if user is None:
            return None
        return user
    except JWTError as e:
        print(f"JWT decode error in optional: {e}")
        return None


def get_token_from_request(request: Request):
    """
    Извлечение токена из запроса (из заголовка Authorization или из cookie)
    """
    # Сначала пробуем получить токен из заголовка Authorization
    token = request.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token[7:]
    else:
        # Если в заголовке нет, пробуем получить из cookie
        token = request.cookies.get("access_token")
    
    return token


async def get_current_user_from_request(request: Request, db: Session = Depends(get_db)):
    """
    Получение текущего пользователя из запроса (из заголовка Authorization или из cookie)
    """
    token = get_token_from_request(request)
    
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == int(user_id), User.deleted_at.is_(None)).first()
        if user is None:
            return None
        return user
    except JWTError:
        return None


def get_user_permission_keys(user: User, db: Session) -> set[str]:
    """
    Набор permission.key для текущей роли пользователя.
    ADMIN считается имеющим все права (возвращаем {"*"}).
    """
    from app.models import Role, Permission, RolePermission

    role = user.role or db.query(Role).filter(Role.id == user.role_id).first()
    if role and role.name == "ADMIN":
        return {"*"}
    if not role:
        return set()
    rows = (
        db.query(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role.id)
        .all()
    )
    return {r[0] for r in rows}


def get_current_user_or_redirect():
    """
    Получение текущего пользователя из запроса или вызов HTTPException
    """
    async def current_user_dependency(request: Request, db: Session = Depends(get_db)):
        token = get_token_from_request(request)
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    return current_user_dependency


def verify_backup_code_for_user(user_id: int, plain_code: str, db: Session) -> bool:
    """
    Проверка резервного кода для пользователя
    """
    from app.models import BackupCode
    
    # Находим все неиспользованные резервные коды пользователя
    backup_codes = db.query(BackupCode).filter(
        BackupCode.user_id == user_id,
        BackupCode.is_used == False
    ).all()
    
    # Проверяем каждый код
    for backup_code in backup_codes:
        if verify_backup_code(plain_code, backup_code.code_hash):
            # Помечаем код как использованный
            backup_code.is_used = True
            db.commit()
            return True
    
    return False


def check_2fa_attempts_limit(user: User, db: Session) -> bool:
    """
    Проверка лимита попыток 2FA для пользователя
    """
    from datetime import datetime, timedelta
    
    # Если не было попыток или прошло более 5 минут с последней попытки
    if not user.last_2fa_attempt_at or (datetime.utcnow() - user.last_2fa_attempt_at) > timedelta(minutes=5):
        # Сбрасываем счетчик неудачных попыток
        user.failed_2fa_attempts = 0
        user.last_2fa_attempt_at = None
        db.commit()
        return True
    
    # Проверяем, не превышен ли лимит попыток (например, 5 за 5 минут)
    return user.failed_2fa_attempts < 5 # Максимум 5 попыток в течение 5 минут


def increment_2fa_failed_attempts(user: User, db: Session):
    """
    Увеличение счетчика неудачных попыток 2FA
    """
    from datetime import datetime
    user.failed_2fa_attempts += 1
    user.last_2fa_attempt_at = datetime.utcnow()
    db.commit()


def reset_2fa_attempts(user: User, db: Session):
    """
    Сброс счетчика неудачных попыток 2FA (при успешной аутентификации)
    """
    user.failed_2fa_attempts = 0
    user.last_2fa_attempt_at = None
    db.commit()


def require_roles(allowed_roles: List[str]):
    """Зависимость для проверки ролей пользователя"""
    def dependency(
        current_user: User = Depends(get_current_user_from_cookie),
        db: Session = Depends(get_db)
    ):
        # Загружаем роль, если она не загружена
        if not hasattr(current_user, 'role') or not current_user.role:
            from app.models import Role
            role = db.query(Role).filter(Role.id == current_user.role_id).first()
        else:
            role = current_user.role
        
        if role and role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав"
            )
        current_user.role = role
        return current_user
    return dependency


def require_permission(permission_keys: Union[str, Iterable[str]]):
    """
    Dependency that allows access only if current user has at least one of the given permissions.
    ADMIN role is treated as having all permissions.
    """
    needed = {permission_keys} if isinstance(permission_keys, str) else set(permission_keys)

    def dependency(
        current_user: User = Depends(get_current_user_from_cookie),
        db: Session = Depends(get_db)
    ):
        from app.models import Role, Permission, RolePermission

        role = current_user.role or db.query(Role).filter(Role.id == current_user.role_id).first()

        if role and role.name == "ADMIN":
            current_user.role = role
            return current_user

        if not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="������������ ����"
            )

        role_permissions = db.query(Permission.key).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).filter(RolePermission.role_id == role.id).all()

        granted = {row[0] for row in role_permissions}
        if not needed.intersection(granted):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="������������ ����"
            )
        current_user.role = role
        return current_user

    return dependency


def user_has_permission(user: User, db: Session, permission_key: str) -> bool:
    """Проверка наличия конкретного права у пользователя (ADMIN имеет все)."""
    if user is None:
        return False
    keys = get_user_permission_keys(user, db)
    return ("*" in keys) or (permission_key in keys)


def resolve_current_partner(db: Session, current_user: User):
    """
    Возвращает объект партнёра, связанный с текущим пользователем.
    Ищем по user.partner_id или по partners.user_id.
    """
    from app.models import Partner
    if current_user is None:
        return None
    partner_id = getattr(current_user, "partner_id", None)
    partner_obj = None
    if partner_id:
        partner_obj = db.query(Partner).filter(Partner.id == partner_id).first()
    if partner_obj is None:
        partner_obj = db.query(Partner).filter(Partner.user_id == current_user.id).first()
    return partner_obj


def get_current_user_from_cookie(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Получение текущего пользователя из cookie с валидацией JWT
    """
    token = request.cookies.get("access_token")
    client_ip = request.client.host if request.client else "unknown"
    
    if not token:
        from app.logging_config import auth_logger
        auth_logger.warning(f"Access denied: No token provided from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            from app.logging_config import auth_logger
            auth_logger.warning(f"Access denied: Invalid token (no user_id) from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = db.query(User).filter(User.id == int(user_id), User.deleted_at.is_(None)).first()
        if user is None:
            from app.logging_config import auth_logger
            auth_logger.warning(f"Access denied: User not found for ID {user_id} from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Проверяем, что у пользователя не pending 2FA состояние
        # Если в payload есть признак two_factor_pending, это означает, что пользователь
        # не завершил процесс аутентификации с 2FA
        two_factor_pending = payload.get("two_factor_pending")
        if two_factor_pending:
            from app.logging_config import auth_logger
            auth_logger.warning(f"Access denied: 2FA pending for user {user.username} from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Two-factor authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Проверяем, что у пользователя включена 2FA и он прошёл проверку
        # Если у пользователя включена 2FA, но в токене нет признака, что он прошёл 2FA,
        # значит он использует токен до прохождения 2FA, что недопустимо
        # Однако, если у пользователя 2FA не включена, он может войти без прохождения проверки
        if user.is_2fa_enabled and not payload.get("2fa_verified", False):
            from app.logging_config import auth_logger
            auth_logger.warning(f"Access denied: 2FA required but not verified for user {user.username} from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Two-factor authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        from app.logging_config import auth_logger
        auth_logger.info(f"Access granted for user {user.username} from IP {client_ip} to resource {request.url.path if request.url else 'unknown'}")
        return user
    except JWTError as e:
        from app.logging_config import auth_logger
        auth_logger.error(f"JWT validation error: {str(e)} from IP {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
