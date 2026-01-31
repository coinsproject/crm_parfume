#!/bin/bash
# Скрипт для принудительного применения миграции release_notes

echo "=== Применение миграции для release_notes ==="

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "Ошибка: docker-compose не найден"
    exit 1
fi

echo "1. Проверка текущей версии миграций..."
$DOCKER_COMPOSE exec -T crm alembic current

echo ""
echo "2. Проверка истории миграций..."
$DOCKER_COMPOSE exec -T crm alembic history | grep -E "20260126015515|31a69389712b" | head -5

echo ""
echo "3. Применение миграций..."
$DOCKER_COMPOSE exec -T crm alembic upgrade head

echo ""
echo "4. Проверка структуры таблицы release_notes..."
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import engine
from sqlalchemy import inspect
inspector = inspect(engine)
cols = [col['name'] for col in inspector.get_columns('release_notes')]
print('Колонки в release_notes:', cols)
print('is_published_to_partners:', 'is_published_to_partners' in cols)
print('max_partner_views:', 'max_partner_views' in cols)
"

echo ""
echo "=== Готово ==="



