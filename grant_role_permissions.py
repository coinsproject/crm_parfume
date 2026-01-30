#!/usr/bin/env python3
"""
Скрипт для добавления прав ролям MANAGER, PARTNER, VIEWER
"""
import sys
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission

# Определяем права для каждой роли
ROLE_PERMISSIONS = {
    "MANAGER": [
        "dashboard.view",
        "clients.view_all",
        "clients.create",
        "orders.view_all",
        "orders.create",
        "partners.view_all",
        "catalog.view_full",
        "catalog.manage",
        "prices.view_client",
        "prices.view_cost",
        "prices.view_margin",
        "prices.edit",
        "price.upload",
        "price.search",
    ],
    "PARTNER": [
        "dashboard.view",
        "clients.view_own",
        "clients.create",
        "orders.view_own",
        "orders.create",
        "partners.view_own",
        "catalog.view_client",
        "prices.view_client",
        "prices.view_cost",
        "prices.view_margin",
        "price.search",
    ],
    "VIEWER": [
        "dashboard.view",
        "clients.view_all",
        "orders.view_all",
        "partners.view_all",
        "catalog.view_full",
        "prices.view_client",
        "price.search",
    ],
}

def grant_role_permissions():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("ДОБАВЛЕНИЕ ПРАВ ДЛЯ РОЛЕЙ")
        print("=" * 70)
        print()
        
        for role_name, permission_keys in ROLE_PERMISSIONS.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                print(f"  ⚠ Роль {role_name} не найдена, пропускаем")
                continue
            
            print(f"Роль: {role_name}")
            print("-" * 70)
            
            # Получаем все права
            permissions = {}
            for key in permission_keys:
                perm = db.query(Permission).filter(Permission.key == key).first()
                if perm:
                    permissions[key] = perm
                else:
                    print(f"  ⚠ Право {key} не найдено в базе")
            
            # Проверяем существующие права
            existing_permission_ids = {
                rp.permission_id 
                for rp in db.query(RolePermission).filter(
                    RolePermission.role_id == role.id
                ).all()
            }
            
            added_count = 0
            for key, perm in permissions.items():
                if perm.id not in existing_permission_ids:
                    print(f"  + Добавляем право: {perm.label} ({key})")
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                    added_count += 1
                else:
                    print(f"  ✓ Право уже есть: {perm.label}")
            
            if added_count > 0:
                db.commit()
                print(f"  ✓ Добавлено прав: {added_count}")
            else:
                print(f"  ✓ Все права уже присутствуют")
            print()
        
        # Финальная статистика
        print("=" * 70)
        print("ИТОГОВАЯ СТАТИСТИКА:")
        print("=" * 70)
        for role_name in ROLE_PERMISSIONS.keys():
            role = db.query(Role).filter(Role.name == role_name).first()
            if role:
                perm_count = db.query(RolePermission).filter(
                    RolePermission.role_id == role.id
                ).count()
                print(f"  {role_name}: {perm_count} прав")
        
        print("\n✓ Готово!")
        
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    grant_role_permissions()

