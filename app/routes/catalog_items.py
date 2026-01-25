from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db import get_db
from app.models import User, CatalogItem, CatalogVariant, PriceProduct
from app.services.auth_service import require_permission, user_has_permission
from app.services.fragella_client import FragellaClient
import json
from decimal import Decimal

router = APIRouter(prefix="/catalog", tags=["catalog"])
templates = Jinja2Templates(directory="app/templates")


def _volume_label(v: CatalogVariant) -> str:
    val = ""
    if v.volume_value is not None:
        val = str(v.volume_value).rstrip("0").rstrip(".") if isinstance(v.volume_value, (float, int)) else str(v.volume_value)
    unit = (v.volume_unit or "").strip()
    label = f"{val} {unit}".strip()
    if v.is_tester:
        label = f"{label} (тестер)" if label else "тестер"
    return label


@router.get("", response_class=HTMLResponse)
async def catalog_list(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    page: int = 1,
    current_user: User = Depends(require_permission(["catalog.view_full"])),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    per_page = 20

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
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            sa.or_(
                CatalogItem.display_name.ilike(term),
                CatalogItem.brand.ilike(term),
                CatalogItem.name.ilike(term),
                CatalogItem.type.ilike(term),
                CatalogItem.description_short.ilike(term),
            )
        )
    if category:
        query = query.filter(CatalogItem.type.ilike(f"%{category.strip()}%"))
    if brand:
        query = query.filter(CatalogItem.brand.ilike(f"%{brand.strip()}%"))

    total = query.count()
    items = (
        query.order_by(CatalogItem.brand.asc(), CatalogItem.name.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    pages = (total + per_page - 1) // per_page if total else 1

    item_ids = [i.id for i in items]
    variants_by_item = {iid: [] for iid in item_ids}
    if item_ids:
        # Фильтруем варианты только для активных товаров прайса
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

    return templates.TemplateResponse(
        "catalog_items_list.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "catalog",
            "items": items,
            "variants_by_item": variants_by_item,
            "volume_label": _volume_label,
            "page": page,
            "pages": pages,
            "total": total,
            "per_page": per_page,
            "q": q or "",
            "brand_filter": brand or "",
            "category_filter": category or "",
        },
    )


def _parse_tags(raw: str | None):
    if raw is None:
        return None
    tokens = [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]
    return tokens or None


@router.get("/{item_id}", response_class=HTMLResponse)
async def catalog_detail(
    request: Request,
    item_id: int,
    current_user: User = Depends(require_permission(["catalog.view_full"])),
    db: Session = Depends(get_db),
):
    ci = db.query(CatalogItem).filter(CatalogItem.id == item_id, CatalogItem.visible.is_(True)).first()
    if not ci:
        return HTMLResponse(status_code=404, content="Товар не найден")
    # Фильтруем варианты только для активных товаров прайса
    variants = (
        db.query(CatalogVariant)
        .join(PriceProduct, CatalogVariant.price_product_id == PriceProduct.id)
        .filter(
            CatalogVariant.catalog_item_id == ci.id,
            PriceProduct.is_active.is_(True),
            PriceProduct.is_in_stock.is_(True),
            PriceProduct.is_in_current_pricelist.is_(True)
        )
        .all()
    )
    can_manage = user_has_permission(current_user, db, "catalog.manage")
    tags_text = ", ".join(ci.tags) if isinstance(ci.tags, list) else (ci.tags or "")
    item = ci
    return templates.TemplateResponse(
        "catalog_items_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "catalog",
            "item": item,
            "variants": variants,
            "volume_label": _volume_label,
            "page_title": f"{item.brand} - {item.name}",
            "can_manage": can_manage,
            "tags_text": tags_text,
        },
    )


