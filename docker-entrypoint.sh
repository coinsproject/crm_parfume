#!/bin/bash
set -e

# Создаем директорию для БД если её нет
mkdir -p /app/data /app/logs

# Применяем миграции Alembic (игнорируем ошибки если БД еще не создана)
echo "Applying database migrations..."
alembic upgrade head || echo "Migrations may have failed, will try to initialize DB..."

# Инициализируем БД если нужно (только если БД пустая)
echo "Initializing database if needed..."
if [ ! -f /app/data/crm.db ] || [ ! -s /app/data/crm.db ]; then
    echo "Database not found or empty, initializing..."
    python init_db.py
    # После инициализации применяем миграции еще раз
    echo "Re-applying migrations after initialization..."
    alembic upgrade head || true
else
    echo "Database already exists, skipping initialization."
fi

echo "Starting application..."
exec "$@"

