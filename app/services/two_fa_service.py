"""
Сервис для работы с двухфакторной аутентификацией (2FA)
"""
from datetime import datetime, timedelta
from typing import List, Optional
import bcrypt
import pyotp
import secrets
import qrcode
from io import BytesIO
import base64
from sqlalchemy.orm import Session
from app.models import User, BackupCode
from app.config import settings
from app.logging_config import two_fa_logger
from datetime import datetime, timedelta
from typing import List, Optional
import bcrypt
import pyotp
import secrets
import qrcode
from io import BytesIO
import base64
from sqlalchemy.orm import Session
from app.models import User, BackupCode
from app.config import settings


def generate_totp_secret() -> str:
    """
    Генерация TOTP-секрета для пользователя
    """
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str, issuer_name: str = "ParfumeCRM") -> str:
    """
    Формирование otpauth URI для QR-кода
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=issuer_name
    )


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Проверка TOTP-кода
    """
    try:
        totp = pyotp.TOTP(secret)
        # valid_window=1 позволяет +/- один 30-секундный шаг для уменьшения проблем с рассинхронизацией
        is_valid = totp.verify(code, valid_window=1)
        if is_valid:
            two_fa_logger.info("TOTP code verification successful")
        else:
            two_fa_logger.warning(f"TOTP code verification failed for code: {code[:3]}...")
        return is_valid
    except Exception as e:
        two_fa_logger.error(f"Error during TOTP verification: {str(e)}")
        return False


def generate_backup_codes(count: int = 10) -> list[str]:
    """
    Генерация резервных кодов
    """
    codes = []
    for _ in range(count):
        # Генерируем 8-символьный код из букв и цифр
        code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567') for _ in range(8))
        codes.append(code)
    return codes


def hash_backup_code(plain_code: str) -> str:
    """
    Хеширование резервного кода с использованием bcrypt
    """
    pwd_bytes = plain_code.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_backup_code(plain_code: str, hashed_code: str) -> bool:
    """
    Проверка соответствия резервного кода хешу
    """
    pwd_bytes = plain_code.encode('utf-8')
    hash_bytes = hashed_code.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def verify_backup_code_for_user(user_id: int, plain_code: str, db: Session) -> bool:
    """
    Проверка резервного кода для пользователя
    """
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
            two_fa_logger.info(f"Backup code verification successful for user ID: {user_id}")
            return True
    
    two_fa_logger.warning(f"Backup code verification failed for user ID: {user_id}, invalid code: {plain_code[:3]}...")
    return False


def generate_qr_code(data: str) -> str:
    """
    Генерация QR-кода в формате base64 для встраивания в HTML
    """
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_image = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{qr_image}"


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
    attempts_exceeded = user.failed_2fa_attempts >= 5  # Максимум 5 попыток в течение 5 минут
    if attempts_exceeded:
        two_fa_logger.warning(f"2FA attempts limit exceeded for user: {user.username}")
    return not attempts_exceeded


def increment_2fa_failed_attempts(user: User, db: Session):
    """
    Увеличение счетчика неудачных попыток 2FA
    """
    from datetime import datetime
    user.failed_2fa_attempts += 1
    user.last_2fa_attempt_at = datetime.utcnow()
    db.commit()
    two_fa_logger.warning(f"Incremented 2FA failed attempts for user: {user.username}, current count: {user.failed_2fa_attempts}")


def reset_2fa_attempts(user: User, db: Session):
    """
    Сброс счетчика неудачных попыток 2FA (при успешной аутентификации)
    """
    user.failed_2fa_attempts = 0
    user.last_2fa_attempt_at = None
    db.commit()
    two_fa_logger.info(f"Reset 2FA attempts counter for user: {user.username}")


def enable_2fa_for_user(user: User, secret: str, db: Session) -> List[str]:
    """
    Включение 2FA для пользователя и генерация резервных кодов
    """
    # Устанавливаем секрет и включаем 2FA
    user.totp_secret = secret
    user.is_2fa_enabled = True
    user.totp_secret_temp = None  # Очищаем временный секрет
    
    db.commit()
    
    # Генерируем и сохраняем резервные коды
    backup_codes = generate_backup_codes(count=10)
    
    for plain_code in backup_codes:
        code_hash = hash_backup_code(plain_code)
        backup_code = BackupCode(
            user_id=user.id,
            code_hash=code_hash,
            is_used=False
        )
        db.add(backup_code)
    
    db.commit()
    
    two_fa_logger.info(f"2FA enabled for user: {user.username}")
    return backup_codes


def disable_2fa_for_user(user: User, db: Session):
    """
    Отключение 2FA для пользователя
    """
    user.is_2fa_enabled = False
    user.totp_secret = None
    user.totp_secret_temp = None
    
    # Удаляем все резервные коды пользователя
    db.query(BackupCode).filter(BackupCode.user_id == user.id).delete()
    
    db.commit()
    two_fa_logger.info(f"2FA disabled for user: {user.username}")