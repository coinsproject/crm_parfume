#!/bin/bash
# Скрипт для установки надбавки партнеру на сервере
# Использование: ./set_partner_markup.sh <partner_id> <markup_percent>

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ $# -ne 2 ]; then
    echo -e "${YELLOW}Использование: $0 <partner_id> <markup_percent>${NC}"
    echo -e "${YELLOW}Пример: $0 1 3.0${NC}"
    exit 1
fi

PARTNER_ID=$1
MARKUP=$2

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

if [ -f "set_partner_markup.py" ]; then
    echo -e "${BLUE}Копирование скрипта в контейнер...${NC}"
    if docker cp set_partner_markup.py crm:/app/set_partner_markup.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/set_partner_markup.py" < set_partner_markup.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}\n"
        
        echo -e "${BLUE}Установка надбавки ${MARKUP}% для партнера ID ${PARTNER_ID}...${NC}\n"
        $DOCKER_COMPOSE exec -T crm python set_partner_markup.py $PARTNER_ID $MARKUP
        
        $DOCKER_COMPOSE exec -T crm rm -f /app/set_partner_markup.py 2>/dev/null || true
    else
        echo -e "${RED}✗ Не удалось скопировать скрипт${NC}"
        exit 1
    fi
else
    echo -e "${RED}Файл set_partner_markup.py не найден!${NC}"
    exit 1
fi

