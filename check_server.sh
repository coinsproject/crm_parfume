#!/bin/bash
# Диагностический скрипт для проверки окружения на сервере

echo "=== Диагностика сервера ==="
echo ""

echo "1. Текущая директория:"
pwd
echo ""

echo "2. Содержимое текущей директории:"
ls -la
echo ""

echo "3. Проверка Docker:"
if command -v docker &> /dev/null; then
    echo "✓ Docker установлен: $(docker --version)"
else
    echo "✗ Docker НЕ установлен"
fi
echo ""

echo "4. Проверка Docker Compose:"
if command -v docker-compose &> /dev/null; then
    echo "✓ docker-compose установлен: $(docker-compose --version)"
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    echo "✓ docker compose установлен: $(docker compose version)"
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "✗ Docker Compose НЕ найден"
    DOCKER_COMPOSE_CMD=""
fi
echo ""

echo "5. Проверка структуры проекта:"
if [ -f "docker-compose.yml" ]; then
    echo "✓ docker-compose.yml найден"
else
    echo "✗ docker-compose.yml НЕ найден в текущей директории"
    echo "  Ищем в родительских директориях..."
    find .. -maxdepth 2 -name "docker-compose.yml" 2>/dev/null | head -5
fi
echo ""

echo "6. Проверка файла update.sh:"
if [ -f "update.sh" ]; then
    echo "✓ update.sh найден"
    if [ -x "update.sh" ]; then
        echo "✓ update.sh исполняемый"
    else
        echo "✗ update.sh НЕ исполняемый (нужно: chmod +x update.sh)"
    fi
else
    echo "✗ update.sh НЕ найден"
fi
echo ""

echo "7. Проверка Git репозитория:"
if [ -d ".git" ]; then
    echo "✓ Git репозиторий найден"
    echo "  Ветка: $(git branch --show-current 2>/dev/null || echo 'неизвестно')"
    echo "  Последний коммит: $(git log -1 --oneline 2>/dev/null || echo 'неизвестно')"
else
    echo "✗ Git репозиторий НЕ найден"
fi
echo ""

echo "8. Проверка контейнеров Docker:"
if [ -n "$DOCKER_COMPOSE_CMD" ]; then
    if [ -f "docker-compose.yml" ]; then
        echo "Запущенные контейнеры:"
        $DOCKER_COMPOSE_CMD ps 2>/dev/null || echo "  Ошибка при проверке контейнеров"
    else
        echo "  docker-compose.yml не найден, пропускаем проверку контейнеров"
    fi
else
    echo "  Docker Compose не найден, пропускаем проверку контейнеров"
fi
echo ""

echo "9. Проверка базы данных:"
if [ -f "data/crm.db" ]; then
    echo "✓ База данных найдена: data/crm.db"
    ls -lh data/crm.db
elif [ -f "./data/crm.db" ]; then
    echo "✓ База данных найдена: ./data/crm.db"
    ls -lh ./data/crm.db
else
    echo "✗ База данных НЕ найдена (это нормально для первого запуска)"
fi
echo ""

echo "=== Рекомендации ==="
echo ""

if [ ! -f "docker-compose.yml" ]; then
    echo "⚠ ПРОБЛЕМА: docker-compose.yml не найден в текущей директории"
    echo "  Решение:"
    echo "    1. Проверьте, что вы находитесь в правильной директории"
    echo "    2. Или найдите правильную директорию: find /opt -name docker-compose.yml"
    echo ""
fi

if [ -z "$DOCKER_COMPOSE_CMD" ]; then
    echo "⚠ ПРОБЛЕМА: Docker Compose не установлен"
    echo "  Решение:"
    echo "    sudo apt-get update"
    echo "    sudo apt-get install docker-compose"
    echo "    # или для новой версии Docker Compose V2 уже входит в Docker"
    echo ""
fi

if [ ! -x "update.sh" ] && [ -f "update.sh" ]; then
    echo "⚠ ПРОБЛЕМА: update.sh не исполняемый"
    echo "  Решение: chmod +x update.sh"
    echo ""
fi

echo "=== Конец диагностики ==="

