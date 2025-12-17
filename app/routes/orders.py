from typing import List, Optional
import logging
import time

from fastapi import APIRouter, Depends, Request, HTTPException, status, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import sqlalchemy as sa
from app.db import get_db
from app.models import (
    User,
    Order,
    Client,
    OrderItem,
    Fragrance,
    Partner,
    PriceProduct,
    PriceHistory,
    CatalogItem,
)
from app.services.auth_service import require_permission, user_has_permission
from app.services.order_pricing_service import fill_item_prices, recalc_order_totals

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

ORDER_STATUSES: list[tuple[str, str]] = [
    ("NEW", "Новый"),
    ("WAITING_PAYMENT", "В ожидании оплаты"),
    ("PAID", "Оплачен"),
    ("PACKING", "Сборка"),
    ("SHIPPED", "Отправлен"),
    ("DELIVERED", "Доставлен"),
    ("CANCELLED", "Отменён"),
    ("RETURNED", "Возврат"),
]
ORDER_STATUS_LABELS = dict(ORDER_STATUSES)

def _order_filters_for_user(current_user: User, can_view_all: bool):
    if can_view_all:
        return None
    return [
        (Order.partner_id == getattr(current_user, "partner_id", None)) |
        (Order.created_by_user_id == current_user.id)
    ]


@router.get("/", response_class=HTMLResponse)
async def get_orders_list(
    request: Request,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db)
):
    """Список заказов с учётом прав"""
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    can_view_own = user_has_permission(current_user, db, "orders.view_own")
    q = (request.query_params.get("q") or "").strip()
    status_filter = request.query_params.get("status") or ""
    partner_filter_raw = request.query_params.get("partner_id")
    partner_filter_id = None
    if partner_filter_raw not in (None, "", "all"):
        try:
            partner_filter_id = int(partner_filter_raw)
        except ValueError:
            partner_filter_id = None

    if not can_view_all and not can_view_own:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    query = db.query(Order)
    if not can_view_all and can_view_own:
        query = query.filter(
            (Order.partner_id == getattr(current_user, "partner_id", None)) |
            (Order.created_by_user_id == current_user.id)
        )
    if q:
        like_expr = f"%{q.lower()}%"
        query = query.join(Client, Client.id == Order.client_id).filter(
            (Order.id.ilike(like_expr)) |
            (Client.name.ilike(like_expr)) |
            (Client.phone.ilike(like_expr))
        )
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if can_view_all and partner_filter_id is not None:
        if partner_filter_id == 0:
            query = query.filter(Order.partner_id.is_(None))
        else:
            query = query.filter(Order.partner_id == partner_filter_id)
    orders = query.order_by(Order.created_at.desc()).all()

    return templates.TemplateResponse("orders_list.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "orders": orders,
        "is_partner_user": bool(getattr(current_user, "partner_id", None)) and not can_view_all,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "filters": {"q": q, "status": status_filter, "partner_id": partner_filter_id},
        "partners": db.query(Partner).all() if can_view_all else [],
    })


@router.get("/new", response_class=HTMLResponse)
async def new_order_form(
    request: Request,
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
    price_product_id: Optional[int] = None,
    catalog_item_id: Optional[int] = Query(None),
):
    t0 = time.perf_counter()
    clients = db.query(Client).all()
    partners = db.query(Partner).all()
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    fixed_partner = None
    if is_partner_user:
        fixed_partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
        partners = []

    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    logger.info("[ORDER_NEW] rendered in %.3f sec (clients=%s)", time.perf_counter() - t0, len(clients))
    return templates.TemplateResponse("order_form.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "order": None,
        "clients": clients,
        "partners": partners,
        "fixed_partner": fixed_partner,
        "is_partner_user": is_partner_user,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "selected_price_product_id": price_product_id,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
    })


