from typing import List, Optional
import logging
import time

from fastapi import APIRouter, Depends, Request, HTTPException, status as http_status, Form, Query
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
    Notification,
)
from app.services.auth_service import require_permission, user_has_permission
from app.services.order_pricing_service import fill_item_prices, recalc_order_totals

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

ORDER_STATUSES: list[tuple[str, str]] = [
    ("NEW", "Новый"),
    ("PENDING_CLIENT_APPROVAL", "Требуется подтверждение клиента"),
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
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    query = db.query(Order)
    if not can_view_all and can_view_own:
        query = query.filter(
            (Order.partner_id == getattr(current_user, "partner_id", None)) |
            (Order.created_by_user_id == current_user.id)
        )
    if q:
        like_expr = f"%{q.lower()}%"
        # Пытаемся преобразовать q в число для поиска по ID
        try:
            order_id = int(q)
            query = query.join(Client, Order.client_id == Client.id).filter(
                (Order.id == order_id) |
                (Client.name.ilike(like_expr)) |
                (Client.phone.ilike(like_expr))
            )
        except ValueError:
            # Если q не число, ищем только по имени и телефону клиента
            query = query.join(Client, Order.client_id == Client.id).filter(
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
    
    # Определяем для каждого заказа, может ли пользователь его удалить
    orders_with_permissions = []
    for order in orders:
        can_delete_order = False
        if can_view_all:
            can_delete_order = True
        elif can_view_own:
            if order.created_by_user_id == current_user.id:
                can_delete_order = True
            if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
                can_delete_order = True
        orders_with_permissions.append({
            "order": order,
            "can_delete": can_delete_order
        })

    return templates.TemplateResponse("orders_list.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "orders_with_permissions": orders_with_permissions,
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
    client_id: Optional[int] = Query(None),
):
    t0 = time.perf_counter()
    # Убрали db.query(Client).all() - клиенты будут загружаться через API поиска
    partners = db.query(Partner).all()
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    fixed_partner = None
    if is_partner_user:
        fixed_partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
        partners = []

    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")
    can_view_all_clients = user_has_permission(current_user, db, "clients.view_all")
    can_view_own_clients = user_has_permission(current_user, db, "clients.view_own")

    logger.info("[ORDER_NEW] rendered in %.3f sec", time.perf_counter() - t0)
    # Если передан client_id, получаем информацию о клиенте для предзаполнения
    selected_client = None
    if client_id:
        selected_client = db.query(Client).filter(Client.id == client_id).first()
    
    return templates.TemplateResponse("order_form.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "order": None,
        "partners": partners,
        "fixed_partner": fixed_partner,
        "is_partner_user": is_partner_user,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "selected_price_product_id": price_product_id,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
        "can_view_all_clients": can_view_all_clients,
        "can_view_own_clients": can_view_own_clients,
        "selected_client": selected_client,
    })


@router.post("/", response_class=RedirectResponse)
async def create_order(
    request: Request,
    client_id: int = Form(...),
    partner_id: Optional[str] = Form(None),
    status_value: str = Form("NEW"),
    payment_method: Optional[str] = Form(None),
    delivery_type: Optional[str] = Form(None),
    delivery_tracking: Optional[str] = Form(None),
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
        payment_method=payment_method if payment_method else None,
        delivery_type=delivery_type if delivery_type else None,
        delivery_tracking=delivery_tracking if delivery_tracking else None,
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

    recalc_order_totals(order, db)
    db.commit()
    db.refresh(order)
    
    # Создаём уведомление для администратора о новом заказе
    admin_users = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).all()
    for admin in admin_users:
        notification = Notification(
            user_id=admin.id,
            type="order_created",
            title=f"Создан новый заказ #{order.id}",
            message=f"Клиент: {client.name if client else 'Неизвестно'}. Сумма: {order.total_client_amount or order.total_amount}",
            related_type="order",
            related_id=order.id,
        )
        db.add(notification)
    
    # Если заказ принадлежит партнёру, уведомляем его
    if order.partner_id:
        partner = db.query(Partner).filter(Partner.id == order.partner_id).first()
        if partner and partner.user_id:
            notification = Notification(
                user_id=partner.user_id,
                type="order_created",
                title=f"Создан новый заказ #{order.id}",
                message=f"Клиент: {client.name if client else 'Неизвестно'}. Сумма: {order.total_client_amount or order.total_amount}",
                related_type="order",
                related_id=order.id,
            )
            db.add(notification)
    
    db.commit()

    return RedirectResponse(url=f"/orders/{order.id}", status_code=http_status.HTTP_303_SEE_OTHER)


@router.get("/{order_id}/edit", response_class=HTMLResponse)
async def edit_order_form(
    request: Request,
    order_id: int,
    client_id: Optional[int] = Query(None),
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
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    # Убрали db.query(Client).all() - клиенты будут загружаться через API поиска
    partners = db.query(Partner).all()
    is_partner_user = bool(getattr(current_user, "partner_id", None)) and not user_has_permission(current_user, db, "orders.view_all")
    fixed_partner = None
    if is_partner_user:
        fixed_partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
        partners = []
    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")
    can_view_all_clients = user_has_permission(current_user, db, "clients.view_all")
    can_view_own_clients = user_has_permission(current_user, db, "clients.view_own")
    
    # Если передан client_id в query параметрах (возврат после создания клиента), используем его
    selected_client = None
    if client_id:
        selected_client = db.query(Client).filter(Client.id == client_id).first()

    return templates.TemplateResponse("order_form.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "orders",
        "order": order,
        "partners": partners,
        "fixed_partner": fixed_partner,
        "is_partner_user": is_partner_user,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
        "can_view_all_clients": can_view_all_clients,
        "can_view_own_clients": can_view_own_clients,
        "selected_client": selected_client,
    })


@router.post("/{order_id}/add_item", response_class=RedirectResponse)
async def add_item_to_order(
    order_id: int,
    price_product_id: int = Form(...),
    quantity: int = Form(1),
    discount: str = Form("0"),
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own", "orders.create"])),
    db: Session = Depends(get_db)
):
    """Добавление товара из прайса в существующий заказ"""
    from decimal import Decimal
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    if not can_view_all:
        partner_id = getattr(current_user, "partner_id", None)
        if order.partner_id != partner_id and order.created_by_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому заказу")
    
    # Получаем товар из прайса
    price_product = db.query(PriceProduct).filter(PriceProduct.id == price_product_id).first()
    if not price_product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Получаем последнюю цену из истории
    latest_history = (
        db.query(PriceHistory)
        .filter(PriceHistory.price_product_id == price_product.id)
        .order_by(PriceHistory.created_at.desc())
        .first()
    )
    
    base_price = 0
    if latest_history:
        base_price = (latest_history.new_price_2 if latest_history.new_price_2 is not None else latest_history.price) or 0
    
    name = price_product.product_name or price_product.raw_name or price_product.external_article
    original_name = price_product.raw_name or name
    
    # Парсим discount
    try:
        discount_val = Decimal(str(discount).replace(",", "."))
    except (ValueError, TypeError):
        discount_val = Decimal(0)
    
    qty_int = max(1, int(quantity or 1))
    
    # Создаём позицию заказа
    item = OrderItem(
        price_product_id=price_product_id,
        name=name,
        original_name=original_name,
        qty=qty_int,
        discount=discount_val,
        price=base_price or 0,
    )
    
    # Заполняем цены
    fill_item_prices(order, item, None, db, price_product)
    order.items.append(item)
    
    # Пересчитываем суммы заказа
    recalc_order_totals(order, db)
    db.commit()
    
    return RedirectResponse(url=f"/orders/{order_id}/edit", status_code=303)


@router.post("/{order_id}/edit", response_class=RedirectResponse)
async def update_order(
    request: Request,
    order_id: int,
    client_id: int = Form(...),
    partner_id: Optional[str] = Form(None),
    status_value: str = Form("NEW"),
    payment_method: Optional[str] = Form(None),
    delivery_type: Optional[str] = Form(None),
    delivery_tracking: Optional[str] = Form(None),
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
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

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
    order.payment_method = payment_method if payment_method else None
    order.delivery_type = delivery_type if delivery_type else None
    order.delivery_tracking = delivery_tracking if delivery_tracking else None

    # Сохраняем количество товаров до обновления для проверки изменений
    old_items_count = len(order.items)
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

    recalc_order_totals(order, db)
    db.commit()
    db.refresh(order)
    
    # Проверяем, были ли добавлены новые товары
    new_items_count = len(order.items)
    items_added = new_items_count > old_items_count
    
    if items_added:
        # Создаём уведомление для администратора о добавлении товаров
        admin_users = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).all()
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                type="order_items_added",
                title=f"В заказ #{order.id} добавлены товары",
                message=f"Добавлено товаров: {new_items_count - old_items_count}. Клиент: {client.name if client else 'Неизвестно'}",
                related_type="order",
                related_id=order.id,
            )
            db.add(notification)
        
        # Если заказ принадлежит партнёру, уведомляем его
        if order.partner_id:
            partner = db.query(Partner).filter(Partner.id == order.partner_id).first()
            if partner and partner.user_id:
                notification = Notification(
                    user_id=partner.user_id,
                    type="order_items_added",
                    title=f"В заказ #{order.id} добавлены товары",
                    message=f"Добавлено товаров: {new_items_count - old_items_count}. Клиент: {client.name if client else 'Неизвестно'}",
                    related_type="order",
                    related_id=order.id,
                )
                db.add(notification)
        
        db.commit()

    return RedirectResponse(url=f"/orders/{order.id}", status_code=http_status.HTTP_303_SEE_OTHER)


