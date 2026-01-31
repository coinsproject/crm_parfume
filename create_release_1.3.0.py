#!/usr/bin/env python
"""Скрипт для создания релиз-ноутса версии 1.3.0"""
import sys
import os
from datetime import date

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal
from app.services.version_service import create_version_and_release_note, update_version_file
from app.models import User

def main():
    """Создает новую версию 1.3.0 с описанием изменений"""
    db = SessionLocal()
    
    try:
        # Получаем администратора
        admin = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).first()
        if not admin:
            print("Ошибка: администратор не найден")
            return
        
        # Создаем версию 1.3.0
        new_version, release_note = create_version_and_release_note(
            db=db,
            release_type="minor",
            title="Версия 1.3.0 - Email и Telegram уведомления, русификация прав",
            description="Добавлена система уведомлений администраторов по email и Telegram при регистрации новых пользователей. Полная русификация прав доступа. Улучшения в скрипте обновления.",
            changes="""Добавлено:
- Система email уведомлений для администраторов
  * Поддержка SMTP (Gmail, Yandex, Mail.ru и другие)
  * HTML и plain text версии писем
  * Автоматическая отправка при регистрации партнёров
- Система Telegram уведомлений для администраторов
  * Интеграция с Telegram Bot API
  * Поддержка нескольких администраторов
  * HTML форматирование сообщений
- Полная русификация прав доступа
  * Все права теперь отображаются на русском языке
  * Автоматическое обновление существующих прав
- Документация по настройке уведомлений (NOTIFICATIONS_SETUP.md)

Изменено:
- Обновлен скрипт fix_permissions.py для автоматической русификации прав
- Обновлен init_db.py для использования русских названий прав при инициализации
- Улучшен скрипт full_update.sh для автоматической обработки локальных изменений Git
- Добавлены переменные окружения для настройки email и Telegram

Исправлено:
- Проблема с конфликтами локальных изменений при обновлении на сервере
- Английские названия прав теперь автоматически обновляются на русские
- Улучшена обработка ошибок при отправке уведомлений""",
            is_published=False,
            is_published_to_partners=False,
            is_important=True,  # Важное обновление
            created_by_user_id=admin.id,
            update_version_file_flag=True,
        )
        
        print(f"[OK] Версия {new_version} успешно создана!")
        print(f"[OK] Релиз-ноутс ID: {release_note.id}")
        print(f"[OK] Файл app/version.py обновлен")
        print(f"\nДля публикации версии перейдите в админ-панель: /release_notes/{release_note.id}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()

