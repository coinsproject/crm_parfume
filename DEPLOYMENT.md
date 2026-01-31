# Инструкция по обновлению приложения на сервере

## Важно: Резервное копирование перед обновлением

**ВСЕГДА делайте резервную копию базы данных перед обновлением!**

## Быстрое обновление (Docker)

### Шаг 1: Резервное копирование базы данных

```bash
# Остановите контейнер
docker-compose stop

# Создайте резервную копию БД
docker-compose exec crm sqlite3 /app/data/crm.db ".backup /app/data/crm_backup_$(date +%Y%m%d_%H%M%S).db"

# Или скопируйте файл БД напрямую
cp ./data/crm.db ./backups/crm_backup_$(date +%Y%m%d_%H%M%S).db

# Убедитесь, что резервная копия создана
ls -lh ./data/crm_backup_*.db
```

### Шаг 2: Обновление кода

```bash
# Перейдите в директорию проекта
cd /path/to/crm_parfume

# Получите последние изменения из Git
git fetch origin
git pull origin main

# Проверьте, что изменения получены
git log --oneline -5
```

### Шаг 3: Пересборка и перезапуск

```bash
# Пересоберите Docker образ (если изменились зависимости или Dockerfile)
docker-compose build

# Или пересоберите без кэша (если есть проблемы)
docker-compose build --no-cache

# Примените миграции (если они есть)
docker-compose up -d
docker-compose exec crm alembic upgrade head

# Проверьте логи
docker-compose logs -f
```

### Шаг 4: Проверка работоспособности

```bash
# Проверьте, что контейнер запущен
docker-compose ps

# Проверьте health endpoint
curl http://localhost:8000/health

# Проверьте логи на ошибки
docker-compose logs --tail=50 crm
```

## Детальная инструкция

### Вариант 1: Обновление с Docker Compose (рекомендуется)

#### 1. Подготовка

```bash
# Создайте директорию для бэкапов (если её нет)
mkdir -p ./backups

# Проверьте текущую версию
git log --oneline -1

# Проверьте статус контейнеров
docker-compose ps
```

#### 2. Резервное копирование

```bash
# Полная резервная копия БД
BACKUP_FILE="./backups/crm_backup_$(date +%Y%m%d_%H%M%S).db"
docker-compose exec crm sqlite3 /app/data/crm.db ".backup $BACKUP_FILE"

# Копирование на локальный диск (если нужно)
docker cp crm:/app/data/crm.db "$BACKUP_FILE"

# Проверка размера бэкапа
ls -lh "$BACKUP_FILE"
```

#### 3. Обновление кода

```bash
# Сохраните текущую версию (опционально, для отката)
git tag backup-$(date +%Y%m%d_%H%M%S)

# Получите обновления
git fetch origin main
git pull origin main

# Проверьте изменения
git diff HEAD~1 HEAD
```

#### 4. Обновление зависимостей (если изменился requirements.txt)

```bash
# Пересоберите образ
docker-compose build

# Или без кэша
docker-compose build --no-cache
```

#### 5. Применение миграций

```bash
# Запустите контейнер
docker-compose up -d

# Дождитесь полного запуска
sleep 5

# Примените миграции
docker-compose exec crm alembic upgrade head

# Проверьте статус миграций
docker-compose exec crm alembic current
```

#### 6. Перезапуск

```bash
# Перезапустите контейнер
docker-compose restart

# Или полный перезапуск
docker-compose down
docker-compose up -d
```

#### 7. Проверка

```bash
# Проверьте логи
docker-compose logs -f --tail=100

# Проверьте доступность
curl http://localhost:8000/health

# Проверьте в браузере
# Откройте http://your-server:8000
```

### Вариант 2: Обновление без Docker (локальная установка)

#### 1. Резервное копирование

```bash
# Остановите приложение (если запущено через systemd/supervisor)
sudo systemctl stop crm
# или
supervisorctl stop crm

# Создайте резервную копию
BACKUP_FILE="./backups/crm_backup_$(date +%Y%m%d_%H%M%S).db"
cp ./data/crm.db "$BACKUP_FILE"

# Или через SQLite
sqlite3 ./data/crm.db ".backup $BACKUP_FILE"
```

#### 2. Обновление кода

```bash
# Получите обновления
git fetch origin main
git pull origin main
```

#### 3. Обновление зависимостей

```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Обновите зависимости
pip install -r requirements.txt --upgrade
```

#### 4. Применение миграций

```bash
# Примените миграции
alembic upgrade head

# Проверьте статус
alembic current
```

#### 5. Перезапуск

```bash
# Запустите приложение
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Или через systemd
sudo systemctl restart crm

# Или через supervisor
supervisorctl restart crm
```

## Откат к предыдущей версии (если что-то пошло не так)

### С Docker

```bash
# Остановите текущий контейнер
docker-compose down

# Восстановите БД из резервной копии
cp ./backups/crm_backup_YYYYMMDD_HHMMSS.db ./data/crm.db

# Откатите код к предыдущей версии
git log --oneline  # Найдите нужный коммит
git checkout <commit-hash>

# Пересоберите и запустите
docker-compose build
docker-compose up -d
```

### Без Docker

```bash
# Восстановите БД
cp ./backups/crm_backup_YYYYMMDD_HHMMSS.db ./data/crm.db

# Откатите код
git checkout <commit-hash>

# Перезапустите
sudo systemctl restart crm
```

## Автоматизация обновлений

