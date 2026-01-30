#!/usr/bin/env python3
"""
Скрипт для исправления ролей (перевод на русский) и проверки надбавок партнеров
"""
import sys
from app.db import SessionLocal
from app.models import Role, Partner

def fix_roles_and_markups():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("ИСПРАВЛЕНИЕ РОЛЕЙ И ПРОВЕРКА НАДБАВОК")
        print("=" * 70)
        print()
        
        # 1. Исправление описаний ролей
        print("1. ИСПРАВЛЕНИЕ ОПИСАНИЙ РОЛЕЙ:")
        print("-" * 70)
        
        role_descriptions = {
            "ADMIN": "Системная роль администратора",
            "MANAGER": "Менеджер",
            "PARTNER": "Партнёр",
            "VIEWER": "Просмотр",
        }
        
        updated_count = 0
        for role in db.query(Role).all():
            expected_desc = role_descriptions.get(role.name)
            if expected_desc and role.description != expected_desc:
                print(f"  Обновление роли {role.name}:")
                print(f"    Было: '{role.description or '(нет)'}'")
                print(f"    Стало: '{expected_desc}'")
                role.description = expected_desc
                updated_count += 1
            else:
                print(f"  ✓ Роль {role.name}: описание корректно")
        
        if updated_count > 0:
            db.commit()
            print(f"\n  ✓ Обновлено описаний: {updated_count}")
        else:
            print("\n  ✓ Все описания ролей корректны")
        
        # 2. Проверка надбавок партнеров
        print("\n2. ПРОВЕРКА НАДБАВОК ПАРТНЕРОВ:")
        print("-" * 70)
        
        partners = db.query(Partner).all()
        if not partners:
            print("  ⚠ Партнеры не найдены")
        else:
            partners_without_markup = []
            for partner in partners:
                markup = partner.partner_price_markup_percent
                if markup is None or markup == 0:
                    partners_without_markup.append(partner)
                    print(f"  ⚠ {partner.full_name or partner.name} (ID: {partner.id}): надбавка не установлена")
                else:
                    print(f"  ✓ {partner.full_name or partner.name} (ID: {partner.id}): надбавка {markup}%")
            
            if partners_without_markup:
                print(f"\n  ⚠ Найдено партнеров без надбавки: {len(partners_without_markup)}")
                print("  Для установки надбавки используйте форму редактирования партнера")
        
        # 3. Проверка расчета цен
        print("\n3. ПРОВЕРКА РАСЧЕТА ЦЕН:")
        print("-" * 70)
        
        from app.services.partner_pricing_service import get_partner_pricing_policy, calc_partner_price
        from decimal import Decimal
        
        test_partner = db.query(Partner).filter(
            Partner.partner_price_markup_percent.isnot(None),
            Partner.partner_price_markup_percent > 0
        ).first()
        
        if test_partner:
            policy = get_partner_pricing_policy(db, test_partner.id)
            base_price = Decimal("1000.00")
            partner_price = calc_partner_price(base_price, policy.partner_price_markup_percent)
            
            print(f"  Тестовый партнер: {test_partner.full_name or test_partner.name}")
            print(f"  Надбавка на прайс: {policy.partner_price_markup_percent}%")
            print(f"  Базовая цена: {base_price:.2f} руб.")
            print(f"  Цена для партнера: {partner_price:.2f} руб.")
            print(f"  Разница: {partner_price - base_price:.2f} руб.")
            print("  ✓ Расчет работает корректно")
        else:
            print("  ⚠ Нет партнеров с установленной надбавкой для проверки")
        
        print("\n" + "=" * 70)
        print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    fix_roles_and_markups()