@router.post("/", response_class=RedirectResponse)
async def create_order(
    request: Request,
    client_id: int = Form(...),
    partner_id: Optional[str] = Form(None),
    status_value: str = Form("NEW"),
    fragrance_ids: List[str] = Form([]),
    price_product_ids: List[str] = Form([]),
    catalog_item_ids: List[str] = Form([]),
    quantities: List[int] = Form([]),
    discounts: List[str] = Form([]),
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db)
):
    partner_id_int = int(partner_id) if partner_id not in (None, "", "None") else None
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    if is_partner_user:
        partner_id_int = current_user.partner_id

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Клиент не найден")

    order = Order(
        client_id=client_id,
        created_by_user_id=current_user.id,
        partner_id=partner_id_int,
        status=status_value,
        total_amount=0,
    )
    db.add(order)

    def _to_int_or_none(seq):
        return [int(x) if str(x).strip().isdigit() else None for x in seq]

    fragrance_ids_clean = _to_int_or_none(fragrance_ids)
    price_product_ids_clean = _to_int_or_none(price_product_ids)
    catalog_item_ids_clean = _to_int_or_none(catalog_item_ids)

    for idx in range(max(len(fragrance_ids_clean), len(price_product_ids_clean), len(catalog_item_ids_clean))):
        fr_id = fragrance_ids_clean[idx] if idx < len(fragrance_ids_clean) else None
        price_prod_id = price_product_ids_clean[idx] if idx < len(price_product_ids_clean) else None
        catalog_item_id = catalog_item_ids_clean[idx] if idx < len(catalog_item_ids_clean) else None

        if fr_id is None and price_prod_id is None and catalog_item_id is None:
            continue

        fragrance = None
        price_product = None
        catalog_item = None
        if fr_id:
            fragrance = db.query(Fragrance).filter(Fragrance.id == fr_id).first()
            if not fragrance:
                raise HTTPException(status_code=400, detail=f"Аромат #{fr_id} не найден")
        if price_prod_id:
            price_product = db.query(PriceProduct).filter(PriceProduct.id == price_prod_id).first()
            if not price_product:
                raise HTTPException(status_code=400, detail=f"Товар прайса #{price_prod_id} не найден")
        if catalog_item_id:
            catalog_item = db.query(CatalogItem).filter(CatalogItem.id == catalog_item_id).first()
            if not catalog_item:
                raise HTTPException(status_code=400, detail=f"Товар каталога #{catalog_item_id} не найден")
            if catalog_item.price_product_id and not price_product:
                price_product = db.query(PriceProduct).filter(PriceProduct.id == catalog_item.price_product_id).first()
                price_prod_id = catalog_item.price_product_id

        qty = quantities[idx] if idx < len(quantities) else 1
        try:
            qty_int = int(qty)
        except ValueError:
            qty_int = 1
        discount_raw = discounts[idx] if idx < len(discounts) else "0"
        try:
            discount_val = float(discount_raw or 0)
        except ValueError:
            discount_val = 0

        name = ""
        original_name = ""
        base_price = 0
        if catalog_item:
            name = catalog_item.name or ""
        if fragrance:
            name = name or f"{fragrance.name} ({fragrance.brand})"
            base_price = fragrance.price or base_price
        if price_product:
            latest_history = (
                db.query(PriceHistory)
                .filter(PriceHistory.price_product_id == price_product.id)
                .order_by(PriceHistory.created_at.desc())
                .first()
            )
            if latest_history:
                base_price = (latest_history.new_price_2 if latest_history.new_price_2 is not None else latest_history.price) or base_price
            if not name:
                name = price_product.product_name or price_product.raw_name or price_product.external_article
            original_name = price_product.raw_name or name
        elif fragrance:
            original_name = name
        else:
            original_name = name or "Товар"

        item = OrderItem(
            price_product_id=price_prod_id,
            catalog_item_id=catalog_item_id,
            sku_id=fr_id,
            name=name,
            original_name=original_name,
            qty=qty_int,
            discount=discount_val,
            price=base_price or 0,
        )
        fill_item_prices(order, item, fragrance, db, price_product)
        order.items.append(item)

    recalc_order_totals(order)
    db.commit()
    db.refresh(order)

    return RedirectResponse(url=f"/orders/{order.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{order_id}/edit", response_class=HTMLResponse)
