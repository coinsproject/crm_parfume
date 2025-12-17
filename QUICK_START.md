# Быстрый старт

## Публикация на GitHub

1. **Создайте репозиторий на GitHub** (через веб-интерфейс или CLI)

2. **Инициализируйте Git и опубликуйте:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Parfume CRM with Docker support"
   git branch -M main
   git remote add origin https://github.com/<ваш-username>/<название-репозитория>.git
   git push -u origin main
   ```

Подробные инструкции см. в [GITHUB_SETUP.md](GITHUB_SETUP.md)

## Запуск через Docker

### Самый простой способ:

```bash
# 1. Клонируйте репозиторий (или используйте текущую директорию)
git clone <repository-url>
cd CRM

# 2. Запустите
docker-compose up -d

# 3. Откройте в браузере
# http://localhost:8000
```

### Первый вход:
- **Логин:** `admin`
- **Пароль:** `admin123`

**Важно:** Смените пароль после первого входа!

### Остановка:
```bash
docker-compose down
```

Подробные инструкции см. в [DOCKER.md](DOCKER.md)

## Что было добавлено:

✅ `Dockerfile` - образ Docker для приложения  
✅ `docker-compose.yml` - конфигурация для удобного запуска  
✅ `docker-entrypoint.sh` - скрипт инициализации БД  
✅ `requirements.txt` - зависимости Python  
✅ `.dockerignore` - исключения для Docker  
✅ `.gitignore` - исключения для Git  
✅ `.env.example` - пример переменных окружения  
✅ `DOCKER.md` - подробная документация по Docker  
✅ `GITHUB_SETUP.md` - инструкции по публикации на GitHub  

## Структура проекта

```
CRM/
├── app/              # Основной код приложения
├── alembic/         # Миграции базы данных
├── data/            # База данных (создается автоматически)
├── logs/            # Логи приложения
├── Dockerfile       # Конфигурация Docker
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Следующие шаги

1. Опубликуйте проект на GitHub (см. GITHUB_SETUP.md)
2. Настройте переменные окружения в `.env`
3. При необходимости настройте PostgreSQL вместо SQLite
4. Настройте резервное копирование БД
5. Добавьте CI/CD через GitHub Actions (опционально)

