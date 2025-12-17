# Инструкция по публикации проекта на GitHub

## Подготовка проекта

### 1. Проверка файлов

Убедитесь, что все необходимые файлы созданы:
- ✅ `Dockerfile`
- ✅ `docker-compose.yml`
- ✅ `.dockerignore`
- ✅ `.gitignore`
- ✅ `requirements.txt`
- ✅ `.env.example`
- ✅ `docker-entrypoint.sh`
- ✅ `DOCKER.md`

### 2. Проверка .gitignore

Убедитесь, что `.gitignore` исключает:
- Файлы базы данных (`.db`, `.db-shm`, `.db-wal`)
- Логи (`logs/`, `*.log`)
- Временные файлы (`tmp_*.py`, `_tmp_*.py`)
- Виртуальные окружения (`venv/`, `env/`)
- Файлы IDE (`.vscode/`, `.idea/`)
- Файлы окружения (`.env`)

### 3. Проверка конфиденциальных данных

**ВАЖНО:** Убедитесь, что в репозитории нет:
- Реальных паролей
- Секретных ключей
- API ключей
- Личных данных

Все чувствительные данные должны быть в `.env`, который исключен через `.gitignore`.

## Создание репозитория на GitHub

### Вариант 1: Через веб-интерфейс GitHub

1. Войдите в GitHub и нажмите "New repository"
2. Заполните:
   - **Repository name:** `parfume-crm` (или другое имя)
   - **Description:** `CRM система для парфюмерного бизнеса`
   - **Visibility:** Public или Private (на ваш выбор)
   - **НЕ** добавляйте README, .gitignore или лицензию (они уже есть)
3. Нажмите "Create repository"

### Вариант 2: Через GitHub CLI

```bash
gh repo create parfume-crm --public --description "CRM система для парфюмерного бизнеса"
```

## Инициализация Git и публикация

### 1. Инициализация Git (если еще не сделано)

```bash
git init
```

### 2. Добавление всех файлов

```bash
git add .
```

### 3. Проверка что будет закоммичено

```bash
git status
```

Убедитесь, что нет файлов, которые не должны быть в репозитории (БД, логи, .env и т.д.)

### 4. Первый коммит

```bash
git commit -m "Initial commit: Parfume CRM with Docker support"
```

### 5. Добавление remote репозитория

```bash
# Замените <username> на ваш GitHub username
git remote add origin https://github.com/<username>/parfume-crm.git

# Или через SSH
git remote add origin git@github.com:<username>/parfume-crm.git
```

### 6. Публикация на GitHub

```bash
git branch -M main
git push -u origin main
```

## Обновление README для GitHub

Убедитесь, что в `README.md` есть:

1. Описание проекта
2. Скриншоты (если есть)
3. Инструкции по установке
4. Инструкции по Docker
5. Информация о лицензии
6. Badges (опционально)

## Добавление GitHub Actions (опционально)

Создайте `.github/workflows/docker-build.yml` для автоматической сборки Docker образа:

```yaml
name: Docker Build

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: docker build -t parfume-crm:latest .
    
    - name: Test Docker image
      run: docker run -d --name test-crm -p 8000:8000 parfume-crm:latest
```

## Настройка GitHub Pages (если нужно)

Если нужна документация на GitHub Pages:

1. Создайте директорию `docs/`
2. Добавьте документацию
3. В настройках репозитория включите GitHub Pages
4. Выберите источник: `main branch / docs folder`

## Дополнительные рекомендации

### 1. Добавление лицензии

Создайте файл `LICENSE` с выбранной лицензией (MIT, Apache 2.0, и т.д.)

### 2. Добавление CONTRIBUTING.md

Если проект открыт для контрибьюторов, создайте `CONTRIBUTING.md` с инструкциями.

### 3. Настройка Issues и Projects

Включите Issues и Projects в настройках репозитория для управления задачами.

### 4. Защита главной ветки

В настройках репозитория → Branches → Add rule:
- Require pull request reviews
- Require status checks to pass
- Require branches to be up to date

### 5. Добавление тегов релизов

```bash
# Создание тега
git tag -a v1.0.0 -m "Release version 1.0.0"

# Публикация тега
git push origin v1.0.0
```

## Проверка после публикации

1. Откройте репозиторий на GitHub
2. Убедитесь, что все файлы на месте
3. Проверьте, что `.env` и другие чувствительные файлы не попали в репозиторий
4. Проверьте, что README отображается корректно
5. Протестируйте клонирование:
   ```bash
   git clone https://github.com/<username>/parfume-crm.git
   cd parfume-crm
   docker-compose up -d
   ```

## Обновление проекта

После внесения изменений:

```bash
git add .
git commit -m "Описание изменений"
git push
```

## Полезные ссылки

- [GitHub Docs](https://docs.github.com/)
- [Docker Hub](https://hub.docker.com/) - для публикации Docker образов
- [GitHub Actions](https://docs.github.com/en/actions)

