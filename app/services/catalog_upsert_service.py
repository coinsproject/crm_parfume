"""
Сервис для создания/обновления каталога из нормализованного прайса
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from app.models import PriceProduct, CatalogItem, CatalogVariant
from app.services.price_normalization_service import NormalizedResult


def _json_loads(text: Optional[str]) -> Any:
    """Безопасная загрузка JSON из текста"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(obj: Any) -> Optional[str]:
    """Безопасная сериализация в JSON"""
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def upsert_catalog_from_price(price_product: PriceProduct, normalized: NormalizedResult, db: Session) -> Optional[CatalogVariant]:
    """
    Создаёт или обновляет каталог на основе нормализованного прайса
    
    Args:
        price_product: объект PriceProduct из БД
        normalized: результат нормализации
        db: сессия БД
    
    Returns:
        CatalogVariant - созданный или обновлённый вариант, или None в случае ошибки
    """
    if not normalized or not normalized.group_key:
        # Если нет normalized или group_key, не можем создать каталог
        return None
    
    # Если нет price_product или его ID, не можем создать вариант
    if not price_product or not price_product.id:
        return None
    
    # 1. Находим или создаём CatalogItem по group_key
    catalog_item = db.query(CatalogItem).filter(CatalogItem.group_key == normalized.group_key).first()
    
    if not catalog_item:
        # Создаём новую карточку
        try:
            # Проверяем еще раз (на случай параллельного создания)
            catalog_item = db.query(CatalogItem).filter(CatalogItem.group_key == normalized.group_key).first()
            if not catalog_item:
                # Используем прямой SQL для избежания конфликтов в identity map
                display_name = f"{normalized.brand} {normalized.model_name}".strip() if (normalized.brand and normalized.model_name) else (normalized.model_name or normalized.brand or "Unknown")
                tags_json = json.dumps({"series": normalized.series}) if normalized.series else None
                
                result = db.execute(
                    text("""
                        INSERT INTO catalog_items (group_key, brand, name, display_name, visible, in_stock, tags, created_at, updated_at)
                        VALUES (:group_key, :brand, :name, :display_name, :visible, :in_stock, :tags, :created_at, :updated_at)
                    """),
                    {
                        "group_key": normalized.group_key,
                        "brand": normalized.brand if normalized.brand else None,
                        "name": normalized.model_name if normalized.model_name else None,
                        "display_name": display_name,
                        "visible": True,
                        "in_stock": price_product.is_in_stock if price_product and hasattr(price_product, 'is_in_stock') else False,
                        "tags": tags_json,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                )
                db.flush()
                
                # Загружаем созданный объект из БД
                catalog_item = db.query(CatalogItem).filter(CatalogItem.group_key == normalized.group_key).first()
        except Exception as create_error:
            # Если не удалось создать catalog_item, проверяем, не был ли он создан параллельно
            try:
                db.rollback()
                # Очищаем identity map для CatalogItem перед повторным запросом
                db.expire_all()
                catalog_item = db.query(CatalogItem).filter(CatalogItem.group_key == normalized.group_key).first()
                if not catalog_item:
                    return None
            except:
                return None
    else:
        # Обновляем существующую карточку
        if normalized.brand and not catalog_item.brand:
            catalog_item.brand = normalized.brand
        if normalized.model_name and not catalog_item.name:
            catalog_item.name = normalized.model_name
        catalog_item.in_stock = catalog_item.in_stock or (price_product.is_in_stock if price_product else False)
    
    # 2. Находим или создаём CatalogVariant
    variant = None
    
    # Сначала проверяем, есть ли уже вариант для этого price_product_id (это приоритетно из-за UNIQUE constraint)
    if price_product and price_product.id:
        existing_variant = db.query(CatalogVariant).filter(
            CatalogVariant.price_product_id == price_product.id
        ).first()
        if existing_variant:
            variant = existing_variant
    
    # Если не нашли по price_product_id, ищем по variant_key
    if not variant and normalized.variant_key:
        variant = db.query(CatalogVariant).filter(CatalogVariant.variant_key == normalized.variant_key).first()
    
    if not variant:
        # Создаём новый вариант
        variant = CatalogVariant(
            catalog_item_id=catalog_item.id,
            price_product_id=price_product.id if price_product else None,
            variant_key=normalized.variant_key,
            format=normalized.attrs.get('format', 'full'),
            gender=normalized.attrs.get('gender'),
            in_stock=price_product.is_in_stock if price_product else False,
        )
        
        # Заполняем объёмы
        if 'volume_ml' in normalized.attrs:
            variant.volume_value = normalized.attrs['volume_ml']
            variant.volume_unit = 'мл'
        elif 'volumes_ml' in normalized.attrs:
            variant.volumes_ml = _json_dumps(normalized.attrs['volumes_ml'])
            variant.total_ml = normalized.attrs.get('total_ml')
        
        # Заполняем остальные атрибуты
        if 'color' in normalized.attrs:
            variant.color = normalized.attrs['color']
        if 'size_cm' in normalized.attrs:
            variant.size_cm = _json_dumps(normalized.attrs['size_cm'])
        if 'pack' in normalized.attrs:
            variant.pack = _json_dumps(normalized.attrs['pack'])
        if 'density_raw' in normalized.attrs:
            variant.density_raw = normalized.attrs['density_raw']
        if 'features' in normalized.attrs:
            variant.features = _json_dumps(normalized.attrs['features'])
        
        # Legacy поля
        variant.is_tester = normalized.attrs.get('format') == 'tester'
        
        try:
            db.add(variant)
            db.flush()
        except IntegrityError as ie:
            # Если возникла ошибка UNIQUE constraint на price_product_id,
            # значит вариант для этого продукта уже существует
            error_str = str(ie)
            if "price_product_id" in error_str.lower() or "unique" in error_str.lower():
                # НЕ делаем rollback - это откатит все изменения продукта!
                # Просто удаляем вариант из сессии и находим существующий
                db.expunge(variant)
                
                # Находим существующий вариант и обновляем его
                if price_product and price_product.id:
                    existing_variant = db.query(CatalogVariant).filter(
                        CatalogVariant.price_product_id == price_product.id
                    ).first()
                    if existing_variant:
                        variant = existing_variant
                        # Переходим к обновлению существующего варианта (код ниже)
                    else:
                        # Неожиданная ситуация - возвращаем None, чтобы не прерывать загрузку
                        return None
                else:
                    return None
            else:
                # Другая ошибка целостности - удаляем из сессии и возвращаем None
                db.expunge(variant)
                return None
    
    # Обновляем существующий вариант (если он был найден или создан, или восстановлен после ошибки)
    if variant:
        try:
            if price_product:
                # Обновляем price_product_id только если он еще не установлен
                if not variant.price_product_id or variant.price_product_id != price_product.id:
                    variant.price_product_id = price_product.id
                variant.in_stock = price_product.is_in_stock
            
            # Обновляем catalog_item_id если изменился
            if variant.catalog_item_id != catalog_item.id:
                variant.catalog_item_id = catalog_item.id
            
            # Обновляем variant_key если он изменился
            if normalized.variant_key and variant.variant_key != normalized.variant_key:
                variant.variant_key = normalized.variant_key
            
            # Обновляем атрибуты, если они изменились
            if 'format' in normalized.attrs:
                variant.format = normalized.attrs['format']
                variant.is_tester = normalized.attrs['format'] == 'tester'
            
            if 'volume_ml' in normalized.attrs:
                variant.volume_value = normalized.attrs['volume_ml']
                variant.volume_unit = 'мл'
            elif 'volumes_ml' in normalized.attrs:
                variant.volumes_ml = _json_dumps(normalized.attrs['volumes_ml'])
                variant.total_ml = normalized.attrs.get('total_ml')
            
            if 'color' in normalized.attrs:
                variant.color = normalized.attrs['color']
            if 'size_cm' in normalized.attrs:
                variant.size_cm = _json_dumps(normalized.attrs['size_cm'])
            if 'pack' in normalized.attrs:
                variant.pack = _json_dumps(normalized.attrs['pack'])
            if 'density_raw' in normalized.attrs:
                variant.density_raw = normalized.attrs['density_raw']
            if 'features' in normalized.attrs:
                variant.features = _json_dumps(normalized.attrs['features'])
            
            # Сохраняем изменения
            db.add(variant)
            db.flush()
        except IntegrityError as update_error:
            # Если при обновлении возникла ошибка целостности, просто возвращаем None
            # чтобы не прерывать загрузку прайса
            db.rollback()
            return None
        except Exception as update_error:
            # Любая другая ошибка - логируем и возвращаем None
            db.rollback()
            return None
    
    return variant



