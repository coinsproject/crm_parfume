#!/usr/bin/env python3
"""
Скрипт для проверки и добавления недостающих прав в базе данных
"""
import sys
from app.db import SessionLocal
from app.models import Permission, Role, RolePermission

# Все права, которые должны быть в системе
ALL_PERMISSIONS = [
    # Базовые права (004_add_permissions_and_rbac_tables)
    ("dashboard.view", "Просмотр дашборда"),
    ("clients.view_all", "Клиенты: просмотр всех"),
    ("clients.view_own", "Клиенты: просмотр своих"),
    ("clients.create", "Клиенты: создание"),
    ("orders.view_all", "Заказы: просмотр всех"),
    ("orders.view_own", "Заказы: просмотр своих"),
    ("orders.create", "Заказы: создание"),
    ("partners.view_all", "Партнёры: просмотр всех"),
    ("partners.view_own", "Партнёры: просмотр своих"),
    ("catalog.view_full", "Каталог: полный режим"),
    ("catalog.view_client", "Каталог: клиентский режим"),
    ("catalog.manage", "Каталог: управление данными"),
    # Права для работы с ценами (008_add_price_permissions)
    ("prices.view_client", "Просмотр цен для клиента"),
    ("prices.view_cost", "Просмотр себестоимости/закупа"),
    ("prices.view_margin", "Просмотр маржи"),
    ("prices.edit", "Редактирование цен"),
    # Право загрузки прайса (010_add_price_uploads_and_permission)
    ("price.upload", "Загрузка прайса"),
    # Право поиска по прайсу (011_add_price_search_permission)
    ("price.search", "Поиск по прайсу"),
]

def fix_permissions():
    db = SessionLocal()
    try:
        print("=== Проверка прав в базе данных ===\n")
        
        # Получаем существующие права
        existing_permissions = {p.key: p for p in db.query(Permission).all()}
        print(f"Найдено прав в базе: {len(existing_permissions)}")
        
        # Проверяем и добавляем недостающие права, обновляем существующие
        added_count = 0
        updated_count = 0
        for key, label in ALL_PERMISSIONS:
            if key not in existing_permissions:
                print(f"  + Добавляем право: {key} ({label})")
                new_perm = Permission(key=key, label=label)
                db.add(new_perm)
                added_count += 1
            else:
                # Обновляем название права, если оно отличается
                existing_perm = existing_permissions[key]
                if existing_perm.label != label:
                    print(f"  ↻ Обновляем название права: {key} ('{existing_perm.label}' → '{label}')")
                    existing_perm.label = label
                    updated_count += 1
                else:
                    print(f"  ✓ Право уже существует: {key}")
        
        if added_count > 0 or updated_count > 0:
            db.commit()
            if added_count > 0:
                print(f"\n✓ Добавлено {added_count} новых прав")
            if updated_count > 0:
                print(f"✓ Обновлено {updated_count} названий прав")
        else:
            print("\n✓ Все права уже присутствуют в базе с корректными названиями")
        
        # Проверяем роли и их права
        print("\n=== Проверка ролей и их прав ===\n")
        roles = db.query(Role).all()
        for role in roles:
            role_perms = db.query(RolePermission).filter(
                RolePermission.role_id == role.id
            ).count()
            print(f"  {role.name}: {role_perms} прав")
        
        # Проверяем, что у ADMIN есть все права
        print("\n=== Проверка прав ADMIN ===\n")
        admin_role = db.query(Role).filter(Role.name == "ADMIN").first()
        if admin_role:
            all_permissions = db.query(Permission).all()
            admin_permission_ids = {
                rp.permission_id 
                for rp in db.query(RolePermission).filter(
                    RolePermission.role_id == admin_role.id
                ).all()
            }
            
            missing_for_admin = []
            for perm in all_permissions:
                if perm.id not in admin_permission_ids:
                    missing_for_admin.append(perm.key)
                    print(f"  + Добавляем право {perm.key} для ADMIN")
                    db.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))
            
            if missing_for_admin:
                db.commit()
                print(f"\n✓ Добавлено {len(missing_for_admin)} прав для ADMIN")
            else:
                print("  ✓ У ADMIN есть все права")
        
        # Финальная статистика
        print("\n=== Финальная статистика ===\n")
        total_permissions = db.query(Permission).count()
        total_role_permissions = db.query(RolePermission).count()
        print(f"Всего прав: {total_permissions}")
        print(f"Всего связей роли-права: {total_role_permissions}")
        
        print("\n✓ Проверка завершена успешно!")
        
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    fix_permissions()

