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
cd "$SCRIPT_DIR"

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

# Количество резервных копий для хранения (остальные будут удалены)
KEEP_BACKUPS=10

if $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    # Пробуем несколько способов копирования
    if docker cp crm:/app/data/crm.db "$BACKUP_FILE" 2>/dev/null; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
    elif $DOCKER_COMPOSE exec -T crm test -f /app/data/crm.db 2>/dev/null; then
        # Альтернативный способ через временный файл
        $DOCKER_COMPOSE exec -T crm sh -c "cp /app/data/crm.db /tmp/crm_backup_temp.db" 2>/dev/null
        if docker cp crm:/tmp/crm_backup_temp.db "$BACKUP_FILE" 2>/dev/null; then
            $DOCKER_COMPOSE exec -T crm rm -f /tmp/crm_backup_temp.db 2>/dev/null
            BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
            echo -e "${GREEN}✓ Резервная копия создана: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
        else
            echo -e "${YELLOW}⚠ Не удалось создать резервную копию, продолжаем...${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ База данных не найдена в контейнере, пропускаем бэкап${NC}"
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

# Удаление старых резервных копий
if [ -d "$BACKUP_DIR" ]; then
    echo -e "${BLUE}Очистка старых резервных копий (оставляем последние ${KEEP_BACKUPS})...${NC}"
    TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "crm_backup*.db" -type f | wc -l)
    
    if [ "$TOTAL_BACKUPS" -gt "$KEEP_BACKUPS" ]; then
        # Сортируем по времени модификации (новые первыми) и удаляем старые
        # Используем ls -t для сортировки по времени (более совместимо)
        OLD_BACKUPS=$(ls -t "$BACKUP_DIR"/crm_backup*.db 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)))
        
        DELETED_COUNT=0
        TOTAL_SIZE_FREED=0
        
        if [ -n "$OLD_BACKUPS" ]; then
            echo "$OLD_BACKUPS" | while read -r old_backup; do
                if [ -f "$old_backup" ]; then
                    SIZE=$(stat -f%z "$old_backup" 2>/dev/null || stat -c%s "$old_backup" 2>/dev/null || du -b "$old_backup" | cut -f1)
                    TOTAL_SIZE_FREED=$((TOTAL_SIZE_FREED + SIZE))
                    rm -f "$old_backup"
                    DELETED_COUNT=$((DELETED_COUNT + 1))
                    echo -e "${YELLOW}  Удален: $(basename "$old_backup")${NC}"
                fi
            done
        fi
        
        if [ "$DELETED_COUNT" -gt 0 ]; then
            # Вычисляем размер в MB (без bc для совместимости)
            SIZE_FREED_MB=$((TOTAL_SIZE_FREED / 1024 / 1024))
            if [ "$SIZE_FREED_MB" -gt 0 ]; then
                echo -e "${GREEN}✓ Удалено старых копий: ${DELETED_COUNT} (освобождено ~${SIZE_FREED_MB} MB)${NC}"
            else
                echo -e "${GREEN}✓ Удалено старых копий: ${DELETED_COUNT}${NC}"
            fi
        else
            echo -e "${BLUE}Нет старых копий для удаления${NC}"
        fi
    else
        echo -e "${BLUE}Количество копий в норме (${TOTAL_BACKUPS}/${KEEP_BACKUPS}), удаление не требуется${NC}"
    fi
fi

# ============================================================================
# ШАГ 2: Обновление кода из Git
# ============================================================================
print_section "ШАГ 2: Обновление кода из Git"

# Исправляем проблему с правами доступа Git (dubious ownership)
if [ -d ".git" ]; then
    REPO_DIR=$(pwd)
    git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true
fi

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
    # Проверяем изменения относительно предыдущего коммита
    if git diff HEAD@{1} HEAD --name-only 2>/dev/null | grep -qE "(Dockerfile|requirements\.txt|docker-compose\.yml|\.py$|\.html$|\.js$|\.css$)"; then
        echo -e "${YELLOW}Обнаружены изменения в коде или зависимостях${NC}"
        NEEDS_REBUILD=true
    else
        # Если не удалось определить через diff, проверяем последний коммит
        LAST_COMMIT_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -E "(Dockerfile|requirements\.txt|docker-compose\.yml|\.py$|\.html$|\.js$|\.css$)" || true)
        if [ -n "$LAST_COMMIT_FILES" ]; then
            echo -e "${YELLOW}Обнаружены изменения в последнем коммите${NC}"
            NEEDS_REBUILD=true
        fi
    fi
    
    # Если код обновлен, но не определили изменения - все равно пересобираем для надежности
    # (особенно важно для статических файлов, которые копируются в образ)
    if [ "$NEEDS_REBUILD" = false ]; then
        echo -e "${BLUE}Код обновлен, пересобираем образ для применения всех изменений${NC}"
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
ALEMBIC_OUTPUT=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1)
CURRENT_REVISION=$(echo "$ALEMBIC_OUTPUT" | grep -oP '\(revision: \K[^)]+' || echo "$ALEMBIC_OUTPUT" | grep -oE '[a-f0-9]{12,}' | head -1 || echo "не определена")
if [ "$CURRENT_REVISION" = "не определена" ] && echo "$ALEMBIC_OUTPUT" | grep -q "head"; then
    CURRENT_REVISION="head"