@router.post("/{item_id}/enrich", response_class=JSONResponse)
async def catalog_enrich(
    item_id: int,
    current_user: User = Depends(require_permission(["catalog.manage"])),
    db: Session = Depends(get_db),
):
    """Обогащает карточку каталога через Fragella API"""
    try:
        item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
        if not item:
            return {"success": False, "error": "Карточка не найдена"}
        
        if not item.brand or not item.name:
            return {"success": False, "error": "Недостаточно данных для поиска (нужны brand и name)"}
        
        # Ищем через Fragella
        client = FragellaClient()
        search_query = f"{item.brand} {item.name}".strip()
        
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            def run_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(client.search_fragrances(search_query, limit=5, db=db))
                finally:
                    loop.close()
            
            with ThreadPoolExecutor() as executor:
                candidates = executor.submit(run_async).result()
        except Exception as e:
            return {"success": False, "error": f"Ошибка при поиске в Fragella: {str(e)[:200]}"}
        
        if not candidates or len(candidates) == 0:
            item.enrich_status = "error"
            item.enrich_confidence = Decimal("0")
            item.enriched_json = None
            db.commit()
            return {"success": False, "error": "Ничего не найдено в Fragella"}
        
        # Если один кандидат с высокой уверенностью - используем его
        if len(candidates) == 1:
            candidate = candidates[0]
            item.external_source = "fragella"
            item.external_key = str(candidate.get("id", ""))
            item.enrich_status = "enriched"
            item.enrich_confidence = Decimal("0.9")
            item.enriched_json = json.dumps(candidate, ensure_ascii=False)
            
            # Обновляем поля карточки из данных Fragella
            if candidate.get("name"):
                if not item.display_name:
                    item.display_name = candidate["name"]
            if candidate.get("description"):
                if not item.description_full:
                    item.description_full = candidate["description"]
            if candidate.get("image_url"):
                if not item.image_url:
                    item.image_url = candidate["image_url"]
            if candidate.get("notes"):
                if not item.description_short:
                    item.description_short = ", ".join(candidate["notes"][:3]) if isinstance(candidate["notes"], list) else str(candidate["notes"])
            
            db.commit()
            return {
                "success": True,
                "message": "Карточка обогащена",
                "candidate": candidate
            }
        
        # Если несколько кандидатов - нужен выбор
        item.enrich_status = "needs_review"
        item.enrich_confidence = Decimal("0.5")
        item.enriched_json = json.dumps({"candidates": candidates}, ensure_ascii=False)
        db.commit()
        
        return {
            "success": True,
            "needs_review": True,
            "candidates": candidates,
            "message": f"Найдено {len(candidates)} кандидатов, требуется выбор"
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)[:200]}


@router.post("/{item_id}/enrich/select", response_class=JSONResponse)
async def catalog_enrich_select(
    item_id: int,
    candidate_id: str = Form(...),
    current_user: User = Depends(require_permission(["catalog.manage"])),
    db: Session = Depends(get_db),
):
    """Выбирает кандидата из Fragella для обогащения"""
    try:
        item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
        if not item:
            return {"success": False, "error": "Карточка не найдена"}
        
        if not item.enriched_json:
            return {"success": False, "error": "Нет данных для выбора"}
        
        enriched_data = json.loads(item.enriched_json)
        candidates = enriched_data.get("candidates", [])
        
        selected = None
        for cand in candidates:
            if str(cand.get("id", "")) == candidate_id:
                selected = cand
                break
        
        if not selected:
            return {"success": False, "error": "Кандидат не найден"}
        
        # Применяем выбранного кандидата
        item.external_source = "fragella"
        item.external_key = candidate_id
        item.enrich_status = "enriched"
        item.enrich_confidence = Decimal("0.9")
        item.enriched_json = json.dumps(selected, ensure_ascii=False)
        
        # Обновляем поля карточки
        if selected.get("name"):
            if not item.display_name:
                item.display_name = selected["name"]
        if selected.get("description"):
            if not item.description_full:
                item.description_full = selected["description"]
        if selected.get("image_url"):
            if not item.image_url:
                item.image_url = selected["image_url"]
        if selected.get("notes"):
            if not item.description_short:
                item.description_short = ", ".join(selected["notes"][:3]) if isinstance(selected["notes"], list) else str(selected["notes"])
        
        db.commit()
        return {
            "success": True,
            "message": "Кандидат выбран и применен",
            "candidate": selected
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)[:200]}


@router.post("/{item_id}/edit", response_class=HTMLResponse)
async def catalog_update(
    item_id: int,
    current_user: User = Depends(require_permission(["catalog.manage"])),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=405, detail="Редактирование карточек каталога отключено: данные формируются автоматически.")
