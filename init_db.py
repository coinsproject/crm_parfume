# Utility to init database roles/permissions and admin
from sqlalchemy.orm import sessionmaker
from app.db import engine, Base
from app.models import Role, User, Permission, RolePermission
from app.services.auth_service import hash_password

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_roles_and_admin():
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)

        base_permissions = [
            ('dashboard.view', 'View dashboard'),
            ('clients.view_all', 'Clients: view all'),
            ('clients.view_own', 'Clients: view own'),
            ('clients.create', 'Clients: create'),
            ('orders.view_all', 'Orders: view all'),
            ('orders.view_own', 'Orders: view own'),
            ('orders.create', 'Orders: create'),
            ('partners.view_all', 'Partners: view all'),
            ('partners.view_own', 'Partners: view own'),
            ('catalog.view_full', 'Catalog: full mode'),
            ('catalog.view_client', 'Catalog: client mode'),
            ('catalog.manage', 'Catalog: manage data'),
        ]

        for key, label in base_permissions:
            if not db.query(Permission).filter(Permission.key == key).first():
                db.add(Permission(key=key, label=label))
        db.commit()

        if db.query(Role).count() == 0:
            roles = [
                {'name': 'ADMIN', 'description': 'Системная роль администратора', 'is_system': True},
                {'name': 'MANAGER', 'description': 'Менеджер', 'is_system': False},
                {'name': 'PARTNER', 'description': 'Партнёр', 'is_system': False},
                {'name': 'VIEWER', 'description': 'Просмотр', 'is_system': False},
            ]
            for role_data in roles:
                db.add(Role(**role_data))
            db.commit()

        admin_role = db.query(Role).filter(Role.name == 'ADMIN').first()

        all_permissions = db.query(Permission).all()
        for perm in all_permissions:
            exists_link = db.query(RolePermission).filter(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == perm.id,
            ).first()
            if not exists_link:
                db.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))
        db.commit()

        if not db.query(User).filter(User.username == 'admin').first():
            admin_user = User(
                username='admin',
                email='admin@perfumecrm.com',
                password_hash=hash_password('admin123'),
                role_id=admin_role.id,
                is_active=True,
                is_2fa_enabled=False,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f'Admin created: {admin_user.username}')
            print('Login: admin')
            print('Password: admin123')
            print('Please change the password after first login!')
    except Exception as e:
        print(f'Error during init: {e}')
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    init_roles_and_admin()
