from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CatalogItem, User
from app.services.auth_service import require_roles

router = APIRouter(prefix="/admin", tags=["admin-catalog"])
templates = Jinja2Templates(directory="app/templates")


def _parse_tags(raw: str) -> Optional[List[str]]:
    if raw is None:
        return None
    tokens = [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]
    return tokens or None


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_admin_list(
    request: Request,
    brand: Optional[str] = Query(None),
    type_param: Optional[str] = Query(None, alias="type"),
    visible: Optional[str] = Query(None),
    in_stock: Optional[str] = Query(None),
    page: int = Query(1),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    per_page = 20

    query = db.query(CatalogItem)
    if brand:
        query = query.filter(CatalogItem.brand.ilike(f"%{brand.strip()}%"))
    if type_param:
        query = query.filter(CatalogItem.type.ilike(f"%{type_param.strip()}%"))
    if visible in {"1", "0"}:
        query = query.filter(CatalogItem.visible.is_(visible == "1"))
    if in_stock in {"1", "0"}:
        query = query.filter(CatalogItem.in_stock.is_(in_stock == "1"))

    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)

    items = (
        query.order_by(CatalogItem.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    brand_options = [
        b for (b,) in db.query(CatalogItem.brand).filter(CatalogItem.brand.isnot(None)).distinct().order_by(CatalogItem.brand.asc())
    ]
    type_options = [
        t for (t,) in db.query(CatalogItem.type).filter(CatalogItem.type.isnot(None)).distinct().order_by(CatalogItem.type.asc())
    ]

    return templates.TemplateResponse(
        "admin_catalog_list.html",
        {
            "request": request,
            "items": items,
            "brand_options": brand_options,
            "type_options": type_options,
            "filter_brand": brand or "",
            "filter_type": type_param or "",
            "filter_visible": visible or "",
            "filter_in_stock": in_stock or "",
            "current_user": current_user,
            "active_menu": "admin_catalog",
            "page": page,
            "pages": pages,
            "total": total,
            "per_page": per_page,
        },
    )


@router.post("/catalog/visible_all")
async def catalog_admin_visible_all(
    brand: Optional[str] = Form(None),
    type_value: Optional[str] = Form(None),
    visible: Optional[str] = Form(None),
    in_stock: Optional[str] = Form(None),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = db.query(CatalogItem)
    if brand:
        query = query.filter(CatalogItem.brand.ilike(f"%{brand.strip()}%"))
    if type_value:
        query = query.filter(CatalogItem.type.ilike(f"%{type_value.strip()}%"))
    if visible in {"1", "0"}:
        query = query.filter(CatalogItem.visible.is_(visible == "1"))
    if in_stock in {"1", "0"}:
        query = query.filter(CatalogItem.in_stock.is_(in_stock == "1"))

    updated = query.update(
        {"visible": True, "updated_at": datetime.utcnow()}, synchronize_session=False
    )
    db.commit()

    redirect_params = []
    if brand:
        redirect_params.append(f"brand={brand}")
    if type_value:
        redirect_params.append(f"type={type_value}")
    if visible:
        redirect_params.append(f"visible={visible}")
    if in_stock:
        redirect_params.append(f"in_stock={in_stock}")
    qs = f"?{'&'.join(redirect_params)}" if redirect_params else ""
    return RedirectResponse(url=f"/admin/catalog{qs}", status_code=303)


@router.get("/catalog/{item_id}", response_class=HTMLResponse)
async def catalog_admin_edit(
    item_id: int,
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Позиция каталога не найдена")

    type_options = [
        t for (t,) in db.query(CatalogItem.type).filter(CatalogItem.type.isnot(None)).distinct().order_by(CatalogItem.type.asc())
    ]
    brand_options = [
        b for (b,) in db.query(CatalogItem.brand).filter(CatalogItem.brand.isnot(None)).distinct().order_by(CatalogItem.brand.asc())
    ]

    return templates.TemplateResponse(
        "admin_catalog_edit.html",
        {
            "request": request,
            "item": item,
            "type_options": type_options,
            "brand_options": brand_options,
            "current_user": current_user,
            "active_menu": "admin_catalog",
        },
    )


@router.post("/catalog/{item_id}")
async def catalog_admin_update(
    item_id: int,
    name: str = Form(...),
    brand: Optional[str] = Form(None),
    type_param: Optional[str] = Form(None),
    volume: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    description_short: Optional[str] = Form(None),
    description_full: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    visible: Optional[str] = Form(None),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Позиция каталога не найдена")

    item.name = name.strip()
    item.brand = brand.strip() if brand else None
    item.type = type_param.strip() if type_param else None
    item.volume = volume.strip() if volume else None
    item.gender = gender or None
    item.description_short = description_short or None
    item.description_full = description_full or None
    item.image_url = image_url or None
    item.tags = _parse_tags(tags)
    item.visible = str(visible).lower() in {"1", "true", "on", "yes"}
    item.updated_at = datetime.utcnow()

    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/admin/catalog/{item_id}", status_code=303)


@router.post("/catalog/{item_id}/toggle_visible")
async def catalog_admin_toggle_visible(
    item_id: int,
    new_visible: str = Form(...),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Позиция каталога не найдена")
    item.visible = str(new_visible).lower() in {"1", "true", "on", "yes"}
    item.updated_at = datetime.utcnow()
    db.add(item)
    db.commit()
    return RedirectResponse(url="/admin/catalog", status_code=303)
