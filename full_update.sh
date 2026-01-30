#!/bin/bash
# Полноценный скрипт обновления с проверками, миграциями и анализом
# Использование: ./full_update.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Полное обновление Parfume CRM с проверками            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}\n"

# Получаем директорию скрипта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}✗ Ошибка: docker-compose не найден!${NC}"
    exit 1
fi

echo -e "${BLUE}Используется команда: $DOCKER_COMPOSE${NC}\n"

# Функция для вывода секции
print_section() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Функция для проверки статуса
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
        return 0
    else
        echo -e "${RED}✗ $1${NC}"
        return 1
    fi
}

# ============================================================================
# ШАГ 1: Резервное копирование
# ============================================================================
print_section "ШАГ 1: Резервное копирование базы данных"

BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/crm_backup_full_update_$(date +%Y%m%d_%H%M%S).db"

if $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    if docker cp crm:/app/data/crm.db "$BACKUP_FILE" 2>/dev/null; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
    else
        echo -e "${YELLOW}⚠ Не удалось создать резервную копию, продолжаем...${NC}"
    fi
elif [ -f "./data/crm.db" ]; then
    if cp ./data/crm.db "$BACKUP_FILE" 2>/dev/null; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
    else
        echo -e "${YELLOW}⚠ Не удалось создать резервную копию${NC}"
    fi
else
    echo -e "${YELLOW}⚠ База данных не найдена, пропускаем бэкап${NC}"
fi

# ============================================================================
# ШАГ 2: Обновление кода из Git
# ============================================================================
print_section "ШАГ 2: Обновление кода из Git"

git fetch origin main || {
    echo -e "${RED}✗ Ошибка при получении обновлений из Git${NC}"
    exit 1
}

LOCAL=$(git rev-parse @ 2>/dev/null || echo "")
REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")

if [ -z "$LOCAL" ] || [ -z "$REMOTE" ]; then
    echo -e "${YELLOW}Не удалось определить версии, продолжаем обновление...${NC}"
    git pull origin main || {
        echo -e "${RED}✗ Ошибка при обновлении кода${NC}"
        exit 1
    }
    CODE_UPDATED=true
elif [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}✓ Уже на последней версии (commit: ${LOCAL:0:7})${NC}"
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}Обнаружены локальные изменения. Продолжить? (y/n)${NC}"
        read -r response
        if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
            echo -e "${YELLOW}Обновление отменено${NC}"
            exit 0
        fi
    else
        echo -e "${BLUE}Нет изменений для применения${NC}"
        CODE_UPDATED=false
    fi
else
    echo -e "${BLUE}Локальная версия: ${LOCAL:0:7}${NC}"
    echo -e "${BLUE}Удаленная версия: ${REMOTE:0:7}${NC}"
    git pull origin main || {
        echo -e "${RED}✗ Ошибка при обновлении кода${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Код обновлен${NC}"
    CODE_UPDATED=true
fi

# ============================================================================
# ШАГ 3: Проверка необходимости пересборки
# ============================================================================
print_section "ШАГ 3: Анализ изменений и необходимость пересборки"

NEEDS_REBUILD=false

if [ "$CODE_UPDATED" = true ]; then
    if git diff HEAD@{1} HEAD --name-only 2>/dev/null | grep -qE "(Dockerfile|requirements\.txt|docker-compose\.yml|\.py$|\.html$|\.js$|\.css$)"; then
        echo -e "${YELLOW}Обнаружены изменения в коде или зависимостях${NC}"
        NEEDS_REBUILD=true
    fi
fi

if [ "$NEEDS_REBUILD" = true ]; then
    echo -e "${BLUE}Требуется пересборка Docker образа${NC}"
else
    echo -e "${GREEN}Пересборка не требуется${NC}"
fi

# ============================================================================
# ШАГ 4: Пересборка образа (если нужно)
# ============================================================================
if [ "$NEEDS_REBUILD" = true ]; then
    print_section "ШАГ 4: Пересборка Docker образа"
    
    echo -e "${BLUE}Начало пересборки...${NC}"
    if $DOCKER_COMPOSE build; then
        echo -e "${GREEN}✓ Образ пересобран${NC}"
    else
        echo -e "${YELLOW}Попытка пересборки без кэша...${NC}"
        $DOCKER_COMPOSE build --no-cache || {
            echo -e "${RED}✗ Критическая ошибка при пересборке!${NC}"
            exit 1
        }
        echo -e "${GREEN}✓ Образ пересобран${NC}"
    fi
else
    echo -e "\n${BLUE}ШАГ 4: Пересборка не требуется${NC}"
fi

# ============================================================================
# ШАГ 5: Перезапуск контейнера
# ============================================================================
print_section "ШАГ 5: Перезапуск контейнера"

echo -e "${BLUE}Остановка старых контейнеров...${NC}"
$DOCKER_COMPOSE down 2>/dev/null || true

if docker ps -a --format '{{.Names}}' | grep -q "^parfume-crm$"; then
    echo -e "${BLUE}Удаление старого контейнера parfume-crm...${NC}"
    docker stop parfume-crm 2>/dev/null || true
    docker rm -f parfume-crm 2>/dev/null || true
fi

echo -e "${BLUE}Запуск контейнеров...${NC}"
$DOCKER_COMPOSE up -d || {
    echo -e "${RED}✗ Ошибка при запуске контейнеров${NC}"
    exit 1
}

echo -e "${BLUE}Ожидание запуска контейнера...${NC}"
sleep 5

if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    echo -e "${RED}✗ Контейнер не запустился!${NC}"
    echo -e "${YELLOW}Проверьте логи: $DOCKER_COMPOSE logs crm${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Контейнер запущен${NC}"

# ============================================================================
# ШАГ 6: Проверка текущего состояния миграций
# ============================================================================
print_section "ШАГ 6: Анализ текущего состояния миграций"

echo -e "${BLUE}Текущая версия миграций:${NC}"
CURRENT_REVISION=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1 | grep -oP '\(revision: \K[^)]+' || echo "не определена")
echo -e "${YELLOW}  Ревизия: ${CURRENT_REVISION}${NC}"

