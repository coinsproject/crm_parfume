"""
Фоновый сервис для создания карточек каталога из прайса
"""
from sqlalchemy.orm import Session
from app.models import PriceProduct
from app.services.price_normalization_service import normalize_price_row
from app.services.catalog_upsert_service import upsert_catalog_from_price
from app.logging_config import price_logger
import json


def create_catalog_items_from_price_batch(upload_id: int, batch_size: int = 100):
    """
    Создает карточки каталога из нормализованных товаров прайса в фоне
    
    Args:
        upload_id: ID загрузки прайса
        batch_size: размер батча для обработки
    """
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        # Получаем товары из этой загрузки, которые нормализованы и имеют group_key
        from app.models import PriceHistory
        
        product_ids = db.query(PriceHistory.price_product_id).filter(
            PriceHistory.price_upload_id == upload_id
        ).distinct().all()
        product_ids = [pid[0] for pid in product_ids]
        
        if not product_ids:
            price_logger.info(f"[CATALOG_BACKGROUND] No products found for upload {upload_id}")
            return
        
        # Берем только нормализованные товары с group_key
        products = db.query(PriceProduct).filter(
            PriceProduct.id.in_(product_ids),
            PriceProduct.ai_status.in_(["ok", "review"]),
            PriceProduct.ai_group_key.isnot(None),
            PriceProduct.ai_group_key != ""
        ).limit(batch_size * 10).all()  # Обрабатываем больше, но батчами
        
        if not products:
            price_logger.info(f"[CATALOG_BACKGROUND] No normalized products found for upload {upload_id}")
            return
        
        created_count = 0
        error_count = 0
        
        for product in products:
            try:
                # Создаем NormalizedResult из полей продукта
                normalized = type('NormalizedResult', (), {
                    'brand': product.norm_brand,
                    'brand_confidence': float(product.brand_confidence or 0),
                    'model_name': product.model_name or "",
                    'series': product.series,
                    'category_path': json.loads(product.category_path_json) if product.category_path_json else None,
                    'attrs': json.loads(product.attrs_json) if product.attrs_json else None,
                    'group_key': product.ai_group_key,
                    'variant_key': product.variant_key,
                    'search_text': product.search_text,
                    'notes': product.normalization_notes,
                    'needs_review': (product.ai_status == "review")
                })()
                
                # Создаем карточку каталога
                catalog_variant = upsert_catalog_from_price(product, normalized, db)
                if catalog_variant:
                    created_count += 1
                
                # Коммитим периодически
                if (created_count + error_count) % batch_size == 0:
                    db.commit()
                    price_logger.info(f"[CATALOG_BACKGROUND] Processed {created_count + error_count} products, created {created_count} catalog items")
                    
            except Exception as e:
                error_count += 1
                price_logger.warning(f"[CATALOG_BACKGROUND] Failed to create catalog for product_id={product.id}: {str(e)[:200]}")
                if error_count % 10 == 0:
                    db.rollback()
        
        db.commit()
        price_logger.info(f"[CATALOG_BACKGROUND] Completed for upload {upload_id}: created {created_count}, errors {error_count}")
        
    except Exception as e:
        price_logger.exception(f"[CATALOG_BACKGROUND] Error processing upload {upload_id}: {e}")
        db.rollback()
    finally:
        db.close()

