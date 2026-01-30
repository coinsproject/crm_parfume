#!/bin/bash
# Скрипт для исправления прав в базе данных
# Использование: ./fix_permissions.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Исправление прав в базе данных ===${NC}"

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

# Проверяем наличие файла скрипта
if [ ! -f "fix_permissions.py" ]; then
    echo -e "${RED}Ошибка: файл fix_permissions.py не найден!${NC}"
    echo -e "${YELLOW}Убедитесь, что вы находитесь в корневой директории проекта${NC}"
    exit 1
fi

# Копируем скрипт в контейнер (если нужно) или запускаем напрямую
echo -e "${BLUE}Запуск скрипта исправления прав...${NC}\n"

if $DOCKER_COMPOSE exec -T crm python fix_permissions.py; then
    echo -e "\n${GREEN}✓ Скрипт выполнен успешно${NC}"
else
    echo -e "\n${RED}✗ Ошибка при выполнении скрипта${NC}"
    exit 1
fi

echo -e "\n${GREEN}=== Готово ===${NC}"