echo -e "\n${BLUE}Доступные миграции:${NC}"
$DOCKER_COMPOSE exec -T crm alembic history | head -10

# ============================================================================
# ШАГ 7: Применение миграций
# ============================================================================
print_section "ШАГ 7: Применение миграций базы данных"

echo -e "${BLUE}Применение всех миграций до head...${NC}"
if $DOCKER_COMPOSE exec -T crm alembic upgrade head 2>&1 | tee /tmp/migration_output.log; then
    echo -e "${GREEN}✓ Миграции применены успешно${NC}"
else
    MIGRATION_ERROR=$?
    echo -e "${RED}✗ Ошибка при применении миграций!${NC}"
    echo -e "${YELLOW}Последние строки лога:${NC}"
    tail -20 /tmp/migration_output.log
    echo -e "${YELLOW}Лог сохранен в /tmp/migration_output.log${NC}"
    exit 1
fi

FINAL_REVISION=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1 | grep -oP '\(revision: \K[^)]+' || echo "не определена")
if [ "$CURRENT_REVISION" != "$FINAL_REVISION" ]; then
    echo -e "${GREEN}✓ Миграции обновлены: ${CURRENT_REVISION} → ${FINAL_REVISION}${NC}"
else
    echo -e "${BLUE}Миграции уже на последней версии${NC}"
fi

# ============================================================================
# ШАГ 8: Исправление прав в базе данных
# ============================================================================
print_section "ШАГ 8: Проверка и исправление прав доступа"

if [ -f "fix_permissions.py" ]; then
    echo -e "${BLUE}Копирование скрипта исправления прав в контейнер...${NC}"
    if docker cp fix_permissions.py crm:/app/fix_permissions.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/fix_permissions.py" < fix_permissions.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}"
        
        echo -e "${BLUE}Запуск скрипта исправления прав...${NC}\n"
        if $DOCKER_COMPOSE exec -T crm python fix_permissions.py; then
            echo -e "\n${GREEN}✓ Права проверены и исправлены${NC}"
            $DOCKER_COMPOSE exec -T crm rm -f /app/fix_permissions.py 2>/dev/null || true
        else
            echo -e "${YELLOW}⚠ Ошибка при исправлении прав (продолжаем)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Не удалось скопировать скрипт (продолжаем)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Скрипт fix_permissions.py не найден (пропускаем)${NC}"
fi

# ============================================================================
# ШАГ 9: Анализ состояния системы
# ============================================================================
print_section "ШАГ 9: Анализ состояния системы"

echo -e "${BLUE}Проверка ролей и прав в базе данных...${NC}"
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission
db = SessionLocal()
try:
    roles = db.query(Role).all()
    print(f'  Ролей: {len(roles)}')
    for role in roles:
        perm_count = db.query(RolePermission).filter(RolePermission.role_id == role.id).count()
        print(f'    - {role.name}: {perm_count} прав')
    permissions = db.query(Permission).all()
    print(f'  Всего прав: {len(permissions)}')
    total_role_perms = db.query(RolePermission).count()
    print(f'  Всего связей роли-права: {total_role_perms}')
finally:
    db.close()
" 2>/dev/null || echo -e "${YELLOW}  Не удалось проверить роли${NC}"

# ============================================================================
# ШАГ 10: Проверка работоспособности
# ============================================================================
print_section "ШАГ 10: Проверка работоспособности приложения"

echo -e "${BLUE}Ожидание готовности приложения...${NC}"
sleep 3

MAX_RETRIES=10
RETRY_COUNT=0
HEALTH_CHECK_PASSED=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${YELLOW}  Попытка $RETRY_COUNT/$MAX_RETRIES...${NC}"
    sleep 2
done

if [ "$HEALTH_CHECK_PASSED" = true ]; then
    echo -e "${GREEN}✓ Приложение работает корректно${NC}"
    
    # Получаем информацию о версии
    CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "неизвестно")
    APP_VERSION=$($DOCKER_COMPOSE exec -T crm python -c "from app.version import __version__; print(__version__)" 2>/dev/null || echo "неизвестно")
    
    echo -e "\n${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}           ОБНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО!${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Версия кода:     ${CURRENT_COMMIT}${NC}"
    echo -e "${BLUE}Версия приложения: ${APP_VERSION}${NC}"
    echo -e "${BLUE}Ревизия миграций: ${FINAL_REVISION}${NC}"
    if [ -f "$BACKUP_FILE" ]; then
        echo -e "${BLUE}Резервная копия:  $BACKUP_FILE${NC}"
    fi
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "${RED}✗ Приложение не отвечает на health check!${NC}"
    echo -e "${YELLOW}Проверьте логи: $DOCKER_COMPOSE logs --tail=50 crm${NC}"
    if [ -f "$BACKUP_FILE" ]; then
        echo -e "${YELLOW}Резервная копия сохранена: $BACKUP_FILE${NC}"
    fi
    exit 1
fi

