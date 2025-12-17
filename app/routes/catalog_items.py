from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db import get_db
from app.models import User, CatalogItem, CatalogVariant
from app.services.auth_service import require_permission, user_has_permission

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

    query = db.query(CatalogItem).filter(CatalogItem.visible.is_(True))
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
        for v in db.query(CatalogVariant).filter(CatalogVariant.catalog_item_id.in_(item_ids)).all():
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
    variants = db.query(CatalogVariant).filter(CatalogVariant.catalog_item_id == ci.id).all()
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


@router.post("/{item_id}/edit", response_class=HTMLResponse)
async def catalog_update(
    item_id: int,
    current_user: User = Depends(require_permission(["catalog.manage"])),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=405, detail="Редактирование карточек каталога отключено: данные формируются автоматически.")
