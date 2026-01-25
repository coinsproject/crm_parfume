"""Сервис для автоматического управления версиями и релиз-ноутсами"""
import re
from typing import Optional, Dict, Any
from datetime import date, datetime
from sqlalchemy.orm import Session

from app.models import ReleaseNote, User
from app.version import __version__


def parse_version(version_str: str) -> tuple:
    """Парсит версию в формате MAJOR.MINOR.PATCH"""
    try:
        parts = version_str.split('.')
        if len(parts) != 3:
            raise ValueError("Версия должна быть в формате MAJOR.MINOR.PATCH")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as e:
        raise ValueError(f"Неверный формат версии: {e}")


def increment_version(current_version: str, release_type: str = "minor") -> str:
    """Увеличивает версию в зависимости от типа релиза"""
    major, minor, patch = parse_version(current_version)
    
    if release_type == "major":
        return f"{major + 1}.0.0"
    elif release_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif release_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Неизвестный тип релиза: {release_type}")


def get_latest_release_note(db: Session) -> Optional[ReleaseNote]:
    """Получает последний релиз-ноутс"""
    return db.query(ReleaseNote).order_by(ReleaseNote.release_date.desc()).first()


def get_next_version(db: Session, release_type: str = "minor") -> str:
    """Получает следующую версию на основе последнего релиз-ноутса или текущей версии"""
    latest_note = get_latest_release_note(db)
    
    if latest_note:
        # Используем версию из последнего релиз-ноутса
        try:
            return increment_version(latest_note.version, release_type)
        except ValueError:
            # Если версия в неправильном формате, используем текущую версию из кода
            pass
    
    # Используем текущую версию из кода
    return increment_version(__version__, release_type)


def create_release_note(
    db: Session,
    version: str,
    title: str,
    description: Optional[str] = None,
    release_type: str = "minor",
    changes: Optional[str] = None,
    is_published: bool = False,
    is_published_to_partners: bool = False,
    is_important: bool = False,
    max_partner_views: Optional[int] = None,
    created_by_user_id: Optional[int] = None,
    release_date: Optional[date] = None,
) -> ReleaseNote:
    """Создает новый релиз-ноутс"""
    # Проверяем, что версия уникальна
    existing = db.query(ReleaseNote).filter(ReleaseNote.version == version).first()
    if existing:
        raise ValueError(f"Версия {version} уже существует")
    
    if release_date is None:
        release_date = date.today()
    
    release_note = ReleaseNote(
        version=version,
        title=title,
        description=description,
        release_type=release_type,
        release_date=release_date,
        changes=changes,
        is_published=is_published,
        is_published_to_partners=is_published_to_partners,
        is_important=is_important,
        max_partner_views=max_partner_views,
        created_by_user_id=created_by_user_id,
    )
    
    db.add(release_note)
    db.commit()
    db.refresh(release_note)
    
    return release_note


def update_version_file(new_version: str, file_path: str = "app/version.py") -> None:
    """Обновляет файл version.py с новой версией"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Заменяем версию
        pattern = r'__version__\s*=\s*["\']([^"\']+)["\']'
        new_content = re.sub(pattern, f'__version__ = "{new_version}"', content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    except Exception as e:
        raise ValueError(f"Ошибка при обновлении файла версии: {e}")


def create_version_and_release_note(
    db: Session,
    release_type: str = "minor",
    title: Optional[str] = None,
    description: Optional[str] = None,
    changes: Optional[str] = None,
    is_published: bool = False,
    is_published_to_partners: bool = False,
    is_important: bool = False,
    max_partner_views: Optional[int] = None,
    created_by_user_id: Optional[int] = None,
    update_version_file_flag: bool = True,
) -> tuple[str, ReleaseNote]:
    """Создает новую версию и релиз-ноутс автоматически"""
    # Получаем следующую версию
    new_version = get_next_version(db, release_type)
    
    # Если заголовок не указан, создаем автоматический
    if title is None:
        title = f"Версия {new_version}"
    
    # Создаем релиз-ноутс
    release_note = create_release_note(
        db=db,
        version=new_version,
        title=title,
        description=description,
        release_type=release_type,
        changes=changes,
        is_published=is_published,
        is_published_to_partners=is_published_to_partners,
        is_important=is_important,
        max_partner_views=max_partner_views,
        created_by_user_id=created_by_user_id,
    )
    
    # Обновляем файл version.py
    if update_version_file_flag:
        try:
            update_version_file(new_version)
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение
            print(f"Предупреждение: не удалось обновить файл версии: {e}")
    
    return new_version, release_note

