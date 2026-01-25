#!/bin/bash
set -e

# Скрипт для автоматического обновления CRM приложения
# Использование: ./update.sh

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Начало обновления Parfume CRM ===${NC}"

# Получаем директорию скрипта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Определяем команду docker compose (поддержка старой и новой версии)
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}Ошибка: docker-compose или docker compose не найден!${NC}"
    echo -e "${YELLOW}Установите Docker Compose:${NC}"
    echo -e "  Для старой версии: sudo apt-get install docker-compose"
    echo -e "  Для новой версии: Docker Compose V2 входит в состав Docker"
    exit 1
fi

echo -e "${BLUE}Используется команда: $DOCKER_COMPOSE${NC}"

# 1. Резервное копирование
echo -e "${YELLOW}[1/5] Создание резервной копии базы данных...${NC}"
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/crm_backup_$(date +%Y%m%d_%H%M%S).db"

if $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    # Контейнер запущен - создаем бэкап через контейнер
    if $DOCKER_COMPOSE exec -T crm test -f /app/data/crm.db 2>/dev/null; then
        $DOCKER_COMPOSE exec -T crm sqlite3 /app/data/crm.db ".backup /app/data/backup_temp.db" 2>/dev/null || \
        docker cp crm:/app/data/crm.db "$BACKUP_FILE" 2>/dev/null || {
            echo -e "${RED}Ошибка при создании резервной копии через контейнер${NC}"
            exit 1
        }
        if [ -f "$BACKUP_FILE" ]; then
            echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE${NC}"
        else
            # Копируем из контейнера
            docker cp crm:/app/data/backup_temp.db "$BACKUP_FILE" 2>/dev/null || {
                echo -e "${RED}Не удалось создать резервную копию${NC}"
                exit 1
            }
            echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE${NC}"
        fi
    else
        echo -e "${YELLOW}База данных не найдена в контейнере, пропускаем бэкап${NC}"
    fi
elif [ -f "./data/crm.db" ]; then
    # Контейнер не запущен, но БД есть локально
    cp ./data/crm.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}База данных не найдена, пропускаем бэкап${NC}"
fi

# Проверка размера бэкапа
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${BLUE}Размер резервной копии: $BACKUP_SIZE${NC}"
fi

# 2. Обновление кода
echo -e "${YELLOW}[2/5] Обновление кода из Git...${NC}"
git fetch origin main || {
    echo -e "${RED}Ошибка при получении обновлений из Git${NC}"
    exit 1
}

LOCAL=$(git rev-parse @ 2>/dev/null || echo "")
REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")

if [ -z "$LOCAL" ] || [ -z "$REMOTE" ]; then
    echo -e "${YELLOW}Не удалось определить версии, продолжаем обновление...${NC}"
    git pull origin main || {
        echo -e "${RED}Ошибка при обновлении кода${NC}"
        exit 1
    }
elif [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}✓ Уже на последней версии (commit: ${LOCAL:0:7})${NC}"
    echo -e "${BLUE}Проверяем наличие изменений в рабочей директории...${NC}"
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}Обнаружены локальные изменения. Продолжить? (y/n)${NC}"
        read -r response
        if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
            echo -e "${YELLOW}Обновление отменено${NC}"
            exit 0
        fi
    else
        echo -e "${GREEN}Нет изменений для применения${NC}"
        exit 0
    fi
