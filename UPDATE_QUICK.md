# Быстрое обновление - Шпаргалка

## Самый простой способ (автоматический)

```bash
chmod +x update.sh
./update.sh
```

Скрипт автоматически:
1. ✅ Создаст резервную копию БД
2. ✅ Обновит код из Git
3. ✅ Пересоберет образ (если нужно)
4. ✅ Применит миграции
5. ✅ Проверит работоспособность

## Ручное обновление (3 шага)

### 1. Резервная копия
```bash
docker-compose exec crm sqlite3 /app/data/crm.db ".backup /app/data/crm_backup_$(date +%Y%m%d_%H%M%S).db"
```

### 2. Обновление
```bash
git pull origin main
docker-compose build  # только если изменились зависимости
docker-compose up -d
docker-compose exec crm alembic upgrade head
```

### 3. Проверка
```bash
curl http://localhost:8000/health
docker-compose logs --tail=50 crm
```

## Откат (если что-то пошло не так)

```bash
# Восстановить БД
cp ./backups/crm_backup_YYYYMMDD_HHMMSS.db ./data/crm.db

# Откатить код
git checkout <предыдущий-коммит>

# Перезапустить
docker-compose restart
```

## Важно!

- ⚠️ **ВСЕГДА** делайте резервную копию перед обновлением
- ⚠️ Проверяйте логи после обновления
- ⚠️ Тестируйте на тестовом сервере перед продакшеном

Подробная инструкция: [DEPLOYMENT.md](DEPLOYMENT.md)










