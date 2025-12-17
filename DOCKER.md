# Инструкции по работе с Docker

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd CRM
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и настройте необходимые параметры:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл, особенно `SECRET_KEY` для продакшена.

### 3. Запуск приложения

```bash
docker-compose up -d
```

Приложение будет доступно по адресу: http://localhost:8000

### 4. Первый вход

После первого запуска создается администратор:
- **Логин:** `admin`
- **Пароль:** `admin123`

**Важно:** Смените пароль после первого входа!

## Управление контейнером

### Просмотр логов

```bash
# Все логи
docker-compose logs

# Логи в реальном времени
docker-compose logs -f

# Логи только приложения
docker-compose logs -f crm
```

### Остановка

```bash
docker-compose stop
```

### Запуск после остановки

```bash
docker-compose start
```

### Перезапуск

```bash
docker-compose restart
```

### Полная остановка с удалением контейнера

```bash
docker-compose down
```

### Остановка с удалением volumes (удалит данные БД!)

```bash
docker-compose down -v
```

## Работа с базой данных

### Применение миграций

Миграции применяются автоматически при запуске контейнера через `docker-entrypoint.sh`.

Для ручного применения:

```bash
docker-compose exec crm alembic upgrade head
```

### Создание новой миграции

```bash
docker-compose exec crm alembic revision --autogenerate -m "описание изменений"
```

### Доступ к базе данных

```bash
# SQLite
docker-compose exec crm sqlite3 /app/data/crm.db

# Или через Python
docker-compose exec crm python
>>> from app.db import SessionLocal
>>> db = SessionLocal()
```

## Пересборка образа

Если вы изменили код или зависимости:

```bash
# Пересборка без кэша
docker-compose build --no-cache

# Пересборка и перезапуск
docker-compose up -d --build
```

## Обновление зависимостей

1. Обновите `requirements.txt`
2. Пересоберите образ:
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

## Резервное копирование

### Резервная копия базы данных

```bash
# SQLite
docker-compose exec crm sqlite3 /app/data/crm.db ".backup /app/data/crm_backup.db"

# Копирование из контейнера
docker cp parfume-crm:/app/data/crm.db ./backups/crm_$(date +%Y%m%d_%H%M%S).db
```

### Восстановление из резервной копии

```bash
docker cp ./backups/crm_backup.db parfume-crm:/app/data/crm.db
docker-compose restart
```

## Переменные окружения

Все переменные окружения можно настроить в `docker-compose.yml` или через файл `.env`.

Основные переменные:
- `DATABASE_URL` - URL базы данных
- `SECRET_KEY` - Секретный ключ для JWT (обязательно измените!)
- `FRAGELLA_API_KEY` - API ключ для Fragella (опционально)

## Troubleshooting

### Контейнер не запускается

1. Проверьте логи:
   ```bash
   docker-compose logs
   ```

2. Проверьте, что порт 8000 свободен:
   ```bash
   # Linux/Mac
   lsof -i :8000
   
   # Windows
   netstat -ano | findstr :8000
   ```

### Проблемы с правами доступа

На Linux/Mac может потребоваться настроить права на директории:

```bash
sudo chown -R $USER:$USER ./data ./logs
chmod -R 755 ./data ./logs
```

### Очистка Docker

```bash
# Удаление неиспользуемых образов
docker image prune -a

# Удаление неиспользуемых volumes
docker volume prune

# Полная очистка (осторожно!)
docker system prune -a --volumes
```

## Production deployment

Для продакшена рекомендуется:

1. Использовать PostgreSQL вместо SQLite
2. Настроить reverse proxy (nginx)
3. Использовать SSL/TLS сертификаты
4. Настроить регулярное резервное копирование
5. Использовать Docker secrets для чувствительных данных
6. Настроить мониторинг и логирование

Пример с PostgreSQL:

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: crmdb
      POSTGRES_USER: crmuser
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  crm:
    # ... остальная конфигурация
    environment:
      DATABASE_URL: postgresql://crmuser:${DB_PASSWORD}@db:5432/crmdb
    depends_on:
      - db

volumes:
  postgres_data:
```

