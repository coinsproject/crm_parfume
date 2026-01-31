#!/bin/bash
# Скрипт для исправления версии Alembic в базе данных

echo "=== Исправление версии Alembic ==="

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "Ошибка: docker-compose не найден"
    exit 1
fi

echo "1. Проверка текущей версии в alembic_version..."
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import engine
from sqlalchemy import text
with engine.connect() as conn:
    try:
        result = conn.execute(text('SELECT version_num FROM alembic_version'))
        versions = [row[0] for row in result.fetchall()]
        print('Текущие версии в alembic_version:', versions)
    except Exception as e:
        print('Ошибка или таблица пуста:', e)
        print('Таблица alembic_version не существует или пуста')
"

echo ""
echo "2. Проверка структуры таблицы release_notes..."
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('PRAGMA table_info(release_notes)'))
    cols = [row[1] for row in result.fetchall()]
    print('Колонки в release_notes:', cols)
    has_is_published_to_partners = 'is_published_to_partners' in cols
    has_max_partner_views = 'max_partner_views' in cols
    print('is_published_to_partners:', has_is_published_to_partners)
    print('max_partner_views:', has_max_partner_views)
    
    if not has_is_published_to_partners:
        print('')
        print('Нужно применить миграцию 20260126015515')
        print('Но сначала нужно проштамповать текущее состояние БД')
"

echo ""
echo "3. Определение последней примененной миграции..."
echo "Проверяем наличие таблиц из разных миграций..."

$DOCKER_COMPOSE exec -T crm python -c "
from app.db import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)
tables = inspector.get_table_names()
print('Существующие таблицы:', sorted(tables))

# Проверяем наличие ключевых таблиц
key_tables = {
    'partners': '96a60174218e',
    'release_notes': '31a69389712b',
}

# Проверяем структуру release_notes
if 'release_notes' in tables:
    result = inspector.get_columns('release_notes')
    cols = [col['name'] for col in result]
    has_new_fields = 'is_published_to_partners' in cols and 'max_partner_views' in cols
    
    if has_new_fields:
        print('')
        print('Вероятная версия: 20260126015515 (последняя)')
        suggested_version = '20260126015515'
    else:
        print('')
        print('Вероятная версия: 31a69389712b (release_notes создана, но без новых полей)')
        suggested_version = '31a69389712b'
else:
    print('')
    print('Вероятная версия: 96a60174218e (базовые таблицы)')
    suggested_version = '96a60174218e'

print('')
print('Рекомендуется проштамповать на версию:', suggested_version)
"

echo ""
echo "4. Проштамповка БД на версию 31a69389712b (если release_notes без новых полей)..."
echo "   Или на 20260126015515 (если поля уже есть)"
echo ""
echo "Выполните вручную:"
echo "  sudo docker-compose exec crm alembic stamp 31a69389712b"
echo "  # или"
echo "  sudo docker-compose exec crm alembic stamp 20260126015515"
echo ""
echo "Затем примените недостающие миграции:"
echo "  sudo docker-compose exec crm alembic upgrade head"



