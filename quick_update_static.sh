#!/bin/bash
# Быстрое обновление статических файлов (CSS, JS) на сервере

echo "=== Быстрое обновление статических файлов ==="

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "Ошибка: docker-compose не найден"
    exit 1
fi

echo "1. Обновление кода из Git..."
git pull origin main || {
    echo "Ошибка при обновлении кода"
    exit 1
}

echo ""
echo "2. Пересборка Docker образа (для применения изменений в статических файлах)..."
$DOCKER_COMPOSE build --no-cache crm || {
    echo "Ошибка при пересборке образа"
    exit 1
}

echo ""
echo "3. Перезапуск контейнера..."
$DOCKER_COMPOSE up -d crm || {
    echo "Ошибка при перезапуске контейнера"
    exit 1
}

echo ""
echo "4. Ожидание запуска контейнера..."
sleep 5

echo ""
echo "=== Готово ==="
echo ""
echo "ВАЖНО: Очистите кеш браузера или сделайте Hard Refresh:"
echo "  - Chrome/Edge: Ctrl+Shift+R (Windows) или Cmd+Shift+R (Mac)"
echo "  - Firefox: Ctrl+F5 (Windows) или Cmd+Shift+R (Mac)"
echo "  - Safari: Cmd+Option+R (Mac)"
echo ""
echo "Или откройте в режиме инкогнито для проверки"

