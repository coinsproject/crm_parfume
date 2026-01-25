#!/usr/bin/env python
"""Скрипт для автоматического создания новой версии и релиз-ноутса"""
import sys
import os
from datetime import date

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal
from app.services.version_service import create_version_and_release_note, update_version_file
from app.models import User, Notification, Partner

def main():
    """Создает новую версию 1.1.0 с описанием изменений"""
    db = SessionLocal()
    
    try:
        # Получаем администратора
        admin = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).first()
        if not admin:
            print("Ошибка: администратор не найден")
            return
        
        # Создаем версию 1.1.0
        new_version, release_note = create_version_and_release_note(
            db=db,
            release_type="minor",
            title="Версия 1.1.0 - Адаптация для мобильных устройств",
            description="Полная адаптация интерфейса CRM для работы на мобильных телефонах и планшетах. Добавлена автоматизация управления версиями.",
            changes="""Добавлено:
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
- Улучшена работа модальных окон на мобильных""",
            is_published=False,
            is_published_to_partners=False,
            is_important=False,
            created_by_user_id=admin.id,
            update_version_file_flag=True,
        )
        
        print(f"[OK] Версия {new_version} успешно создана!")
        print(f"[OK] Релиз-ноутс ID: {release_note.id}")
        print(f"[OK] Файл app/version.py обновлен")
        print(f"\nДля публикации версии перейдите в админ-панель: /release_notes/{release_note.id}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()

