from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CatalogItem, PriceProduct
from app.services.auth_service import require_permission

router = APIRouter(prefix="/internal", tags=["internal-catalog"])


class CatalogEnrichPayload(BaseModel):
    name: Optional[str] = None
    description_short: Optional[str] = None
    description_full: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    visible: Optional[bool] = None


@router.post("/catalog/{item_id}/enrich")
async def enrich_catalog_item(
    item_id: int,
    payload: CatalogEnrichPayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission(["catalog.manage", "catalog.view_full"])),
):
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар каталога не найден")

    if payload.name is not None:
        item.name = payload.name
    if payload.description_short is not None:
        item.description_short = payload.description_short
    if payload.description_full is not None:
        item.description_full = payload.description_full
    if payload.image_url is not None:
        item.image_url = payload.image_url
    if payload.tags is not None:
        item.tags = payload.tags
    if payload.visible is not None:
        item.visible = payload.visible
    item.updated_at = datetime.utcnow()
    db.add(item)
    db.commit()
    return {"status": "ok"}


@router.get("/catalog/{item_id}/raw")
async def get_catalog_item_raw(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission(["catalog.view_full", "catalog.manage"])),
):
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар каталога не найден")
    price_product = None
    if item.price_product_id:
        price_product = db.query(PriceProduct).filter(PriceProduct.id == item.price_product_id).first()

    return {
        "id": item.id,
        "article": item.article,
        "brand": item.brand,
        "name": item.name,
        "type": item.type,
        "volume": item.volume,
        "gender": item.gender,
        "description_short": item.description_short,
        "description_full": item.description_full,
        "image_url": item.image_url,
        "tags": item.tags,
        "visible": item.visible,
        "in_stock": item.in_stock,
        "price_product": {
            "id": price_product.id,
            "external_article": price_product.external_article,
            "raw_name": price_product.raw_name,
            "brand": price_product.brand,
            "product_name": price_product.product_name,
            "category": price_product.category,
            "volume_value": float(price_product.volume_value) if price_product and price_product.volume_value else None,
            "volume_unit": price_product.volume_unit if price_product else None,
            "gender": price_product.gender if price_product else None,
            "is_active": price_product.is_active if price_product else None,
        } if price_product else None,
    }
