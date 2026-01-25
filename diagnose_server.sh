#!/bin/bash
# Скрипт для диагностики проблем на сервере

echo "=== Диагностика CRM на сервере ==="
echo ""

echo "1. Проверка Docker:"
docker --version
docker-compose --version || docker compose version
echo ""

echo "2. Проверка статуса контейнеров:"
docker ps -a | grep -E "parfume|crm" || echo "Контейнеры не найдены"
echo ""

echo "3. Проверка логов контейнера (последние 50 строк):"
docker logs parfume-crm --tail=50 2>&1 || echo "Не удалось получить логи"
echo ""

echo "4. Проверка файлов проекта:"
cd /opt/crm_parfume 2>/dev/null || cd /opt/crm_parfume/crm_parfume 2>/dev/null || echo "Директория не найдена"
pwd
ls -la | head -20
echo ""

echo "5. Проверка docker-compose.yml:"
if [ -f docker-compose.yml ]; then
    echo "docker-compose.yml найден"
    docker-compose config 2>&1 | head -30 || docker compose config 2>&1 | head -30
else
    echo "docker-compose.yml не найден!"
fi
echo ""

echo "6. Проверка Dockerfile:"
if [ -f Dockerfile ]; then
    echo "Dockerfile найден"
    head -20 Dockerfile
else
    echo "Dockerfile не найден!"
fi
echo ""

echo "7. Проверка базы данных:"
if [ -f ./data/crm.db ]; then
    echo "База данных найдена:"
    ls -lh ./data/crm.db
else
    echo "База данных не найдена в ./data/crm.db"
fi
echo ""

echo "8. Попытка сборки образа:"
docker-compose build --no-cache 2>&1 | tail -30 || docker compose build --no-cache 2>&1 | tail -30
echo ""

echo "=== Конец диагностики ==="

