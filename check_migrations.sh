#!/bin/bash
# Скрипт для проверки и принудительного применения миграций на сервере

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Проверка миграций на сервере ===${NC}"

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}Ошибка: docker-compose не найден!${NC}"
    exit 1
fi

# Проверяем, запущен ли контейнер
if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    echo -e "${RED}Контейнер не запущен! Запустите его сначала: $DOCKER_COMPOSE up -d${NC}"
    exit 1
fi

echo -e "${BLUE}1. Проверка текущей версии миграций...${NC}"
CURRENT_REVISION=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1 | grep -oP '\(revision: \K[^)]+' || echo "не определена")
echo -e "${YELLOW}Текущая ревизия: ${CURRENT_REVISION}${NC}"

echo -e "${BLUE}2. Проверка доступных миграций...${NC}"
$DOCKER_COMPOSE exec -T crm alembic history | head -20

echo -e "${BLUE}3. Попытка применения всех миграций до head...${NC}"
if $DOCKER_COMPOSE exec -T crm alembic upgrade head; then
    echo -e "${GREEN}✓ Миграции применены успешно${NC}"
else
    echo -e "${RED}✗ Ошибка при применении миграций${NC}"
    echo -e "${YELLOW}Проверьте логи выше для деталей${NC}"
    exit 1
fi

echo -e "${BLUE}4. Проверка финальной версии...${NC}"
FINAL_REVISION=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1 | grep -oP '\(revision: \K[^)]+' || echo "не определена")
echo -e "${GREEN}Финальная ревизия: ${FINAL_REVISION}${NC}"

if [ "$CURRENT_REVISION" != "$FINAL_REVISION" ]; then
    echo -e "${GREEN}✓ Миграции обновлены с ${CURRENT_REVISION} до ${FINAL_REVISION}${NC}"
else
    echo -e "${YELLOW}Миграции уже на последней версии${NC}"
fi

echo -e "${BLUE}5. Проверка ролей в базе данных...${NC}"
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission
db = SessionLocal()
try:
    roles = db.query(Role).all()
    print(f'Найдено ролей: {len(roles)}')
    for role in roles:
        print(f'  - {role.name}: {role.description}')
    permissions = db.query(Permission).all()
    print(f'Найдено прав: {len(permissions)}')
    role_perms = db.query(RolePermission).all()
    print(f'Найдено связей роли-права: {len(role_perms)}')
finally:
    db.close()
" || echo -e "${YELLOW}Не удалось проверить роли (возможно, требуется перезапуск контейнера)${NC}"

echo -e "${GREEN}=== Проверка завершена ===${NC}"

