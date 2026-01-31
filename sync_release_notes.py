#!/usr/bin/env python
"""Скрипт для синхронизации релиз-ноутсов на сервере"""
import sys
import os
from datetime import date

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal
from app.models import User, ReleaseNote
from app.services.version_service import create_release_note

# Определяем все релиз-ноутсы, которые должны быть
RELEASE_NOTES = [
    {
        "version": "1.2.0",
        "title": "Версия 1.2.0 - Автоматизация версионирования",
        "description": "Добавлена автоматизация управления версиями и релиз-ноутсами",
        "release_type": "minor",
        "release_date": date(2026, 1, 26),
        "changes": """Добавлено:
- Автоматическое управление версиями
- Система релиз-ноутсов
- API для создания версий программно
- Автоматическое определение следующей версии""",
    },
    {
        "version": "1.3.0",
        "title": "Версия 1.3.0",
        "description": "Обновление системы",
        "release_type": "minor",
        "release_date": date(2026, 1, 27),
        "changes": "Обновление системы",
    },
    {
        "version": "1.3.1",
        "title": "Версия 1.3.1 - Документация",
        "description": "Добавлена секция документации в админ-панели с инструкциями по настройке и обновлению",
        "release_type": "patch",
        "release_date": date(2026, 1, 27),
        "changes": """Добавлено:
- Секция документации в админ-панели (/settings/docs)
- Инструкции по настройке уведомлений (email и Telegram)
- Инструкции по обновлению системы
- Интеграция релиз-ноутсов в документацию""",
    },
    {
        "version": "1.3.2",
        "title": "Версия 1.3.2 - Профиль администратора",
        "description": "Добавлена страница профиля администратора с возможностью редактирования данных и смены пароля",
        "release_type": "patch",
        "release_date": date(2026, 1, 27),
        "changes": """Добавлено:
- Страница профиля администратора (/settings/profile)
- Возможность редактирования имени (full_name) и email
- Возможность смены пароля с проверкой текущего пароля
- Ссылка на профиль в верхней панели (topbar)
- Ссылка на профиль в меню настроек

Изменено:
- Улучшена навигация для администраторов
- Добавлена валидация при смене пароля (минимум 6 символов)
- Добавлена проверка уникальности email при обновлении профиля""",
    },
    {
        "version": "1.3.3",
        "title": "Версия 1.3.3 - Оптимизация кода",
        "description": "Проведена масштабная оптимизация кодовой базы: удалены временные файлы, старые скрипты и дублирующаяся документация",
        "release_type": "patch",
        "release_date": date(2026, 1, 27),
        "changes": """Удалено:
- Все временные файлы (tmp_*.py, _tmp_*.py, tmp_*.txt)
- Старые скрипты обновления (update.sh, quick_update_static.sh, quick_fix.sh и др.)
- Старые диагностические скрипты (diagnose_server.sh, check_server.sh и др.)
- Старые скрипты миграций (fix_migration.sh, force_migrate.sh и др.)
- Утилиты, которые уже применены (add_price_indexes.py, add_price_history_index.py, set_partner_markup.py)
- Старая папка migrations/ (миграции уже в alembic)
- Дублирующиеся markdown файлы с инструкциями (8 файлов)
- Старые базы данных в корне проекта

Обновлено:
- README.md: ссылки на update.sh заменены на full_update.sh
- DEPLOYMENT.md: инструкции по использованию full_update.sh
- .gitignore: добавлено исключение для tmp_*.txt

Результат:
- Удалено 35 файлов
- Упрощена структура проекта
- Улучшена читаемость документации
- Все функции обновления теперь через единый скрипт full_update.sh""",
    },
]

def sync_release_notes():
    """Синхронизирует релиз-ноутсы на сервере"""
    db = SessionLocal()
    
    try:
        # Получаем администратора
        admin = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).first()
        if not admin:
            print("Ошибка: администратор не найден")
            return
        
        print("=== Синхронизация релиз-ноутсов ===\n")
        
        created_count = 0
        skipped_count = 0
        
        for release_data in RELEASE_NOTES:
            version = release_data["version"]
            
            # Проверяем, существует ли уже этот релиз-ноутс
            existing = db.query(ReleaseNote).filter(ReleaseNote.version == version).first()
            
            if existing:
                print(f"✓ Версия {version} уже существует (ID: {existing.id})")
                skipped_count += 1
            else:
                try:
                    # Создаем релиз-ноутс
                    release_note = create_release_note(
                        db=db,
                        version=version,
                        title=release_data["title"],
                        description=release_data.get("description"),
                        release_type=release_data.get("release_type", "minor"),
                        changes=release_data.get("changes"),
                        is_published=release_data.get("is_published", False),
                        is_published_to_partners=release_data.get("is_published_to_partners", False),
                        is_important=release_data.get("is_important", False),
                        max_partner_views=release_data.get("max_partner_views"),
                        created_by_user_id=admin.id,
                        release_date=release_data.get("release_date", date.today()),
                    )
                    print(f"✓ Создан релиз-ноутс для версии {version} (ID: {release_note.id})")
                    created_count += 1
                except ValueError as e:
                    print(f"✗ Ошибка при создании версии {version}: {e}")
                    skipped_count += 1
        
        print(f"\n=== Результат ===")
        print(f"Создано: {created_count}")
        print(f"Пропущено (уже существуют): {skipped_count}")
        print(f"Всего обработано: {len(RELEASE_NOTES)}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    sync_release_notes()

