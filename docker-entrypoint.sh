#!/bin/bash
set -e

# Создаем директорию для БД если её нет
mkdir -p /app/data /app/logs

# Инициализируем БД если нужно (создает структуру таблиц через Base.metadata.create_all)
echo "Initializing database if needed..."
if [ ! -f /app/data/crm.db ] || [ ! -s /app/data/crm.db ]; then
    echo "Database not found or empty, creating structure..."
    python init_db.py
fi

# Применяем миграции Alembic (для обновления структуры БД)
echo "Applying database migrations..."
alembic upgrade head 2>&1 || {
    echo "Warning: Migrations may have failed, but continuing..."
    echo "You may need to apply migrations manually: alembic upgrade head"
}

echo "Starting application..."
exec "$@"