else
    echo -e "${BLUE}Локальная версия: ${LOCAL:0:7}${NC}"
    echo -e "${BLUE}Удаленная версия: ${REMOTE:0:7}${NC}"
    git pull origin main || {
        echo -e "${RED}Ошибка при обновлении кода${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Код обновлен${NC}"
fi

# 3. Проверка изменений в зависимостях
echo -e "${YELLOW}[3/5] Проверка изменений...${NC}"
NEEDS_REBUILD=false

if git diff HEAD@{1} HEAD --name-only 2>/dev/null | grep -qE "(Dockerfile|requirements\.txt|docker-compose\.yml)"; then
    echo -e "${YELLOW}Обнаружены изменения в Dockerfile или зависимостях${NC}"
    NEEDS_REBUILD=true
fi

# 4. Пересборка (если нужно)
if [ "$NEEDS_REBUILD" = true ]; then
    echo -e "${YELLOW}[4/5] Пересборка Docker образа...${NC}"
    $DOCKER_COMPOSE build || {
        echo -e "${RED}Ошибка при пересборке образа${NC}"
        echo -e "${YELLOW}Попытка пересборки без кэша...${NC}"
        $DOCKER_COMPOSE build --no-cache || {
            echo -e "${RED}Критическая ошибка при пересборке!${NC}"
            echo -e "${YELLOW}Откат к предыдущей версии...${NC}"
            git checkout HEAD@{1}
            exit 1
        }
    }
    echo -e "${GREEN}✓ Образ пересобран${NC}"
else
    echo -e "${BLUE}[4/5] Пересборка не требуется${NC}"
fi

# 5. Применение миграций и перезапуск
echo -e "${YELLOW}[5/5] Применение миграций и перезапуск...${NC}"

# Запускаем контейнеры
$DOCKER_COMPOSE up -d || {
    echo -e "${RED}Ошибка при запуске контейнеров${NC}"
    exit 1
}

# Ждем запуска
echo -e "${BLUE}Ожидание запуска контейнера...${NC}"
sleep 5

# Проверяем, что контейнер запущен
if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    echo -e "${RED}Контейнер не запустился!${NC}"
    echo -e "${YELLOW}Проверьте логи: $DOCKER_COMPOSE logs crm${NC}"
    exit 1
fi

# Применяем миграции
echo -e "${BLUE}Применение миграций базы данных...${NC}"
if $DOCKER_COMPOSE exec -T crm alembic upgrade head 2>&1 | tee /tmp/migration_output.log; then
    echo -e "${GREEN}✓ Миграции применены успешно${NC}"
else
    MIGRATION_ERROR=$?
    echo -e "${RED}Ошибка при применении миграций!${NC}"
    echo -e "${YELLOW}Лог миграций сохранен в /tmp/migration_output.log${NC}"
    
    # Показываем последние строки лога
    echo -e "${YELLOW}Последние строки лога:${NC}"
    tail -20 /tmp/migration_output.log
    
    echo -e "${YELLOW}Откат к предыдущей версии? (y/n)${NC}"
    read -r response
    if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
        echo -e "${YELLOW}Откат к предыдущей версии...${NC}"
        git checkout HEAD@{1}
        $DOCKER_COMPOSE restart
        exit 1
    else
        echo -e "${YELLOW}Продолжаем без отката. Проверьте миграции вручную.${NC}"
    fi
fi

# 6. Проверка работоспособности
echo -e "${YELLOW}Проверка работоспособности...${NC}"
sleep 3

MAX_RETRIES=5
RETRY_COUNT=0
HEALTH_CHECK_PASSED=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${YELLOW}Попытка $RETRY_COUNT/$MAX_RETRIES...${NC}"
    sleep 2
done

if [ "$HEALTH_CHECK_PASSED" = true ]; then
    echo -e "${GREEN}✓ Приложение работает корректно!${NC}"
    
    # Показываем информацию о версии
    CURRENT_COMMIT=$(git rev-parse --short HEAD)
    echo -e "${BLUE}Текущая версия: ${CURRENT_COMMIT}${NC}"
    echo -e "${BLUE}Резервная копия: $BACKUP_FILE${NC}"
    
    echo -e "${GREEN}=== Обновление завершено успешно ===${NC}"
else
    echo -e "${RED}Приложение не отвечает на health check!${NC}"
    echo -e "${YELLOW}Проверьте логи: $DOCKER_COMPOSE logs --tail=50 crm${NC}"
    echo -e "${YELLOW}Резервная копия сохранена: $BACKUP_FILE${NC}"
    exit 1
fi










