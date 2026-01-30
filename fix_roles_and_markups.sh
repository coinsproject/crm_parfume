#!/bin/bash
# Скрипт для исправления ролей и проверки надбавок на сервере

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Исправление ролей и проверка надбавок ===${NC}\n"

if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}Ошибка: docker-compose не найден!${NC}"
    exit 1
fi

if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    echo -e "${RED}Контейнер не запущен!${NC}"
    exit 1
fi

if [ -f "fix_roles_and_markups.py" ]; then
    echo -e "${BLUE}Копирование скрипта в контейнер...${NC}"
    if docker cp fix_roles_and_markups.py crm:/app/fix_roles_and_markups.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/fix_roles_and_markups.py" < fix_roles_and_markups.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}\n"
        
        $DOCKER_COMPOSE exec -T crm python fix_roles_and_markups.py
        
        $DOCKER_COMPOSE exec -T crm rm -f /app/fix_roles_and_markups.py 2>/dev/null || true
    else
        echo -e "${RED}✗ Не удалось скопировать скрипт${NC}"
        exit 1
    fi
else
    echo -e "${RED}Файл fix_roles_and_markups.py не найден!${NC}"
    exit 1
fi

