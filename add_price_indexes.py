#!/usr/bin/env python3
"""
Скрипт для добавления индексов к таблице price_products для оптимизации поиска
"""
from app.db import SessionLocal
import sqlalchemy as sa

def add_indexes():
    db = SessionLocal()
    try:
        print("Creating indexes for price_products table...")
        
        # Индексы для быстрого поиска
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_active ON price_products(is_active)'))
        print("✓ Index on is_active created")
        
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_in_stock ON price_products(is_in_stock)'))
        print("✓ Index on is_in_stock created")
        
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_in_pricelist ON price_products(is_in_current_pricelist)'))
        print("✓ Index on is_in_current_pricelist created")
        
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_brand ON price_products(brand)'))
        print("✓ Index on brand created")
        
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_id_desc ON price_products(id DESC)'))
        print("✓ Index on id DESC created")
        
        # Составной индекс для частых запросов
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_products_filter ON price_products(is_active, is_in_stock, is_in_current_pricelist)'))
        print("✓ Composite index on (is_active, is_in_stock, is_in_current_pricelist) created")
        
        db.commit()
        print("\n✅ All indexes created successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_indexes()

