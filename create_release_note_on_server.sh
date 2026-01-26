#!/bin/bash
# Скрипт для создания релиз-ноутса на сервере

echo "=== Создание релиз-ноутса на сервере ==="

# Определяем команду docker compose
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "Ошибка: docker-compose не найден"
    exit 1
fi

echo "1. Проверка существующих релиз-ноутсов..."
$DOCKER_COMPOSE exec -T crm python -c "
from app.db import SessionLocal
from app.models import ReleaseNote
db = SessionLocal()
notes = db.query(ReleaseNote).all()
print(f'Найдено релиз-ноутсов: {len(notes)}')
for note in notes:
    print(f'  - {note.version}: {note.title}')
db.close()
"

echo ""
echo "2. Проверка текущей версии..."
$DOCKER_COMPOSE exec -T crm python -c "
from app.version import __version__
print(f'Текущая версия в коде: {__version__}')
"

echo ""
echo "3. Создание релиз-ноутса для версии 1.2.0..."
$DOCKER_COMPOSE exec -T crm python << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/app')

from app.db import SessionLocal
from app.models import User, ReleaseNote
from datetime import date
from sqlalchemy import text

db = SessionLocal()

try:
    # Проверяем, есть ли уже релиз-ноутс для 1.2.0
    existing = db.query(ReleaseNote).filter(ReleaseNote.version == '1.2.0').first()
    if existing:
        print('Релиз-ноутс для версии 1.2.0 уже существует!')
        print(f'ID: {existing.id}, Заголовок: {existing.title}')
    else:
        # Получаем администратора
        admin = db.query(User).join(User.role).filter(User.role.has(name='ADMIN')).first()
        if not admin:
            print('Ошибка: администратор не найден')
            sys.exit(1)
        
        # Проверяем наличие полей в таблице
        try:
            result = db.execute(text("PRAGMA table_info(release_notes)"))
            columns = [row[1] for row in result.fetchall()]
            has_new_fields = 'is_published_to_partners' in columns and 'max_partner_views' in columns
        except:
            has_new_fields = False
        
        # Создаем релиз-ноутс
        release_note_data = {
            'version': '1.2.0',
            'title': 'Версия 1.2.0 - Адаптация для мобильных устройств',
            'description': 'Полная адаптация интерфейса CRM для работы на мобильных телефонах и планшетах. Добавлена автоматизация управления версиями.',
            'release_type': 'minor',
            'release_date': date.today(),
            'changes': '''Добавлено:
- Полная адаптация интерфейса для мобильных устройств (телефоны и планшеты)
- Адаптивное мобильное меню с бургер-кнопкой
- Оптимизация таблиц для мобильных экранов
- Улучшение форм для touch-устройств
- Автоматическое управление версиями и релиз-ноутсами
- API для создания версий программно

Изменено:
- Улучшена читаемость на маленьких экранах
- Оптимизированы размеры шрифтов и отступы
- Улучшена навигация на мобильных устройствах

Исправлено:
- Проблемы с отображением на мобильных устройствах
- Улучшена работа модальных окон на мобильных''',
            'is_published': False,
            'is_important': False,
            'created_by_user_id': admin.id,
        }
        
        # Добавляем новые поля только если они существуют
        if has_new_fields:
            release_note_data['is_published_to_partners'] = False
            release_note_data['max_partner_views'] = None
        
        release_note = ReleaseNote(**release_note_data)
        
        db.add(release_note)
        db.commit()
        db.refresh(release_note)
        
        print('✓ Релиз-ноутс создан!')
        print(f'  ID: {release_note.id}')
        print(f'  Версия: {release_note.version}')
        print(f'  Заголовок: {release_note.title}')
except Exception as e:
    print(f'Ошибка при создании релиз-ноутса: {e}')
    import traceback
    traceback.print_exc()
    db.rollback()
finally:
    db.close()
PYTHON_SCRIPT

echo ""
echo "=== Готово ==="