@router.get("/api/client_search")
async def order_client_search_api(
    q: str = "",
    page: int = 1,
    page_size: int = 100,
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own"])),
    db: Session = Depends(get_db),
):
    """API для поиска клиентов при создании заказа"""
    from app.routes.clients import _get_filters_for_user
    
    # Увеличиваем лимит для показа всех доступных клиентов
    page_size = max(5, min(int(page_size or 100), 500))
    page = max(1, int(page or 1))
    
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    can_view_own = user_has_permission(current_user, db, "clients.view_own")
    
    if not can_view_all and not can_view_own:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    query = db.query(Client)
    filters = _get_filters_for_user(current_user, can_view_all, q=q.strip())
    for flt in filters:
        query = query.filter(flt)
    
    # Если запрос пустой, показываем всех доступных клиентов (без пагинации для удобства)
    if not q.strip():
        clients = query.order_by(Client.created_at.desc()).limit(page_size).all()
    else:
        clients = query.order_by(Client.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone or "",
            "city": c.city or "",
            "email": c.email or "",
        }
        for c in clients
    ]


@router.get("/api/list")
async def get_orders_list_api(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """API для получения списка заказов пользователя (для выбора при добавлении товара)"""
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    
    query = db.query(Order)
    
    # Фильтруем по правам доступа
    if not can_view_all:
        partner_id = getattr(current_user, "partner_id", None)
        query = query.filter(
            (Order.created_by_user_id == current_user.id) |
            (Order.partner_id == partner_id)
        )
    
    # Фильтр по статусу - показываем только активные заказы (не отменённые и не доставленные)
    if status:
        query = query.filter(Order.status == status)
    else:
        # По умолчанию показываем только активные заказы
        query = query.filter(
            Order.status.notin_(["CANCELLED", "DELIVERED", "RETURNED"])
        )
    
    limit = max(1, min(int(limit or 50), 100))
    orders = query.order_by(Order.created_at.desc()).limit(limit).all()
    
    return [
        {
            "id": o.id,
            "client_name": o.client.name if o.client else "",
            "client_phone": o.client.phone if o.client else "",
            "status": o.status,
            "status_label": ORDER_STATUS_LABELS.get(o.status, o.status),
            "total_amount": float(o.total_amount) if o.total_amount else 0.0,
            "created_at": o.created_at.isoformat() if o.created_at else "",
            "items_count": len(o.items) if o.items else 0,
        }
        for o in orders
    ]


@router.get("/api/price_search")
async def order_price_search_api(
    q: str = "",
    page: int = 1,
    page_size: int = 10,
    client_id: Optional[str] = None,
    partner_id: Optional[str] = None,
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
):
    from app.services.partner_pricing_service import get_total_markup_percent, calc_client_price
    from decimal import Decimal
    
    page_size = max(5, min(int(page_size or 10), 100))  # Увеличиваем лимит для показа большего количества товаров
    page = max(1, int(page or 1))

    query = db.query(PriceProduct).filter(PriceProduct.is_active.is_(True))
    q_norm = (q or "").strip()
    if q_norm:
        # Используем улучшенный поиск с поддержкой кириллицы
        # Разбиваем запрос на токены и ищем по каждому
        tokens = [t.strip() for t in q_norm.replace(",", " ").split() if t.strip()]
        if tokens:
            # Пробуем использовать FTS5 для лучшей поддержки кириллицы
            dialect = db.bind.dialect.name if db.bind else None
            fts_ids = []
            
            if dialect == "sqlite" and tokens:
                try:
                    # Проверяем существование таблицы FTS5
                    fts_exists = db.execute(sa.text("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='price_products_fts5'
                    """)).first()
                    
                    if fts_exists:
                        # Формируем поисковый запрос для FTS5
                        match_expr = " AND ".join(tokens)
                        try:
                            fts_subquery = sa.text("""
                                SELECT rowid FROM price_products_fts5 
                                WHERE price_products_fts5 MATCH :match
                            """)
                            fts_result = db.execute(fts_subquery, {"match": match_expr})
                            fts_ids = [row[0] for row in fts_result] if fts_result else []
                        except Exception:
                            fts_ids = []
                except Exception:
                    fts_ids = []
            
            if fts_ids:
                # Используем FTS5 результаты
                query = query.filter(PriceProduct.id.in_(fts_ids))
            else:
                # Fallback на обычный поиск с улучшенной обработкой кириллицы
                # Используем OR для каждого токена, чтобы найти товары, содержащие любой из токенов
                conditions = []
                for tok in tokens:
                    like_expr = f"%{tok}%"
                    conditions.append(
                        (PriceProduct.external_article.ilike(like_expr)) |
                        (PriceProduct.raw_name.ilike(like_expr)) |
                        (PriceProduct.brand.ilike(like_expr)) |
                        (PriceProduct.product_name.ilike(like_expr)) |
                        (PriceProduct.search_text.ilike(like_expr) if hasattr(PriceProduct, 'search_text') else sa.false())
                    )
                # Объединяем условия через AND (все токены должны быть найдены)
                from sqlalchemy import or_, and_
                query = query.filter(and_(*conditions))

    products = (
        query.order_by(PriceProduct.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    product_ids = [p.id for p in products]
    base_price_by_pid: dict[int, Decimal] = {}
    if product_ids and (user_has_permission(current_user, db, "prices.view_client") or user_has_permission(current_user, db, "prices.view_cost")):
        # Используем ту же логику, что и в order_price_product_api для получения актуальных цен
        # Сначала проверяем PriceProduct.price_2, затем PriceHistory
        for product in products:
            # Приоритет 1: PriceProduct.price_2 (если есть)
            if product.price_2 is not None:
                base_price_by_pid[product.id] = Decimal(str(product.price_2))
            else:
                # Приоритет 2: последняя PriceHistory
                history = (
                    db.query(PriceHistory)
                    .filter(PriceHistory.price_product_id == product.id)
                    .order_by(PriceHistory.created_at.desc())
                    .first()
                )
                if history:
                    val = history.new_price_2 if history.new_price_2 is not None else history.price
                    if val is not None:
                        base_price_by_pid[product.id] = Decimal(str(val))

    # Определяем partner_id и client_id для применения накруток
    partner_id_int = None
    client_id_int = None
    
    # Если partner_id передан в запросе
    if partner_id not in (None, "", "None", "null"):
        try:
            partner_id_int = int(partner_id)
        except ValueError:
            pass
    
    # Если partner_id не передан, но у пользователя есть partner_id
    if partner_id_int is None:
        partner_id_int = getattr(current_user, "partner_id", None)
    
    # Если client_id передан в запросе
    if client_id not in (None, "", "None", "null"):
        try:
            client_id_int = int(client_id)
        except ValueError:
            pass

    # Применяем накрутки к ценам
    # ВАЖНО: Используем ту же логику, что и при добавлении товара в заказ
    price_by_pid: dict[int, float] = {}
    for pid, base_price in base_price_by_pid.items():
        if partner_id_int:
            # Если есть партнер, применяем накрутки
            total_markup = get_total_markup_percent(db, partner_id_int, client_id=client_id_int)
            client_price = calc_client_price(base_price, total_markup)
            price_by_pid[pid] = float(client_price)
        else:
            # Если нет партнера, используем базовую цену (без накруток)
            price_by_pid[pid] = float(base_price)

    return [
        {
            "id": p.id,
            "external_article": p.external_article,
            "brand": p.brand,
            "product_name": p.product_name or p.raw_name,
            "raw_name": p.raw_name,  # Добавляем raw_name для полного отображения
            "volume_value": float(p.volume_value) if p.volume_value is not None else None,
            "volume_unit": p.volume_unit,
            "base_price": price_by_pid.get(p.id),
        }
        for p in products
    ]


@router.get("/api/price_product/{product_id}")
async def order_price_product_api(
    product_id: int,
    client_id: Optional[str] = None,
    partner_id: Optional[str] = None,
    current_user: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
):
    from app.services.partner_pricing_service import get_total_markup_percent, calc_client_price
    from decimal import Decimal
    
    product = db.query(PriceProduct).filter(PriceProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    base_price = None
    if user_has_permission(current_user, db, "prices.view_client") or user_has_permission(current_user, db, "prices.view_cost"):
        # Приоритет 1: PriceProduct.price_2 (если есть)
        if product.price_2 is not None:
            base_price = Decimal(str(product.price_2))
        else:
            # Приоритет 2: последняя PriceHistory
            history = (
                db.query(PriceHistory)
                .filter(PriceHistory.price_product_id == product.id)
                .order_by(PriceHistory.created_at.desc())
                .first()
            )
            if history:
                val = history.new_price_2 if history.new_price_2 is not None else history.price
                if val is not None:
                    base_price = Decimal(str(val))

    # Определяем partner_id и client_id для применения накруток
    partner_id_int = None
    client_id_int = None
    
    # Если partner_id передан в запросе
    if partner_id not in (None, "", "None", "null"):
        try:
            partner_id_int = int(partner_id)
        except ValueError:
            pass
    
    # Если partner_id не передан, но у пользователя есть partner_id
    if partner_id_int is None:
        partner_id_int = getattr(current_user, "partner_id", None)
    
    # Если client_id передан в запросе
    if client_id not in (None, "", "None", "null"):
        try:
            client_id_int = int(client_id)
        except ValueError:
            pass

    # Применяем накрутки к цене, если есть партнер
    final_price = None
    if base_price is not None:
        if partner_id_int:
            total_markup = get_total_markup_percent(db, partner_id_int, client_id=client_id_int)
            client_price = calc_client_price(base_price, total_markup)
            final_price = float(client_price)
        else:
            final_price = float(base_price)

    return {
        "id": product.id,
        "external_article": product.external_article,
        "brand": product.brand,
        "product_name": product.product_name or product.raw_name,
        "base_price": final_price,
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
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Проверяем, может ли пользователь удалять этот заказ
    can_delete = False
    if can_view_all:
        can_delete = True
    elif can_view_own:
        if order.created_by_user_id == current_user.id:
            can_delete = True
        if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
            can_delete = True

    can_view_client_price = user_has_permission(current_user, db, "prices.view_client")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    # Пересчитываем маржу для старых заказов, если нужно
    if order.items:
        from app.services.order_pricing_service import fill_item_prices
        needs_recalc = False
        for item in order.items:
            if item.price_product_id:
                fill_item_prices(order, item, None, db, item.price_product)
                needs_recalc = True
        if needs_recalc:
            recalc_order_totals(order, db)
            db.commit()
            db.refresh(order)

    return templates.TemplateResponse("order_detail.html", {
        "request": request,
        "current_user": current_user,
        "order": order,
        "active_menu": "orders",
        "is_partner_user": bool(getattr(current_user, "partner_id", None)) and not can_view_all,
        "status_labels": ORDER_STATUS_LABELS,
        "status_choices": ORDER_STATUSES,
        "can_view_client_price": can_view_client_price,
        "can_view_cost": can_view_cost,
        "can_view_margin": can_view_margin,
        "can_delete": can_delete,
    })


@router.post("/{order_id}/status", response_class=RedirectResponse)
async def update_order_status(
    order_id: int,
    status: str = Form(...),
    return_to: Optional[str] = Form(None),
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db)
):
    """Изменение статуса заказа"""
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        
        # Проверяем права доступа
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
                raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        
        # Проверяем, что статус валидный
        valid_statuses = [code for code, _ in ORDER_STATUSES]
        if status not in valid_statuses:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Неверный статус: {status}")
        
        order.status = status
        db.commit()
        db.refresh(order)
        
        logger.info(f"Order {order_id} status changed to {status} by user {current_user.id}")
        
        # Если запрос пришел со страницы списка, возвращаемся туда
        if return_to == "list":
            return RedirectResponse(url="/orders", status_code=http_status.HTTP_303_SEE_OTHER)
        
        return RedirectResponse(url=f"/orders/{order_id}", status_code=http_status.HTTP_303_SEE_OTHER)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating order {order_id} status: {e}")
        db.rollback()
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при изменении статуса: {str(e)}")


@router.post("/{order_id}/delete", response_class=RedirectResponse)
async def delete_order(
    order_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db)
):
    """Удаление заказа с проверкой доступа"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    can_view_own = user_has_permission(current_user, db, "orders.view_own")
    
    # Проверяем права на удаление
    can_delete = False
    if can_view_all:
        can_delete = True
    elif can_view_own:
        if order.created_by_user_id == current_user.id:
            can_delete = True
        if getattr(current_user, "partner_id", None) and order.partner_id == current_user.partner_id:
            can_delete = True
    
    if not can_delete:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для удаления заказа")
    
    # Удаляем заказ (каскадное удаление удалит все связанные OrderItem)
    db.delete(order)
    db.commit()
    
    return RedirectResponse(url="/orders", status_code=http_status.HTTP_303_SEE_OTHER)
