"""
Сервис для ограничения частоты запросов и защиты от перебора
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.models import User, FragellaUsageLog
from app.config import settings


class RateLimitService:
    def __init__(self):
        # В продвинутом варианте можно использовать Redis, но для простоты используем встроенный кэш
        self.request_cache: Dict[str, list] = {}
        self.blocked_users: Dict[int, datetime] = {}

    def _get_cache_key(self, identifier: str, endpoint: str) -> str:
        """Создание ключа для кэша"""
        return f"{identifier}:{endpoint}"

    def is_rate_limited(self, identifier: str, endpoint: str, max_requests: int, window_seconds: int) -> bool:
        """
        Проверка, не превышен ли лимит запросов
        """
        cache_key = self._get_cache_key(identifier, endpoint)
        
        now = time.time()
        if cache_key not in self.request_cache:
            self.request_cache[cache_key] = []
        
        # Очищаем старые записи вне окна
        self.request_cache[cache_key] = [
            req_time for req_time in self.request_cache[cache_key]
            if now - req_time < window_seconds
        ]
        
        # Проверяем, не превышен ли лимит
        if len(self.request_cache[cache_key]) >= max_requests:
            return True
        
        # Добавляем текущий запрос в кэш
        self.request_cache[cache_key].append(now)
        return False

    def is_user_blocked_for_2fa(self, user_id: int) -> bool:
        """
        Проверка, заблокирован ли пользователь для 2FA
        """
        if user_id in self.blocked_users:
            block_until = self.blocked_users[user_id]
            if datetime.utcnow() < block_until:
                return True
            else:
                # Если время блокировки прошло, удаляем из списка заблокированных
                del self.blocked_users[user_id]
        return False

    def block_user_for_2fa(self, user_id: int, minutes: int = 5):
        """
        Блокировка пользователя для 2FA на указанное количество минут
        """
        self.blocked_users[user_id] = datetime.utcnow() + timedelta(minutes=minutes)

    def check_2fa_attempts(self, user: User, db: Session) -> bool:
        """
        Проверка количества неудачных попыток 2FA
        """
        # Проверяем, прошло ли достаточно времени с последней попытки
        if user.last_2fa_attempt_at:
            time_since_last = datetime.utcnow() - user.last_2fa_attempt_at
            if time_since_last.total_seconds() > 300:  # 5 минут
                # Сбрасываем счетчик если прошло более 5 минут
                user.failed_2fa_attempts = 0
                user.last_2fa_attempt_at = None
                db.commit()
        
        # Проверяем, не превышен ли лимит попыток
        if user.failed_2fa_attempts >= 5:  # 5 неудачных попыток
            # Блокируем пользователя на 5 минут
            time_since_last_attempt = (datetime.utcnow() - user.last_2fa_attempt_at).total_seconds() if user.last_2fa_attempt_at else float('inf')
            if time_since_last_attempt < 300:  # 5 минут (300 секунд)
                return False  # Пользователь все еще заблокирован
            else:
                # Если прошло 5 минут, сбрасываем счетчик
                user.failed_2fa_attempts = 0
                user.last_2fa_attempt_at = None
                db.commit()
        
        return True

    def increment_2fa_failure(self, user: User, db: Session):
        """
        Увеличение счетчика неудачных попыток 2FA
        """
        user.failed_2fa_attempts += 1
        user.last_2fa_attempt_at = datetime.utcnow()
        db.commit()
        
        # Если достигли лимита, блокируем пользователя
        if user.failed_2fa_attempts >= 5:
            self.block_user_for_2fa(user.id, 5)  # Блокируем на 5 минут

    def reset_2fa_attempts(self, user: User, db: Session):
        """
        Сброс счетчика неудачных попыток 2FA
        """
        user.failed_2fa_attempts = 0
        user.last_2fa_attempt_at = None
        db.commit()


# Глобальный экземпляр сервиса
rate_limit_service = RateLimitService()


def check_auth_rate_limit(ip_address: str, db: Session) -> bool:
    """
    Проверка лимита авторизации для IP
    """
    return not rate_limit_service.is_rate_limited(
        ip_address,
        "auth",
        settings.AUTH_MAX_REQUESTS_PER_MINUTE,
        settings.RATE_LIMIT_WINDOW_SECONDS
    )


def check_2fa_attempts_limit(user: User, db: Session) -> bool:
    """
    Проверка лимита попыток 2FA для пользователя
    """
    return rate_limit_service.check_2fa_attempts(user, db)


def increment_2fa_failure_count(user: User, db: Session):
    """
    Увеличение счетчика неудачных попыток 2FA
    """
    rate_limit_service.increment_2fa_failure(user, db)


def reset_2fa_attempts(user: User, db: Session):
    """
    Сброс счетчика неудачных попыток 2FA
    """
    rate_limit_service.reset_2fa_attempts(user, db)