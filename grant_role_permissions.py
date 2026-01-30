#!/usr/bin/env python3
"""
Скрипт для добавления прав ролям MANAGER, PARTNER, VIEWER
"""
import sys
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission

# Определяем права для каждой роли (согласно локальной версии)
ROLE_PERMISSIONS = {
    "MANAGER": [
        "price.search",  # Только поиск по прайсу (как в локальной версии)
    ],
    "PARTNER": [
        "clients.view_own",
        "clients.create",
        "orders.view_own",
        "orders.create",
        "prices.view_client",
        "prices.view_cost",
        "prices.view_margin",
        "price.search",
    ],
    "VIEWER": [
        # Нет прав (как в локальной версии)
    ],
}

def grant_role_permissions():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("СИНХРОНИЗАЦИЯ РОЛЕЙ С ЛОКАЛЬНОЙ ВЕРСИЕЙ")
        print("=" * 70)
        print()
        
        # Сначала делаем роли несистемными (как в локальной версии)
        print("1. УСТАНОВКА is_system = False для MANAGER, PARTNER, VIEWER:")
        print("-" * 70)
        for role_name in ['MANAGER', 'PARTNER', 'VIEWER']:
            role = db.query(Role).filter(Role.name == role_name).first()
            if role:
                if role.is_system:
                    role.is_system = False
                    print(f"  ✓ Роль {role_name}: is_system установлен в False")
                else:
                    print(f"  ✓ Роль {role_name}: уже несистемная")
        db.commit()
        print()
        
        # Теперь добавляем права согласно локальной версии
        print("2. ДОБАВЛЕНИЕ ПРАВ ДЛЯ РОЛЕЙ:")
        print("-" * 70)
        
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

