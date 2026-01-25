"""
Роуты для раздела нормализации
Объединяет нормализацию, бренды, справочники и ревью
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
from typing import Optional
import json
import httpx

from app.db import get_db
from app.models import User, PriceProduct, Brand, BrandAlias
from app.services.auth_service import require_roles, require_permission
from app.services.key_normalization import normalize_key
from app.services.catalog_upsert_service import upsert_catalog_from_price
from app.logging_config import price_logger

router = APIRouter(prefix="/normalization", tags=["normalization"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def normalization_index(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Главная страница раздела нормализации с вкладками"""
    return templates.TemplateResponse(
        "normalization_index.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "normalization",
        },
    )


@router.get("/review", response_class=HTMLResponse)
async def normalization_review_page(
    request: Request,
    page: int = 1,
    status_filter: str = "review",  # review|error|all
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    """Страница ревью нормализации прайса"""
    page = max(1, page)
    per_page = 50
    
    query = db.query(PriceProduct).filter(PriceProduct.is_active.is_(True))
    
    if status_filter == "review":
        query = query.filter(PriceProduct.ai_status == "review")
    elif status_filter == "error":
        query = query.filter(PriceProduct.ai_status == "error")
    elif status_filter == "all":
        query = query.filter(PriceProduct.ai_status.in_(["review", "error"]))
    else:
        query = query.filter(PriceProduct.ai_status == "review")
    
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    
    products = (
        query.order_by(PriceProduct.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    
    # Получаем список брендов для выпадающего списка
    brands = db.query(Brand).order_by(Brand.name_canonical).all()
    
    return templates.TemplateResponse(
        "price_normalization_review.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "normalization",
            "products": products,
            "brands": brands,
            "page": page,
            "pages": pages,
            "total": total,
            "per_page": per_page,
            "status_filter": status_filter,
        },
    )


def _extract_brand_alias_from_raw(raw_name: str, model_name: Optional[str] = None) -> str:
    """
    Извлекает кандидата алиаса бренда из raw_name.
    Берет часть строки от начала до начала модели или до стоп-слов.
    """
    if not raw_name:
        return ""
    
    import re
    raw_name = raw_name.strip()
    
    # Стоп-слова для определения конца названия бренда
    stop_words = {
        'унисекс', 'женск', 'женский', 'мужск', 'мужской',
        'парф', 'парфюмерная', 'туалет', 'туалетная', 'вода',
        'мл', 'ml', 'г', 'гр', 'g', 'gr',
        'тестер', '(тестер)', 'отливант', 'пробник', 'sample',
        'духи', 'edp', 'edt', 'eau', 'de', 'parfum', 'toilette',
        'миниатюра', 'mini', 'decant', 'for', 'women', 'men'
    }
    
    # Если есть > → всё до первого >
    if '>' in raw_name:
        parts = raw_name.split('>', 1)
        candidate = parts[0].strip()
        if candidate:
            return candidate
    
    # Если есть model_name, пытаемся найти его в raw_name и взять всё до него
    if model_name and model_name.strip():
        model_lower = model_name.strip().lower()
        raw_lower = raw_name.lower()
        
        # Ищем модель в raw_name (может быть с разным регистром)
        model_pos = raw_lower.find(model_lower)
        if model_pos > 0:
            # Берем часть до модели
            candidate = raw_name[:model_pos].strip()
            # Очищаем от лишних символов
            candidate = re.sub(r'[^\w&\-\.\s]+$', '', candidate).strip()
            if candidate and len(candidate) >= 2:
                return candidate
    
    # Иначе берем первые 2-5 слов до стоп-слов
    words = raw_name.split()
    
    # Ищем позицию первого стоп-слова
    stop_pos = None
    for i, word in enumerate(words):
        word_lower = word.lower().strip('.,;:()[]{}')
        if word_lower in stop_words:
            stop_pos = i
            break
    
    # Берем от 2 до 5 слов до стоп-слова (или все слова, если стоп-слов нет)
    if stop_pos is not None:
        max_words = min(5, stop_pos)
    else:
        max_words = min(5, len(words))
    
    # Минимум 2 слова для многословных брендов
    if max_words < 2:
        max_words = min(2, len(words))
    
    if max_words == 0:
        return ""
    
    candidate_words = words[:max_words]
    candidate = ' '.join(candidate_words).strip()
    
    # Очищаем от лишних символов в начале/конце
    candidate = re.sub(r'^[^\w&\-\.]+|[^\w&\-\.]+$', '', candidate)
    
    return candidate if candidate and len(candidate) >= 2 else ""


@router.post("/search-fragella/{product_id}", response_class=JSONResponse)
async def search_fragella_for_product(
    product_id: int,
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    """Поиск продукта через Fragella API для автоматического заполнения"""
    product = db.query(PriceProduct).filter(PriceProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    try:
        from app.services.fragella_client import FragellaClient
        client = FragellaClient()
        
        if not client.enabled or not client.api_key:
            return {
                "success": False,
                "error": "Fragella API не настроен"
            }
        
        # Ищем по исходному названию
        search_query = product.raw_name or product.product_name or ""
        if not search_query:
            return {
                "success": False,
                "error": "Нет названия для поиска"
            }
        
        # Выполняем поиск
        try:
            results = await client.search_fragrances(search_query, limit=5, db=db)
        except RuntimeError as rate_error:
            if "limit exceeded" in str(rate_error).lower():
                return {
                    "success": False,
                    "error": "Превышен дневной лимит запросов к Fragella API"
                }
            raise
        except httpx.HTTPStatusError as http_error:
            return {
                "success": False,
                "error": f"Ошибка HTTP {http_error.response.status_code}: {http_error.response.text[:200]}"
            }
        except httpx.RequestError as req_error:
            return {
                "success": False,
                "error": f"Ошибка подключения к Fragella API: {str(req_error)[:200]}"
            }
        
        if not results or len(results) == 0:
            return {
                "success": False,
                "error": "Ничего не найдено в Fragella"
            }
        
        # Формируем список кандидатов
        candidates = []
        for result in results[:5]:
            brand = result.get("Brand") or result.get("brand") or ""
            name = result.get("Name") or result.get("name") or ""
            candidates.append({
                "brand": brand,
                "name": name,
                "full_name": f"{brand} {name}".strip()
            })
        
        return {
            "success": True,
            "candidates": candidates
        }
    except Exception as e:
        price_logger.exception("Fragella search failed for product_id=%s: %s", product_id, e)
        return {
            "success": False,
            "error": f"Ошибка поиска: {str(e)[:200]}"
        }


@router.post("/review/{product_id}", response_class=RedirectResponse)
async def save_normalization_review(
    request: Request,
    product_id: int,
    norm_brand: str = Form(""),
    brand_confidence: str = Form(""),
    model_name: str = Form(""),
    series: str = Form(""),
    format_value: str = Form(""),
    volume_ml: str = Form(""),
    color: str = Form(""),
    brand_alias: str = Form(""),
    create_alias: bool = Form(False),
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    """Сохранение исправлений нормализации"""
    product = db.query(PriceProduct).filter(PriceProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Загружаем текущие данные нормализации
    attrs = {}
    if product.attrs_json:
        try:
            attrs = json.loads(product.attrs_json)
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    
    category_path = []
    if product.category_path_json:
        try:
            category_path = json.loads(product.category_path_json)
        except (json.JSONDecodeError, TypeError):
            category_path = []
    
    # Обновляем поля
    if norm_brand.strip():
        product.norm_brand = norm_brand.strip()
        # Если создаём алиас
        if create_alias and product.raw_name:
            # Находим оригинальный бренд из raw_name
            brand_obj = db.query(Brand).filter(Brand.name_canonical.ilike(norm_brand.strip())).first()
            if brand_obj:
                # Получаем алиас из формы или используем автопредложение
                brand_alias_text = brand_alias.strip() if brand_alias else ""
                
                if not brand_alias_text:
                    # Автопредложение: извлекаем часть строки от начала до начала модели
                    brand_alias_text = _extract_brand_alias_from_raw(product.raw_name, model_name.strip() if model_name else None)
                
                if brand_alias_text:
                    alias_upper = brand_alias_text.upper()
                    alias_key = normalize_key(brand_alias_text) or ""
                    existing = db.query(BrandAlias).filter(BrandAlias.alias_upper == alias_upper).first()
                    if not existing:
                        alias = BrandAlias(brand_id=brand_obj.id, alias_upper=alias_upper, alias_key=alias_key)
                        db.add(alias)
    
    if brand_confidence:
        try:
            product.brand_confidence = Decimal(brand_confidence)
        except (InvalidOperation, ValueError):
            pass
    
    if model_name.strip():
        product.model_name = model_name.strip()
    
    if series.strip():
        product.series = series.strip()
    
    if format_value:
        attrs['format'] = format_value
    
    if volume_ml:
        try:
            attrs['volume_ml'] = int(float(volume_ml))
        except (ValueError, TypeError):
            pass
    
    if color.strip():
        attrs['color'] = color.strip()
    
    # Пересчитываем ключи
    from app.services.price_normalization_service import PriceNormalizationService
    service = PriceNormalizationService(db)
    
    # Генерируем group_key и variant_key заново
    group_key = service._generate_group_key(product.norm_brand, product.model_name, product.series)
    variant_key = service._generate_variant_key(group_key, attrs)
    search_text = service._generate_search_text(
        product.raw_name or "",
        product.norm_brand,
        product.model_name or "",
        product.series,
        attrs
    )
    
    product.ai_group_key = group_key
    product.variant_key = variant_key
    product.search_text = search_text
    product.attrs_json = json.dumps(attrs, ensure_ascii=False) if attrs else None
    product.ai_status = "ok"
    product.normalization_notes = "Исправлено вручную"
    
    # Сохраняем product_type и product_subtype из attrs
    if attrs:
        product.product_type = attrs.get('product_type')
        product.product_subtype = attrs.get('product_subtype')
    
    # Обновляем каталог
    from app.services.price_normalization_service import NormalizedResult
    normalized = NormalizedResult(
        brand=product.norm_brand,
        brand_confidence=float(product.brand_confidence or 0),
        model_name=product.model_name or "",
        series=product.series,
        category_path=category_path,
        attrs=attrs,
        group_key=group_key,
        variant_key=variant_key,
        search_text=search_text,
        needs_review=False,
        notes="Исправлено вручную"
    )
    
    try:
        upsert_catalog_from_price(product, normalized, db)
    except IntegrityError as ie:
        # Ошибка целостности при создании/обновлении каталога - не критично, продолжаем
        price_logger.warning("Catalog upsert IntegrityError after review for product_id=%s: %s", product_id, str(ie)[:200])
    except Exception as e:
        price_logger.exception("Catalog upsert failed after review for product_id=%s: %s", product_id, e)
    
    db.commit()
    
    return RedirectResponse(url="/normalization/review", status_code=303)