fi
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

ALEMBIC_FINAL_OUTPUT=$($DOCKER_COMPOSE exec -T crm alembic current 2>&1)
FINAL_REVISION=$(echo "$ALEMBIC_FINAL_OUTPUT" | grep -oP '\(revision: \K[^)]+' || echo "$ALEMBIC_FINAL_OUTPUT" | grep -oE '[a-f0-9]{12,}' | head -1 || echo "не определена")
if [ "$FINAL_REVISION" = "не определена" ] && echo "$ALEMBIC_FINAL_OUTPUT" | grep -q "head"; then
    FINAL_REVISION="head"
fi
if [ "$CURRENT_REVISION" != "$FINAL_REVISION" ] && [ "$CURRENT_REVISION" != "не определена" ] && [ "$FINAL_REVISION" != "не определена" ]; then
    echo -e "${GREEN}✓ Миграции обновлены: ${CURRENT_REVISION} → ${FINAL_REVISION}${NC}"
elif [ "$FINAL_REVISION" != "не определена" ]; then
    echo -e "${BLUE}Миграции на версии: ${FINAL_REVISION}${NC}"
else
    echo -e "${BLUE}Миграции уже на последней версии${NC}"
fi

# Перезапуск контейнера после миграций для применения изменений
echo -e "\n${BLUE}Перезапуск контейнера после миграций...${NC}"
$DOCKER_COMPOSE restart crm || {
    echo -e "${YELLOW}⚠ Не удалось перезапустить через restart, пробуем stop/start...${NC}"
    $DOCKER_COMPOSE stop crm 2>/dev/null || true
    sleep 2
    $DOCKER_COMPOSE start crm || {
        echo -e "${RED}✗ Ошибка при перезапуске контейнера${NC}"
        echo -e "${YELLOW}Проверьте логи: $DOCKER_COMPOSE logs --tail=50 crm${NC}"
    }
}
sleep 5

# Проверка логов на ошибки
echo -e "${BLUE}Проверка логов контейнера на ошибки...${NC}"
LOG_ERRORS=$($DOCKER_COMPOSE logs --tail=100 crm 2>&1 | grep -iE "(error|exception|traceback|failed|fatal)" | head -20 || true)
if [ -n "$LOG_ERRORS" ]; then
    echo -e "${YELLOW}⚠ Обнаружены ошибки в логах:${NC}"
    echo "$LOG_ERRORS" | while IFS= read -r line; do
        echo -e "${YELLOW}  $line${NC}"
    done
    echo -e "${YELLOW}Полные логи: $DOCKER_COMPOSE logs --tail=100 crm${NC}"
else
    echo -e "${GREEN}✓ Критических ошибок в логах не обнаружено${NC}"
fi

# Проверка статуса контейнера
if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "crm.*Up"; then
    echo -e "${RED}✗ Контейнер не запущен после миграций!${NC}"
    echo -e "${YELLOW}Последние 50 строк логов:${NC}"
    $DOCKER_COMPOSE logs --tail=50 crm
    exit 1
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
# ШАГ 8.5: Синхронизация ролей с локальной версией (русификация)
# ============================================================================
print_section "ШАГ 8.5: Синхронизация ролей (русификация описаний)"

if [ -f "sync_roles_to_local.py" ]; then
    echo -e "${BLUE}Копирование скрипта синхронизации ролей в контейнер...${NC}"
    if docker cp sync_roles_to_local.py crm:/app/sync_roles_to_local.py 2>/dev/null || \
       $DOCKER_COMPOSE exec -T crm sh -c "cat > /app/sync_roles_to_local.py" < sync_roles_to_local.py 2>/dev/null; then
        echo -e "${GREEN}✓ Скрипт скопирован${NC}"
        
        echo -e "${BLUE}Запуск синхронизации ролей...${NC}\n"
        if $DOCKER_COMPOSE exec -T crm python sync_roles_to_local.py; then
            echo -e "\n${GREEN}✓ Роли синхронизированы с локальной версией${NC}"
            $DOCKER_COMPOSE exec -T crm rm -f /app/sync_roles_to_local.py 2>/dev/null || true
        else
            echo -e "${YELLOW}⚠ Ошибка при синхронизации ролей (продолжаем)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Не удалось скопировать скрипт (продолжаем)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Скрипт sync_roles_to_local.py не найден (пропускаем)${NC}"
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
# ШАГ 9.5: Проверка и настройка UFW (firewall)
# ============================================================================
print_section "ШАГ 9.5: Проверка UFW (firewall)"