### Скрипт для автоматического обновления

Используйте скрипт `full_update.sh`:

```bash
#!/bin/bash
set -e

echo "=== Начало обновления CRM ==="

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Директория проекта
PROJECT_DIR="/path/to/crm_parfume"
cd "$PROJECT_DIR"

# 1. Резервное копирование
echo -e "${YELLOW}Создание резервной копии...${NC}"
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/crm_backup_$(date +%Y%m%d_%H%M%S).db"

if [ -f "./data/crm.db" ]; then
    docker-compose exec -T crm sqlite3 /app/data/crm.db ".backup /app/data/backup_temp.db" || \
    cp ./data/crm.db "$BACKUP_FILE"
    echo -e "${GREEN}Резервная копия создана: $BACKUP_FILE${NC}"
else
    echo -e "${RED}Файл БД не найден!${NC}"
    exit 1
fi

# 2. Обновление кода
echo -e "${YELLOW}Обновление кода из Git...${NC}"
git fetch origin main
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}Уже на последней версии${NC}"
    exit 0
fi

git pull origin main
echo -e "${GREEN}Код обновлен${NC}"

# 3. Пересборка (если нужно)
echo -e "${YELLOW}Проверка изменений в Dockerfile...${NC}"
if git diff HEAD~1 HEAD --name-only | grep -q "Dockerfile\|requirements.txt"; then
    echo -e "${YELLOW}Пересборка Docker образа...${NC}"
    docker-compose build
fi

# 4. Применение миграций
echo -e "${YELLOW}Применение миграций...${NC}"
docker-compose up -d
sleep 5
docker-compose exec crm alembic upgrade head || {
    echo -e "${RED}Ошибка при применении миграций!${NC}"
    echo -e "${YELLOW}Откат к предыдущей версии...${NC}"
    git checkout HEAD~1
    docker-compose restart
    exit 1
}

# 5. Проверка
echo -e "${YELLOW}Проверка работоспособности...${NC}"
sleep 3
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}Приложение работает корректно!${NC}"
else
    echo -e "${RED}Приложение не отвечает!${NC}"
    echo -e "${YELLOW}Проверьте логи: docker-compose logs${NC}"
    exit 1
fi

echo -e "${GREEN}=== Обновление завершено успешно ===${NC}"
```

Сделайте скрипт исполняемым:

```bash
chmod +x full_update.sh
```

Использование:

```bash
sudo ./full_update.sh
```

## Рекомендации по безопасности

### 1. Регулярные бэкапы

Настройте автоматическое резервное копирование:

```bash
# Добавьте в crontab (каждый день в 2:00)
0 2 * * * cd /path/to/crm_parfume && docker-compose exec -T crm sqlite3 /app/data/crm.db ".backup /app/data/crm_backup_\$(date +\%Y\%m\%d).db"
```

### 2. Хранение бэкапов

- Храните бэкапы на отдельном диске или сервере
- Используйте облачное хранилище (S3, Google Drive, etc.)
- Храните минимум 7 последних бэкапов

### 3. Тестирование обновлений

Перед обновлением на продакшене:
1. Протестируйте на тестовом сервере
2. Проверьте миграции на копии БД
3. Убедитесь, что все функции работают

### 4. Мониторинг

После обновления проверьте:
- Логи приложения
- Использование памяти и CPU
- Доступность endpoints
- Работоспособность критичных функций

## Часто задаваемые вопросы

### Q: Что делать, если миграции не применяются?

```bash
# Проверьте текущую версию миграций
docker-compose exec crm alembic current

# Проверьте историю миграций
docker-compose exec crm alembic history

# Попробуйте применить вручную
docker-compose exec crm alembic upgrade head --sql  # Покажет SQL без выполнения
docker-compose exec crm alembic upgrade head
```

### Q: Как откатить миграцию?

```bash
# Откатить на одну версию назад
docker-compose exec crm alembic downgrade -1

# Откатить к конкретной версии
docker-compose exec crm alembic downgrade <revision>
```

### Q: Что делать, если контейнер не запускается?

```bash
# Проверьте логи
docker-compose logs crm

# Проверьте конфигурацию
docker-compose config

# Попробуйте запустить вручную
docker-compose run --rm crm /bin/bash
```

### Q: Как обновить только код без пересборки?

```bash
# Если не менялись зависимости и Dockerfile
git pull origin main
docker-compose restart
docker-compose exec crm alembic upgrade head
```

## Контрольный список перед обновлением

- [ ] Создана резервная копия БД
- [ ] Проверена работоспособность текущей версии
- [ ] Прочитаны изменения в CHANGELOG (если есть)
- [ ] Проверены новые миграции
- [ ] Обновлен код из Git
- [ ] Применены миграции
- [ ] Проверена работоспособность после обновления
- [ ] Проверены логи на ошибки

## Полезные команды

```bash
# Просмотр логов в реальном времени
docker-compose logs -f crm

# Просмотр последних 100 строк логов
docker-compose logs --tail=100 crm

# Проверка статуса контейнеров
docker-compose ps

# Вход в контейнер
docker-compose exec crm /bin/bash

# Проверка размера БД
docker-compose exec crm sqlite3 /app/data/crm.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();"

# Список таблиц
docker-compose exec crm sqlite3 /app/data/crm.db ".tables"

# Экспорт данных (опционально)
docker-compose exec crm sqlite3 /app/data/crm.db ".dump" > backup.sql
```










