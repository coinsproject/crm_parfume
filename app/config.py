from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import AnyHttpUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Рабочая БД по умолчанию: локальный файл проекта. Можно переопределить через переменную окружения DATABASE_URL
    DATABASE_URL: str = "sqlite:///./data/crm.db"
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Настройки Fragella API
    FRAGELLA_API_BASE_URL: AnyHttpUrl = "https://api.fragella.com/api/v1"
    FRAGELLA_API_KEY: str = ""  # по умолчанию пустой, будет задаваться через .env
    FRAGELLA_ENABLED: bool = True
    FRAGELLA_MAX_REQUESTS_PER_DAY: int = 500
    FRAGELLA_MIN_INTERVAL_SECONDS: int = 2
    FRAGELLA_TIMEOUT_SECONDS: int = 10
    
    # Настройки 2FA
    MAX_2FA_ATTEMPTS: int = 5  # максимальное количество попыток ввода 2FA кода
    BACKUP_CODES_COUNT: int = 10  # количество резервных кодов
    TEMP_TOKEN_EXPIRE_MINUTES: int = 10  # время жизни временного токена для 2FA (в минутах)
    
    # Настройки ограничения запросов
    AUTH_MAX_REQUESTS_PER_MINUTE: int = 5  # Максимум попыток авторизации в минуту с одного IP
    TWO_FA_MAX_ATTEMPTS: int = 5  # Максимум попыток ввода 2FA кода
    TWO_FA_BLOCK_MINUTES: int = 5  # Время блокировки при превышении лимита 2FA (в минутах)
    RATE_LIMIT_WINDOW_SECONDS: int = 60  # Окно ограничения в секундах
    RATE_LIMIT_MAX_REQUESTS: int = 100  # Максимальное количество запросов в окне


settings = Settings()

DATABASE_URL = settings.DATABASE_URL