if command -v ufw &> /dev/null; then
    UFW_STATUS=$(sudo ufw status 2>/dev/null | head -1 || echo "inactive")
    if echo "$UFW_STATUS" | grep -qi "active"; then
        echo -e "${BLUE}UFW активен, проверяем порт 8000...${NC}"
        if sudo ufw status | grep -q "8000/tcp"; then
            echo -e "${GREEN}✓ Порт 8000 уже открыт в UFW${NC}"
        else
            echo -e "${YELLOW}Порт 8000 не открыт, открываем...${NC}"
            if sudo ufw allow 8000/tcp 2>/dev/null; then
                echo -e "${GREEN}✓ Порт 8000 открыт в UFW${NC}"
            else
                echo -e "${YELLOW}⚠ Не удалось открыть порт 8000 в UFW (продолжаем)${NC}"
            fi
        fi
    else
        echo -e "${BLUE}UFW не активен, пропускаем${NC}"
    fi
else
    echo -e "${BLUE}UFW не установлен, пропускаем${NC}"
fi

# ============================================================================
# ШАГ 10: Проверка работоспособности
# ============================================================================
print_section "ШАГ 10: Проверка работоспособности приложения"

echo -e "${BLUE}Ожидание готовности приложения...${NC}"
sleep 3

# Проверка статуса контейнера
CONTAINER_STATUS=$($DOCKER_COMPOSE ps crm 2>/dev/null | grep -E "crm.*Up" || echo "")
if [ -z "$CONTAINER_STATUS" ]; then
    echo -e "${RED}✗ Контейнер не запущен!${NC}"
    echo -e "${YELLOW}Статус контейнера:${NC}"
    $DOCKER_COMPOSE ps crm
    echo -e "\n${YELLOW}Последние 100 строк логов:${NC}"
    $DOCKER_COMPOSE logs --tail=100 crm
    exit 1
fi

echo -e "${GREEN}✓ Контейнер запущен${NC}"

# Проверка health check
MAX_RETRIES=15
RETRY_COUNT=0
HEALTH_CHECK_PASSED=false

echo -e "${BLUE}Проверка health check приложения...${NC}"
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${YELLOW}  Попытка $RETRY_COUNT/$MAX_RETRIES...${NC}"
    sleep 3
done

if [ "$HEALTH_CHECK_PASSED" = true ]; then
    echo -e "${GREEN}✓ Приложение работает корректно${NC}"
    
    # Финальная проверка логов на критические ошибки
    echo -e "${BLUE}Финальная проверка логов...${NC}"
    RECENT_ERRORS=$($DOCKER_COMPOSE logs --tail=50 crm --since 2m 2>&1 | grep -iE "(error|exception|traceback|failed|fatal)" | head -10 || true)
    if [ -n "$RECENT_ERRORS" ]; then
        echo -e "${YELLOW}⚠ Обнаружены недавние ошибки в логах:${NC}"
        echo "$RECENT_ERRORS" | while IFS= read -r line; do
            echo -e "${YELLOW}  $line${NC}"
        done
    else
        echo -e "${GREEN}✓ Критических ошибок не обнаружено${NC}"
    fi
    
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
    echo -e "\n${YELLOW}=== Диагностика проблемы ===${NC}"
    
    # Проверка статуса контейнера
    echo -e "${BLUE}Статус контейнера:${NC}"
    $DOCKER_COMPOSE ps crm
    
    # Проверка использования ресурсов
    echo -e "\n${BLUE}Использование ресурсов:${NC}"
    docker stats --no-stream crm 2>/dev/null || echo "Не удалось получить статистику"
    
    # Последние логи
    echo -e "\n${BLUE}Последние 100 строк логов:${NC}"
    $DOCKER_COMPOSE logs --tail=100 crm
    
    # Проверка портов
    echo -e "\n${BLUE}Проверка портов:${NC}"
    netstat -tlnp 2>/dev/null | grep 8000 || ss -tlnp 2>/dev/null | grep 8000 || echo "Порт 8000 не прослушивается"
    
    if [ -f "$BACKUP_FILE" ]; then
        echo -e "\n${YELLOW}Резервная копия сохранена: $BACKUP_FILE${NC}"
        echo -e "${YELLOW}Для восстановления: docker cp $BACKUP_FILE crm:/app/data/crm.db${NC}"
    fi
    
    echo -e "\n${YELLOW}Попробуйте перезапустить вручную:${NC}"
    echo -e "${YELLOW}  $DOCKER_COMPOSE restart crm${NC}"
    echo -e "${YELLOW}  $DOCKER_COMPOSE logs -f crm${NC}"
    
    exit 1
fi

