#!/usr/bin/env python3
"""
Скрипт для установки надбавки партнеру напрямую в БД
Использование: python set_partner_markup.py <partner_id> <markup_percent>
"""
import sys
from app.db import SessionLocal
from app.models import Partner
from decimal import Decimal

def set_partner_markup(partner_id: int, markup_percent: float):
    db = SessionLocal()
    try:
        partner = db.query(Partner).filter(Partner.id == partner_id).first()
        if not partner:
            print(f"✗ Партнер с ID {partner_id} не найден")
            return False
        
        markup = Decimal(str(markup_percent)).quantize(Decimal("0.01"))
        
        print(f"Партнер: {partner.full_name or partner.name} (ID: {partner.id})")
        print(f"Текущая надбавка: {partner.partner_price_markup_percent or 0}%")
        print(f"Устанавливаем надбавку: {markup}%")
        
        partner.partner_price_markup_percent = markup
        db.commit()
        db.refresh(partner)
        
        print(f"✓ Надбавка установлена: {partner.partner_price_markup_percent}%")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Использование: python set_partner_markup.py <partner_id> <markup_percent>")
        print("Пример: python set_partner_markup.py 1 3.0")
        sys.exit(1)
    
    try:
        partner_id = int(sys.argv[1])
        markup_percent = float(sys.argv[2])
        set_partner_markup(partner_id, markup_percent)
    except ValueError:
        print("✗ Ошибка: partner_id должен быть числом, markup_percent - числом с точкой")
        sys.exit(1)

