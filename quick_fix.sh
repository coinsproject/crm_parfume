#!/bin/bash
# Быстрое исправление для обновления на сервере

echo "=== Быстрое исправление ==="

# Сохраняем локальные изменения
echo "Сохранение локальных изменений..."
git stash

# Обновляем код
echo "Обновление кода из репозитория..."
git pull origin main

# Останавливаем старый контейнер
echo "Остановка старого контейнера..."
docker-compose down 2>/dev/null || docker stop parfume-crm 2>/dev/null || true
docker rm parfume-crm 2>/dev/null || true

# Запускаем обновление
echo "Запуск обновления..."
chmod +x update.sh
./update.sh

echo "=== Готово ==="



