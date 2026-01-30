#!/usr/bin/env python3
"""
Скрипт для сравнения локальной и серверной версий
Проверяет роли, права, настройки партнеров и структуру БД
"""
import sys
from app.db import SessionLocal
from app.models import Role, Permission, RolePermission, Partner, User
from sqlalchemy import inspect
from decimal import Decimal

def compare_versions():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("СВЕРКА ВЕРСИЙ: ЛОКАЛЬНАЯ vs СЕРВЕРНАЯ")
        print("=" * 70)
        print()
        
        # 1. Проверка ролей
        print("1. РОЛИ В БАЗЕ ДАННЫХ:")
        print("-" * 70)
        roles = db.query(Role).order_by(Role.id).all()
        expected_roles = {
            1: {"name": "ADMIN", "description": "Системная роль администратора"},
            2: {"name": "MANAGER", "description": "Менеджер"},
            3: {"name": "PARTNER", "description": "Партнёр"},
            4: {"name": "VIEWER", "description": "Просмотр"},
        }
        
        for role in roles:
            expected = expected_roles.get(role.id, {})
            status = "✓" if role.description == expected.get("description") else "⚠"
            print(f"  {status} ID {role.id}: {role.name}")
            print(f"     Описание: '{role.description or '(нет)'}'")
            if role.description != expected.get("description"):
                print(f"     Ожидалось: '{expected.get('description', 'неизвестно')}'")
            perm_count = db.query(RolePermission).filter(RolePermission.role_id == role.id).count()
            print(f"     Прав: {perm_count}")
            print()
        
        # 2. Проверка прав
        print("\n2. ПРАВА ДОСТУПА:")
        print("-" * 70)
        permissions = db.query(Permission).order_by(Permission.key).all()
        expected_permissions = [
            "dashboard.view",
            "clients.view_all", "clients.view_own", "clients.create",
            "orders.view_all", "orders.view_own", "orders.create",
            "partners.view_all", "partners.view_own",
            "catalog.view_full", "catalog.view_client", "catalog.manage",
            "prices.view_client", "prices.view_cost", "prices.view_margin", "prices.edit",
            "price.upload", "price.search",
        ]
        
        found_keys = {p.key for p in permissions}
        missing = set(expected_permissions) - found_keys
        extra = found_keys - set(expected_permissions)
        
        print(f"  Всего прав в базе: {len(permissions)}")
        print(f"  Ожидается: {len(expected_permissions)}")
        
        if missing:
            print(f"  ⚠ Отсутствуют права: {', '.join(sorted(missing))}")
        if extra:
            print(f"  ⚠ Лишние права: {', '.join(sorted(extra))}")
        if not missing and not extra:
            print("  ✓ Все права присутствуют")
        
        # 3. Проверка партнеров и надбавок
        print("\n3. ПАРТНЕРЫ И НАДБАВКИ:")
        print("-" * 70)
        partners = db.query(Partner).all()
        if not partners:
            print("  ⚠ Партнеры не найдены")
        else:
            for partner in partners:
                print(f"  Партнер: {partner.full_name or partner.name} (ID: {partner.id})")
                
                # Проверка надбавки на прайс
                markup = partner.partner_price_markup_percent
                if markup is None or markup == 0:
                    print(f"    ⚠ Надбавка на прайс: {markup or 0}% (не установлена)")
                else:
                    print(f"    ✓ Надбавка на прайс: {markup}%")
                
                print(f"    Наценка админа: {partner.admin_markup_percent or 0}%")
                print(f"    Наценка партнера по умолчанию: {partner.partner_default_markup_percent or 0}%")
                print(f"    Макс. наценка партнера: {partner.max_partner_markup_percent or 'не ограничено'}%")
                print()
        
        # 4. Проверка структуры БД
        print("\n4. СТРУКТУРА БАЗЫ ДАННЫХ:")
        print("-" * 70)
        inspector = inspect(db.bind)
        
        # Проверка колонок в partners
        partner_columns = {col['name'] for col in inspector.get_columns('partners')}
        required_columns = {
            'partner_price_markup_percent',
            'admin_markup_percent',
            'partner_default_markup_percent',
            'max_partner_markup_percent'
        }
        
        missing_cols = required_columns - partner_columns
        if missing_cols:
            print(f"  ⚠ Отсутствуют колонки в partners: {', '.join(missing_cols)}")
        else:
            print("  ✓ Все необходимые колонки присутствуют")
        
        # 5. Проверка пользователей-партнеров
        print("\n5. ПОЛЬЗОВАТЕЛИ-ПАРТНЕРЫ:")
        print("-" * 70)
        partner_users = db.query(User).filter(User.partner_id.isnot(None), User.is_active == True).all()
        if partner_users:
            for user in partner_users:
                partner = db.query(Partner).filter(Partner.id == user.partner_id).first()
                if partner:
                    markup = partner.partner_price_markup_percent
                    status = "✓" if markup and markup > 0 else "⚠"
                    print(f"  {status} {user.username} -> Партнер: {partner.full_name or partner.name}")
                    print(f"     Надбавка на прайс: {markup or 0}%")
        else:
            print("  Нет активных пользователей-партнеров")
        
        # 6. Пример расчета цены
        print("\n6. ПРОВЕРКА РАСЧЕТА ЦЕН:")
        print("-" * 70)
        test_partner = db.query(Partner).filter(
            Partner.partner_price_markup_percent.isnot(None),
            Partner.partner_price_markup_percent > 0
        ).first()
        
        if test_partner:
            base_price = Decimal("1000.00")
            markup = Decimal(str(test_partner.partner_price_markup_percent))
            partner_price = base_price * (Decimal("1") + markup / Decimal("100"))
            
            print(f"  Тестовый партнер: {test_partner.full_name or test_partner.name}")
            print(f"  Надбавка: {markup}%")
            print(f"  Базовая цена (price_1): {base_price:.2f} руб.")
            print(f"  Цена для партнера (price_2): {partner_price:.2f} руб.")
            print(f"  Разница: {partner_price - base_price:.2f} руб.")
            print("  ✓ Расчет работает корректно")
        else:
            print("  ⚠ Нет партнеров с установленной надбавкой для теста")
        
        # 7. Итоговая сводка
        print("\n" + "=" * 70)
        print("ИТОГОВАЯ СВОДКА:")
        print("=" * 70)
        
        issues = []
        if missing:
            issues.append(f"Отсутствуют права: {len(missing)}")
        if missing_cols:
            issues.append(f"Отсутствуют колонки: {len(missing_cols)}")
        if not test_partner:
            issues.append("Нет партнеров с надбавкой")
        
        if issues:
            print("  ⚠ Обнаружены проблемы:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  ✓ Все проверки пройдены успешно!")
        
        print()
        
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    compare_versions()

