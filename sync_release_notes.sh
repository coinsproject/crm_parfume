#!/bin/bash
# Скрипт для синхронизации релиз-ноутсов на сервере
# Использование: ./sync_release_notes.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Синхронизация релиз-ноутсов на сервере ===${NC}\n"

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}✗ Ошибка: docker-compose не найден!${NC}"
    exit 1
fi

CONTAINER_NAME="crm"

# Проверяем, что контейнер запущен
if ! $DOCKER_COMPOSE ps | grep -q "$CONTAINER_NAME.*Up"; then
    echo -e "${RED}✗ Контейнер $CONTAINER_NAME не запущен!${NC}"
    exit 1
fi

# Копируем скрипт в контейнер
echo -e "${BLUE}Копирование скрипта в контейнер...${NC}"
if docker cp sync_release_notes.py $CONTAINER_NAME:/app/sync_release_notes.py 2>/dev/null || \
   $DOCKER_COMPOSE exec -T $CONTAINER_NAME sh -c "cat > /app/sync_release_notes.py" < sync_release_notes.py 2>/dev/null; then
    echo -e "${GREEN}✓ Скрипт скопирован${NC}"
else
    echo -e "${RED}✗ Не удалось скопировать скрипт${NC}"
    exit 1
fi

# Запускаем скрипт
echo -e "\n${BLUE}Запуск синхронизации релиз-ноутсов...${NC}\n"
if $DOCKER_COMPOSE exec -T $CONTAINER_NAME python sync_release_notes.py; then
    echo -e "\n${GREEN}✓ Синхронизация завершена успешно${NC}"
    
    # Удаляем скрипт из контейнера
    $DOCKER_COMPOSE exec -T $CONTAINER_NAME rm -f /app/sync_release_notes.py 2>/dev/null || true
else
    echo -e "\n${RED}✗ Ошибка при синхронизации${NC}"
    exit 1
fi

echo -e "\n${GREEN}=== Готово ===${NC}"