async def edit_order_form(
    request: Request,
    order_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own", "orders.create"])),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    can_view_own = user_has_permission(current_user, db, "orders.view_own")
    if not can_view_all:
        allowed = False
        if can_view_own:
            if order.created_by_user_id == current_user.id:
                allowed = True
            if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
                allowed = True
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    clients = db.query(Client).all()
    partners = db.query(Partner).all()
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    fixed_partner = None
    if is_partner_user:
        fixed_partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
        partners = []
    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    return templates.TemplateResponse("order_form.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "order": order,
        "clients": clients,
        "partners": partners,
        "fixed_partner": fixed_partner,
        "is_partner_user": is_partner_user,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
    })


@router.post("/{order_id}/edit", response_class=RedirectResponse)
async def update_order(
    request: Request,
    order_id: int,
    client_id: int = Form(...),
    partner_id: Optional[str] = Form(None),
    status_value: str = Form("NEW"),
    fragrance_ids: List[str] = Form([]),
    price_product_ids: List[str] = Form([]),
    catalog_item_ids: List[str] = Form([]),
    quantities: List[int] = Form([]),
    discounts: List[str] = Form([]),
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own", "orders.create"])),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    can_view_own = user_has_permission(current_user, db, "orders.view_own")
    if not can_view_all:
        allowed = False
        if can_view_own:
            if order.created_by_user_id == current_user.id:
                allowed = True
            if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
                allowed = True
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    partner_id_int = int(partner_id) if partner_id not in (None, "", "None") else None
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    if is_partner_user:
        partner_id_int = current_user.partner_id
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Клиент не найден")

    order.client_id = client_id
    order.partner_id = partner_id_int
    order.status = status_value

    order.items.clear()

    def _to_int_or_none(seq):
        return [int(x) if str(x).strip().isdigit() else None for x in seq]

    fragrance_ids_clean = _to_int_or_none(fragrance_ids)
    price_product_ids_clean = _to_int_or_none(price_product_ids)
    catalog_item_ids_clean = _to_int_or_none(catalog_item_ids)

    for idx in range(max(len(fragrance_ids_clean), len(price_product_ids_clean), len(catalog_item_ids_clean))):
        fr_id = fragrance_ids_clean[idx] if idx < len(fragrance_ids_clean) else None
        price_prod_id = price_product_ids_clean[idx] if idx < len(price_product_ids_clean) else None
        catalog_item_id = catalog_item_ids_clean[idx] if idx < len(catalog_item_ids_clean) else None

        if fr_id is None and price_prod_id is None and catalog_item_id is None:
            continue

        fragrance = None
        price_product = None
        catalog_item = None
        if fr_id:
            fragrance = db.query(Fragrance).filter(Fragrance.id == fr_id).first()
            if not fragrance:
                raise HTTPException(status_code=400, detail=f"Аромат #{fr_id} не найден")
        if price_prod_id:
            price_product = db.query(PriceProduct).filter(PriceProduct.id == price_prod_id).first()
            if not price_product:
                raise HTTPException(status_code=400, detail=f"Товар прайса #{price_prod_id} не найден")
        if catalog_item_id:
            catalog_item = db.query(CatalogItem).filter(CatalogItem.id == catalog_item_id).first()
            if not catalog_item:
                raise HTTPException(status_code=400, detail=f"Товар каталога #{catalog_item_id} не найден")
            if catalog_item.price_product_id and not price_product:
                price_product = db.query(PriceProduct).filter(PriceProduct.id == catalog_item.price_product_id).first()
                price_prod_id = catalog_item.price_product_id

        qty = quantities[idx] if idx < len(quantities) else 1
        try:
            qty_int = int(qty)
        except ValueError:
            qty_int = 1
        discount_raw = discounts[idx] if idx < len(discounts) else "0"
        try:
            discount_val = float(discount_raw or 0)
        except ValueError:
            discount_val = 0

        name = ""
        original_name = ""
        base_price = 0
        if catalog_item:
            name = catalog_item.name or ""
        if fragrance:
            name = name or f"{fragrance.name} ({fragrance.brand})"
            base_price = fragrance.price or base_price
        if price_product:
            latest_history = (
                db.query(PriceHistory)
                .filter(PriceHistory.price_product_id == price_product.id)
                .order_by(PriceHistory.created_at.desc())
                .first()
            )
            if latest_history:
                base_price = (latest_history.new_price_2 if latest_history.new_price_2 is not None else latest_history.price) or base_price
            if not name:
                name = price_product.product_name or price_product.raw_name or price_product.external_article
            original_name = price_product.raw_name or name
        elif fragrance:
            original_name = name
        else:
            original_name = name or "Товар"

        item = OrderItem(
            price_product_id=price_prod_id,
            catalog_item_id=catalog_item_id,
            sku_id=fr_id,
            name=name,
            original_name=original_name,
            qty=qty_int,
            discount=discount_val,
            price=base_price or 0,
        )
        fill_item_prices(order, item, fragrance, db, price_product)
        order.items.append(item)

    recalc_order_totals(order)
    db.commit()
    db.refresh(order)

    return RedirectResponse(url=f"/orders/{order.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/price_search")
async def order_price_search_api(
    q: str = "",
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
):
    page_size = max(5, min(int(page_size or 10), 20))
    page = max(1, int(page or 1))

    query = db.query(PriceProduct).filter(PriceProduct.is_active.is_(True))
    q_norm = (q or "").strip()
    if q_norm:
        like_expr = f"%{q_norm.lower()}%"
        query = query.filter(
            (PriceProduct.external_article.ilike(like_expr)) |
            (PriceProduct.raw_name.ilike(like_expr)) |
            (PriceProduct.brand.ilike(like_expr)) |
            (PriceProduct.product_name.ilike(like_expr))
        )

    products = (
        query.order_by(PriceProduct.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    product_ids = [p.id for p in products]
    price_by_pid: dict[int, float] = {}
    if product_ids and (user_has_permission(current_user, db, "prices.view_client") or user_has_permission(current_user, db, "prices.view_cost")):
        sub = (
            db.query(
                PriceHistory.price_product_id.label("pid"),
                sa.func.max(PriceHistory.created_at).label("max_created"),
            )
            .filter(PriceHistory.price_product_id.in_(product_ids))
            .group_by(PriceHistory.price_product_id)
            .subquery()
        )
        rows = (
            db.query(PriceHistory.price_product_id, PriceHistory.new_price_2, PriceHistory.price)
            .join(sub, (PriceHistory.price_product_id == sub.c.pid) & (PriceHistory.created_at == sub.c.max_created))
            .all()
        )
        for pid, new_price_2, price in rows:
            val = new_price_2 if new_price_2 is not None else price
            if val is not None:
                price_by_pid[int(pid)] = float(val)

    return [
        {
            "id": p.id,
            "external_article": p.external_article,
            "brand": p.brand,
            "product_name": p.product_name or p.raw_name,
            "volume_value": float(p.volume_value) if p.volume_value is not None else None,
            "volume_unit": p.volume_unit,
            "base_price": price_by_pid.get(p.id),
        }
        for p in products
    ]


@router.get("/api/price_product/{product_id}")
async def order_price_product_api(
    product_id: int,
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
):
    product = db.query(PriceProduct).filter(PriceProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    base_price = None
    if user_has_permission(current_user, db, "prices.view_client") or user_has_permission(current_user, db, "prices.view_cost"):
        history = (
            db.query(PriceHistory)
            .filter(PriceHistory.price_product_id == product.id)
            .order_by(PriceHistory.created_at.desc())
            .first()
        )
        if history:
            val = history.new_price_2 if history.new_price_2 is not None else history.price
            if val is not None:
                base_price = float(val)

    return {
        "id": product.id,
        "external_article": product.external_article,
        "brand": product.brand,
        "product_name": product.product_name or product.raw_name,
        "base_price": base_price,
    }


@router.get("/{order_id}", response_class=HTMLResponse)
async def get_order_detail(
    request: Request,
    order_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db)
):
    """Деталь заказа с проверкой доступа"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    can_view_own = user_has_permission(current_user, db, "orders.view_own")
    if not can_view_all:
        allowed = False
        if can_view_own:
            if order.created_by_user_id == current_user.id:
                allowed = True
            if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
                allowed = True
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    return templates.TemplateResponse("order_detail.html", {
        "request": request,
        "current_user": current_user,
        "order": order,
        "active_menu": "orders",
        "is_partner_user": bool(getattr(current_user, "partner_id", None)) and not can_view_all,
        "status_labels": ORDER_STATUS_LABELS,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
    })
