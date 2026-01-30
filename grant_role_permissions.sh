#!/bin/bash
# Скрипт для добавления прав ролям на сервере

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Добавление прав для ролей ===${NC}\n"

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

if [ -f "grant_role_permissions.py" ]; then
    echo -e "${BLUE}Копирование скрипта в контейнер...${NC}"
    if docker cp grant_role_permissions.py crm:/app/grant_role_permissions.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/grant_role_permissions.py" < grant_role_permissions.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}\n"
        
        $DOCKER_COMPOSE exec -T crm python grant_role_permissions.py
        
        $DOCKER_COMPOSE exec -T crm rm -f /app/grant_role_permissions.py 2>/dev/null || true
    else
        echo -e "${RED}✗ Не удалось скопировать скрипт${NC}"
        exit 1
    fi
else
    echo -e "${RED}Файл grant_role_permissions.py не найден!${NC}"
    exit 1
fi

