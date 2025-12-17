"""
Скрипт для создания первого администратора при отсутствии в системе
"""
import os
from sqlalchemy.orm import sessionmaker
from app.db import engine, Base
from app.models import User, Role
from app.services.auth_service import hash_password

def create_first_admin():
    """Создание первого администратора, если в системе нет ни одного администратора"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже администраторы в системе
        admin_exists = db.query(User).join(Role).filter(Role.name == "ADMIN").first()
        
        if admin_exists:
            print("Администратор уже существует в системе.")
            return
        
        # Проверяем, существуют ли роли, и если нет - создаем их
        roles = ["ADMIN", "MANAGER", "PARTNER", "VIEWER"]
        for role_name in roles:
            existing_role = db.query(Role).filter(Role.name == role_name).first()
            if not existing_role:
                role = Role(name=role_name, is_system=True)
                db.add(role)
        
        db.commit()
        
        # Получаем роль ADMIN
        admin_role = db.query(Role).filter(Role.name == "ADMIN").first()
        
        # Получаем данные из переменных окружения или используем значения по умолчанию
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@perfumecrm.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        
        # Создаем пользователя-администратора
        admin_user = User(
            username=admin_username,
            email=admin_email,
            password_hash=hash_password(admin_password),
            role_id=admin_role.id,
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"Администратор создан:")
        print(f"  Логин: {admin_username}")
        print(f"  Email: {admin_email}")
        print(f"  Пароль: {admin_password}")
        print("РЕКОМЕНДАЦИЯ: После первого входа измените пароль на более безопасный!")
        
    except Exception as e:
        print(f"Ошибка при создании администратора: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Создаем таблицы, если они не существуют
    Base.metadata.create_all(bind=engine)
    create_first_admin()