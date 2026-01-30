#!/bin/bash
# Скрипт для сверки версий на сервере

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=== Сверка версий: локальная vs серверная ===${NC}\n"

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
    echo -e "${RED}Контейнер не запущен!${NC}"
    exit 1
fi

# Копируем скрипт в контейнер
if [ -f "compare_versions.py" ]; then
    echo -e "${BLUE}Копирование скрипта в контейнер...${NC}"
    if docker cp compare_versions.py crm:/app/compare_versions.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/compare_versions.py" < compare_versions.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}\n"
        
        echo -e "${BLUE}Запуск сверки...${NC}\n"
        $DOCKER_COMPOSE exec -T crm python compare_versions.py
        
        # Удаляем временный файл
        $DOCKER_COMPOSE exec -T crm rm -f /app/compare_versions.py 2>/dev/null || true
    else
        echo -e "${RED}✗ Не удалось скопировать скрипт${NC}"
        exit 1
    fi
else
    echo -e "${RED}Файл compare_versions.py не найден!${NC}"
    exit 1
fi

