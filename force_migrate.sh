#!/bin/bash
# Скрипт для принудительного применения всех миграций

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Принудительное применение миграций ===${NC}"

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
    echo -e "${YELLOW}Контейнер не запущен. Запускаем...${NC}"
    $DOCKER_COMPOSE up -d
    sleep 5
fi

echo -e "${BLUE}1. Создание резервной копии базы данных...${NC}"
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/crm_backup_before_migrate_$(date +%Y%m%d_%H%M%S).db"

if docker cp crm:/app/data/crm.db "$BACKUP_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠ Не удалось создать резервную копию, продолжаем...${NC}"
fi

echo -e "${BLUE}2. Проверка текущего состояния миграций...${NC}"
$DOCKER_COMPOSE exec -T crm alembic current

echo -e "${BLUE}3. Применение всех миграций до head...${NC}"
echo -e "${YELLOW}Это может занять некоторое время...${NC}"

if $DOCKER_COMPOSE exec -T crm alembic upgrade head; then
    echo -e "${GREEN}✓ Миграции применены успешно${NC}"
else
    echo -e "${RED}✗ Ошибка при применении миграций${NC}"
    echo -e "${YELLOW}Проверьте логи выше. Если нужно, восстановите из резервной копии:${NC}"
    echo -e "${YELLOW}  docker cp $BACKUP_FILE crm:/app/data/crm.db${NC}"
    exit 1
fi

echo -e "${BLUE}4. Проверка финального состояния...${NC}"
$DOCKER_COMPOSE exec -T crm alembic current

echo -e "${BLUE}5. Перезапуск контейнера для применения изменений...${NC}"
$DOCKER_COMPOSE restart crm

echo -e "${GREEN}=== Миграции применены ===${NC}"
echo -e "${BLUE}Резервная копия: $BACKUP_FILE${NC}"

