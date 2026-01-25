from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db import get_db
from app.models import CatalogItem, CatalogVariant, PriceProduct

router = APIRouter(tags=["catalog-api"])


def _split_words(q: str) -> List[str]:
    return [w.strip() for w in (q or "").replace(",", " ").split() if w.strip()]


def _volume_label(v: CatalogVariant) -> str:
    val = ""
    if v.volume_value is not None:
        val = str(v.volume_value).rstrip("0").rstrip(".") if isinstance(v.volume_value, (float, int)) else str(v.volume_value)
    unit = (v.volume_unit or "").strip()
    label = f"{val} {unit}".strip()
    if v.is_tester:
        label = f"{label} (тестер)" if label else "тестер"
    return label


@router.get("/api/catalog")
async def catalog_list(
    q: Optional[str] = None,
    brands: Optional[List[str]] = Query(default=None),
    types: Optional[List[str]] = Query(default=None, alias="types"),
    letter: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    show_out_of_stock: bool = False,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    limit = max(1, min(int(limit or 20), 100))

    # Фильтруем только те CatalogItem, у которых есть варианты с активными товарами прайса
    query = (
        db.query(CatalogItem)
        .join(CatalogVariant, CatalogItem.id == CatalogVariant.catalog_item_id)
        .join(PriceProduct, CatalogVariant.price_product_id == PriceProduct.id)
        .filter(
            CatalogItem.visible.is_(True),
            PriceProduct.is_active.is_(True),
            PriceProduct.is_in_stock.is_(True),
            PriceProduct.is_in_current_pricelist.is_(True)
        )
        .distinct()
    )
    if not show_out_of_stock:
        query = query.filter(CatalogItem.in_stock.is_(True))

    words = _split_words(q or "")
    for w in words:
        like = f"%{w}%"
        query = query.filter(
            sa.and_(
                CatalogItem.display_name.ilike(like)
                | CatalogItem.name.ilike(like)
                | CatalogItem.brand.ilike(like)
                | sa.cast(CatalogItem.tags, sa.String).ilike(like)
                | CatalogItem.description_short.ilike(like)
            )
        )

    if letter:
        first = letter.strip()[:1]
        if first:
            query = query.filter(sa.func.upper(sa.func.substr(CatalogItem.display_name, 1, 1)) == first.upper())

    if brands:
        query = query.filter(CatalogItem.brand.in_(brands))
    if types:
        query = query.filter(CatalogItem.type.in_(types))

    total = query.count()
    items = query.order_by(CatalogItem.brand.asc(), CatalogItem.name.asc()).offset((page - 1) * limit).limit(limit).all()

    # Prefetch variants (только для активных товаров прайса)
    item_ids = [i.id for i in items]
    variants_by_item = {vid: [] for vid in item_ids}
    if item_ids:
        for v in (
            db.query(CatalogVariant)
            .join(PriceProduct, CatalogVariant.price_product_id == PriceProduct.id)
            .filter(
                CatalogVariant.catalog_item_id.in_(item_ids),
                PriceProduct.is_active.is_(True),
                PriceProduct.is_in_stock.is_(True),
                PriceProduct.is_in_current_pricelist.is_(True)
            )
            .all()
        ):
            variants_by_item.setdefault(v.catalog_item_id, []).append(v)

    pages = (total + limit - 1) // limit if total else 1
    data = {
        "items": [
            {
                "id": item.id,
                "displayName": item.display_name or f"{item.brand or ''} {item.name}".strip(),
                "brand": item.brand,
                "type": item.type,
                "image": item.image_url,
                "description": item.description_short,
                "inStock": bool(item.in_stock),
                "volumes": [_volume_label(v) for v in variants_by_item.get(item.id, []) if _volume_label(v)],
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "pages": pages,
    }
    return JSONResponse(data)


@router.get("/api/catalog/{item_id}")
async def catalog_detail(item_id: int, db: Session = Depends(get_db)):
    item = (
        db.query(CatalogItem)
        .filter(CatalogItem.id == item_id, CatalogItem.visible.is_(True))
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Товар каталога не найден")

    # Фильтруем варианты только для активных товаров прайса
    variants = (
        db.query(CatalogVariant)
        .join(PriceProduct, CatalogVariant.price_product_id == PriceProduct.id)
        .filter(
            CatalogVariant.catalog_item_id == item.id,
            PriceProduct.is_active.is_(True),
            PriceProduct.is_in_stock.is_(True),
            PriceProduct.is_in_current_pricelist.is_(True)
        )
        .all()
    )

    return {
        "id": item.id,
        "displayName": item.display_name or f"{item.brand or ''} {item.name}".strip(),
        "brand": item.brand,
        "type": item.type,
        "gender": item.gender,
        "image": item.image_url,
        "description": item.description_full or item.description_short,
        "inStock": bool(item.in_stock),
        "variants": [
            {
                "id": v.id,
                "volume": float(v.volume_value) if v.volume_value is not None else None,
                "unit": v.volume_unit,
                "label": _volume_label(v),
                "isTester": bool(v.is_tester),
                "inStock": bool(v.in_stock),
            }
            for v in variants
        ],
    }


@router.post("/api/price-request")
async def price_request(payload: dict, db: Session = Depends(get_db)):
    variant_id = payload.get("variantId") or payload.get("variant_id")
    if not variant_id:
        raise HTTPException(status_code=400, detail="variantId is required")
    variant = db.query(CatalogVariant).filter(CatalogVariant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Вариант не найден")
    if not variant.in_stock:
        # можно разрешить, но пока считаем ошибкой
        raise HTTPException(status_code=400, detail="Вариант недоступен")
    pp = db.query(PriceProduct).filter(PriceProduct.id == variant.price_product_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Позиция прайса не найдена")

    internal_payload = {
        "article": pp.external_article,
        "fullName": variant.request_payload or pp.raw_name,
        "catalogItemId": variant.catalog_item_id,
        "catalogVariantId": variant.id,
        "priceProductId": pp.id,
        "requested_at": datetime.utcnow().isoformat(),
    }
    # TODO: сохранить/отправить дальше (бот/почта). Пока просто лог.
    return {"status": "ok", "message": "Запрос стоимости зарегистрирован", "payload": internal_payload}
