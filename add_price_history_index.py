#!/usr/bin/env python3
"""
Скрипт для добавления индексов к таблице price_history для оптимизации JOIN запросов
"""
from app.db import SessionLocal
import sqlalchemy as sa

def add_indexes():
    db = SessionLocal()
    try:
        print("Creating indexes for price_history table...")
        
        # Составной индекс для JOIN запросов с upload_id
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_history_upload_product ON price_history(price_upload_id, price_product_id)'))
        print("✓ Composite index on (price_upload_id, price_product_id) created")
        
        # Индекс для быстрого поиска по product_id
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_history_product_id ON price_history(price_product_id)'))
        print("✓ Index on price_product_id created")
        
        # Индекс для быстрого поиска по upload_id
        db.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_price_history_upload_id ON price_history(price_upload_id)'))
        print("✓ Index on price_upload_id created")
        
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


