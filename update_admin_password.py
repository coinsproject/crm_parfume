"""
Скрипт для обновления пароля администратора
"""
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Role
from app.services.auth_service import hash_password


def update_admin_password():
    """
    Обновление пароля администратора
    """
    db: Session = next(get_db())
    
    try:
        # Находим пользователя с именем 'admin'
        admin_user = db.query(User).join(Role).filter(
            User.username == "admin",
            Role.name == "ADMIN"
        ).first()
        
        if not admin_user:
            print("Администратор не найден. Возможно, сначала нужно запустить init_db.py")
            return
        
        # Устанавливаем новый пароль
        new_password = "admin123"  # В реальном приложении лучше генерировать или брать из env
        hashed_password = hash_password(new_password)
        
        admin_user.password_hash = hashed_password
        db.commit()
        
        print(f"Пароль для администратора успешно обновлен!")
        print(f"Логин: admin")
        print(f"Новый пароль: {new_password}")
        print("РЕКОМЕНДАЦИЯ: После первого входа измените пароль на более безопасный!")
        
    except Exception as e:
        print(f"Ошибка при обновлении пароля администратора: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    update_admin_password()