import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models import Invitation, User, Role
from app.services.auth_service import hash_password


def generate_invitation_token(length: int = 32) -> str:
    """Генерация случайного токена для приглашения"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def create_invitation(
    email: str,
    role: Role,
    db: Session,
    partner_id: Optional[int] = None,
    created_by_user: User = None,
    expires_in_days: int = 7,
    partner_full_name: Optional[str] = None,
    partner_phone: Optional[str] = None,
    partner_telegram: Optional[str] = None,
) -> Invitation:
    """Создание приглашения"""
    token = generate_invitation_token()
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    
    invitation = Invitation(
        email=email,
        role_id=role.id,
        partner_id=partner_id,
        token=token,
        expires_at=expires_at,
        is_used=False,
        created_by_user_id=created_by_user.id if created_by_user else None,
        partner_full_name=partner_full_name,
        partner_phone=partner_phone,
        partner_telegram=partner_telegram,
    )
    
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    
    return invitation


def get_valid_invitation_by_token(token: str, db: Session) -> Optional[Invitation]:
    """Получение валидного приглашения по токену"""
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    
    if not invitation:
        return None
    
    # Проверяем, не использовано ли приглашение и не истёк ли срок
    if invitation.is_used or invitation.expires_at < datetime.utcnow():
        return None
    
    return invitation


def mark_invitation_used(invitation: Invitation, db: Session) -> None:
    """Пометить приглашение как использованное"""
    invitation.is_used = True
    db.commit()


def create_user_from_invitation(
    invitation: Invitation,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str],
    db: Session
) -> User:
    """Создание пользователя из приглашения"""
    from app.models import User
    
    hashed_password = hash_password(password)
    
    user = User(
        username=username,
        email=email,
        password_hash=hashed_password,
        full_name=full_name,
        role_id=invitation.role_id,
        partner_id=invitation.partner_id,
        is_active=False,  # Пользователь не активен до тех пор, пока админ не активирует
        pending_activation=True,  # Помечаем, что пользователь ожидает активации
        is_2fa_enabled=False  # 2FA выключена по умолчанию для новых пользователей, админ может включить
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user
