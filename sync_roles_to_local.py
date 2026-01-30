#!/usr/bin/env python3
"""
Скрипт для полной синхронизации ролей с локальной версией
Устанавливает описания, is_system и права точно как в локальной версии
"""
import sys
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission

# Точная конфигурация из локальной версии
LOCAL_ROLE_CONFIG = {
    "ADMIN": {
        "description": "Системная роль администратора",
        "is_system": True,  # ADMIN должен быть системным
        "permissions": [
            "dashboard.view",
            "clients.view_all",
            "clients.view_own",
            "clients.create",
            "orders.view_all",
            "orders.view_own",
            "orders.create",
            "partners.view_all",
            "partners.view_own",
            "catalog.view_full",
            "catalog.view_client",
            "catalog.manage",
            "prices.view_client",
            "prices.view_cost",
            "prices.view_margin",
            "prices.edit",
            "price.upload",
            "price.search",
        ]
    },
    "MANAGER": {
        "description": "Менеджер",
        "is_system": False,  # Несистемная роль
        "permissions": [
            "price.search",
        ]
    },
    "PARTNER": {
        "description": "Партнёр",
        "is_system": False,  # Несистемная роль
        "permissions": [
            "clients.view_own",
            "clients.create",
            "orders.view_own",
            "orders.create",
            "prices.view_client",
            "prices.view_cost",
            "prices.view_margin",
            "price.search",
        ]
    },
    "VIEWER": {
        "description": "Просмотр",
        "is_system": False,  # Несистемная роль
        "permissions": []  # Нет прав
    },
}

def sync_roles_to_local():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("ПОЛНАЯ СИНХРОНИЗАЦИЯ РОЛЕЙ С ЛОКАЛЬНОЙ ВЕРСИЕЙ")
        print("=" * 70)
        print()
        
        for role_name, config in LOCAL_ROLE_CONFIG.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                print(f"  ⚠ Роль {role_name} не найдена, пропускаем")
                continue
            
            print(f"Роль: {role_name}")
            print("-" * 70)
            
            # 1. Обновляем описание
            if role.description != config["description"]:
                print(f"  Описание: '{role.description or '(нет)'}' -> '{config['description']}'")
                role.description = config["description"]
            else:
                print(f"  ✓ Описание корректно: '{config['description']}'")
            
            # 2. Обновляем is_system
            if role.is_system != config["is_system"]:
                print(f"  is_system: {role.is_system} -> {config['is_system']}")
                role.is_system = config["is_system"]
            else:
                print(f"  ✓ is_system корректно: {config['is_system']}")
            
            # 3. Синхронизируем права
            # Получаем текущие права
            current_permission_ids = {
                rp.permission_id 
                for rp in db.query(RolePermission).filter(
                    RolePermission.role_id == role.id
                ).all()
            }
            
            # Получаем нужные права
            needed_permissions = {}
            for perm_key in config["permissions"]:
                perm = db.query(Permission).filter(Permission.key == perm_key).first()
                if perm:
                    needed_permissions[perm_key] = perm
                else:
                    print(f"  ⚠ Право {perm_key} не найдено в базе")
            
            needed_permission_ids = {p.id for p in needed_permissions.values()}
            
            # Удаляем лишние права
            to_remove = current_permission_ids - needed_permission_ids
            if to_remove:
                removed_count = db.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id.in_(to_remove)
                ).delete(synchronize_session=False)
                print(f"  - Удалено лишних прав: {removed_count}")
            
            # Добавляем недостающие права
            to_add = needed_permission_ids - current_permission_ids
            added_count = 0
            for perm_key, perm in needed_permissions.items():
                if perm.id in to_add:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                    print(f"  + Добавлено право: {perm.label} ({perm_key})")
                    added_count += 1
            
            # Сохраняем изменения
            db.commit()
            
            # Финальная проверка
            final_count = db.query(RolePermission).filter(
                RolePermission.role_id == role.id
            ).count()
            expected_count = len(config["permissions"])
            
            if final_count == expected_count:
                print(f"  ✓ Права синхронизированы: {final_count} прав")
            else:
                print(f"  ⚠ Несоответствие: ожидалось {expected_count}, получено {final_count}")
            print()
        
        # Итоговая статистика
        print("=" * 70)
        print("ИТОГОВАЯ СТАТИСТИКА:")
        print("=" * 70)
        for role_name, config in LOCAL_ROLE_CONFIG.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if role:
                perm_count = db.query(RolePermission).filter(
                    RolePermission.role_id == role.id
                ).count()
                status = "✓" if role.description == config["description"] and role.is_system == config["is_system"] and perm_count == len(config["permissions"]) else "⚠"
                print(f"  {status} {role_name}: описание='{role.description}', is_system={role.is_system}, прав={perm_count}")
        
        print("\n✓ Синхронизация завершена!")
        
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    sync_roles_to_local()

