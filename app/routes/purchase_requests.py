"""Роуты для управления запросами на закупку"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.db import get_db
from app.models import User, Partner, Order, PurchaseRequest, purchase_request_orders, PriceProduct, PurchaseRequestItem, Notification, OrderItem
from app.services.auth_service import require_permission, require_roles, user_has_permission
from app.logging_config import price_logger

router = APIRouter(prefix="/purchase_requests", tags=["purchase_requests"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def purchase_requests_list(
    http_request: Request,
    status_filter: Optional[str] = Query(None),
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Список запросов на закупку"""
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    
    query = db.query(PurchaseRequest)
    
    # Партнёр видит только свои запросы
    if not is_admin and getattr(current_user, "partner_id", None):
        query = query.filter(PurchaseRequest.partner_id == current_user.partner_id)
    
    # Фильтр по статусу
    if status_filter and status_filter != "all":
        query = query.filter(PurchaseRequest.status == status_filter)
    
    requests = query.order_by(PurchaseRequest.created_at.desc()).all()
    
    # Подсчитываем количество заказов и позиций для каждого запроса
    for req in requests:
        req.orders_count = len(req.orders) if req.orders else 0
        total_items = 0
        for order in req.orders:
            total_items += len(order.items) if order.items else 0
        req.items_count = total_items
    
    return templates.TemplateResponse("purchase_requests_list.html", {
        "request": http_request,
        "current_user": current_user,
        "purchase_requests": requests,
        "status_filter": status_filter or "all",
        "is_admin": is_admin,
        "active_menu": "orders",
    })


@router.get("/new", response_class=HTMLResponse)
async def new_purchase_request_form(
    http_request: Request,
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    """Форма создания нового запроса на закупку"""
    partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    
    # Получаем заказы партнёра, которые ещё не добавлены в запросы
    orders_in_requests = db.query(purchase_request_orders.c.order_id).subquery()
    available_orders = db.query(Order).filter(
        Order.partner_id == partner.id,
        ~Order.id.in_(db.query(orders_in_requests.c.order_id))
    ).order_by(Order.created_at.desc()).all()
    
    return templates.TemplateResponse("purchase_request_form.html", {
        "request": http_request,
        "current_user": current_user,
        "partner": partner,
        "available_orders": available_orders,
        "active_menu": "orders",
    })


@router.post("/", response_class=RedirectResponse)
async def create_purchase_request(
    http_request: Request,
    expected_delivery_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    order_ids: List[int] = Form([]),
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    """Создание нового запроса на закупку"""
    partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    
    # Парсим дату
    delivery_date = None
    if expected_delivery_date:
        try:
            delivery_date = datetime.strptime(expected_delivery_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Создаём запрос со статусом "NEW" (новый)
    purchase_request = PurchaseRequest(
        partner_id=partner.id,
        created_by_user_id=current_user.id,
        status="NEW",
        expected_delivery_date=delivery_date,
        notes=notes,
    )
    db.add(purchase_request)
    db.flush()
    
    # Добавляем заказы
    if order_ids:
        orders = db.query(Order).filter(
            Order.id.in_(order_ids),
            Order.partner_id == partner.id
        ).all()
        for order in orders:
            purchase_request.orders.append(order)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{purchase_request.id}", status_code=303)


@router.get("/{request_id}", response_class=HTMLResponse)
async def purchase_request_detail(
    http_request: Request,
    request_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Детали запроса на закупку"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    
    # Проверка прав доступа
    if not is_admin and getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому запросу")
    
    # Агрегируем позиции из всех заказов
    # Отслеживаем, когда был создан запрос, чтобы определить новые товары
    request_created_at = purchase_request.created_at
    
    # Получаем все PurchaseRequestItem для этого запроса
    request_items_map = {}
    for req_item in db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.purchase_request_id == request_id
    ).all():
        request_items_map[req_item.order_item_id] = req_item
    
    # Обновляем статус запроса, если он старый (submitted -> NEW)
    if purchase_request.status == "submitted":
        purchase_request.status = "NEW"
        db.flush()
    
    # Флаг для отслеживания изменений, требующих коммита
    has_changes = False
    
    aggregated_items = {}
    for order in purchase_request.orders:
        for item in order.items:
            key = item.price_product_id or item.catalog_item_id or item.sku_id or item.name
            if key not in aggregated_items:
                # Получаем полное наименование из прайса
                full_name = item.name
                if item.price_product_id:
                    price_product = db.query(PriceProduct).filter(PriceProduct.id == item.price_product_id).first()
                    if price_product and price_product.raw_name:
                        full_name = price_product.raw_name
                
                # Определяем статус
                item_status = "normal"
                request_item = request_items_map.get(item.id)
                
                # Проверяем, является ли товар новым
                # В новом запросе (NEW или draft) все товары считаются новыми
                # В отправленном запросе - только товары из заказов, созданных после запроса
                is_new_item = False
                if purchase_request.status in ["NEW", "draft"]:
                    # В новом запросе все товары считаются новыми
                    is_new_item = True
                elif order.created_at and request_created_at and order.created_at > request_created_at:
                    # В отправленном запросе - только если заказ создан после запроса
                    is_new_item = True
                
                # Если нет request_item и товар новый, создаём PurchaseRequestItem со статусом "new"
                if not request_item:
                    if is_new_item:
                        request_item = PurchaseRequestItem(
                            purchase_request_id=request_id,
                            order_item_id=item.id,
                            original_price=item.cost_for_owner,
                            status="new",
                        )
                        db.add(request_item)
                        db.flush()  # Сохраняем, чтобы получить ID
                        request_items_map[item.id] = request_item
                        item_status = "new"
                else:
                    # Если request_item существует, но товар новый и статус ещё "normal", обновляем на "new"
                    if is_new_item and request_item.status == "normal":
                        request_item.status = "new"
                        has_changes = True
                    # Если запрос в статусе NEW/draft, все товары должны быть "new"
                    elif purchase_request.status in ["NEW", "draft"] and request_item.status == "normal":
                        request_item.status = "new"
                        has_changes = True
                
                if request_item:
                    item_status = request_item.status
                
                # Используем цену из request_item, если есть
                display_price = item.cost_for_owner
                if request_item and request_item.proposed_price:
                    display_price = request_item.proposed_price
                elif request_item and request_item.approved_price:
                    display_price = request_item.approved_price
                
                aggregated_items[key] = {
                    "name": full_name,
                    "qty": 0,
                    "total_cost": Decimal(0),
                    "price_product_id": item.price_product_id,
                    "catalog_item_id": item.catalog_item_id,
                    "status": item_status,
                    "order_id": order.id,
                    "order_item_id": item.id,
                    "original_price": item.cost_for_owner,
                    "display_price": display_price,
                    "request_item_id": request_item.id if request_item else None,
                    "price_change_comment": request_item.price_change_comment if request_item else None,
                }
            aggregated_items[key]["qty"] += item.qty
            # Используем display_price для расчёта общей стоимости
            price_for_calc = aggregated_items[key]["display_price"] or aggregated_items[key]["original_price"] or Decimal(0)
            aggregated_items[key]["total_cost"] += price_for_calc * item.qty
    
    # Сохраняем все созданные и обновлённые PurchaseRequestItem для новых товаров
    if has_changes:
        db.commit()
    
    # Получаем доступные заказы для добавления (только для админа)
    available_orders = []
    if is_admin:
        orders_in_requests = db.query(purchase_request_orders.c.order_id).subquery()
        available_orders = db.query(Order).filter(
            ~Order.id.in_(db.query(orders_in_requests.c.order_id))
        ).order_by(Order.created_at.desc()).limit(50).all()
    
    return templates.TemplateResponse("purchase_request_detail.html", {
        "request": http_request,
        "current_user": current_user,
        "purchase_request": purchase_request,
        "aggregated_items": list(aggregated_items.values()),
        "available_orders": available_orders,
        "is_admin": is_admin,
        "active_menu": "orders",
    })


@router.post("/{request_id}/submit", response_class=RedirectResponse)
async def submit_purchase_request(
    request_id: int,
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    """Отправка запроса на закупку партнёром"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    if getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    
    if purchase_request.status not in ["NEW", "draft"]:  # Поддерживаем старые черновики
        raise HTTPException(status_code=400, detail="Можно отправить только новый запрос")
    
    if not purchase_request.orders:
        raise HTTPException(status_code=400, detail="Добавьте хотя бы один заказ")
    
    # Партнёр отправляет запрос - статус остается "NEW" (новый)
    # Статус изменится только когда администратор отправит на подтверждение
    if purchase_request.status == "draft":
        purchase_request.status = "NEW"  # Обновляем старые черновики на NEW
    purchase_request.submitted_at = datetime.utcnow()
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/send_for_approval", response_class=RedirectResponse)
async def send_for_approval(
    request_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Отправка запроса на подтверждение поставщику (только для администратора)"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    # Меняем статус запроса на "PENDING_APPROVAL" (отправлен на подтверждение)
    purchase_request.status = "PENDING_APPROVAL"
    
    # Меняем статус всех позиций со статусом "new" на "confirmation"
    request_items = db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.purchase_request_id == request_id,
        PurchaseRequestItem.status == "new"
    ).all()
    
    items_updated = 0
    for item in request_items:
        item.status = "confirmation"
        items_updated += 1
    
    # Создаём уведомление для партнёра
    if purchase_request.partner and purchase_request.partner.user_id:
        notification = Notification(
            user_id=purchase_request.partner.user_id,
            type="purchase_request_sent_for_approval",
            title=f"Запрос #{request_id} отправлен на подтверждение",
            message=f"Администратор отправил запрос на закупку поставщику. Обновлено позиций: {items_updated}",
            related_type="purchase_request",
            related_id=request_id,
        )
        db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/add_orders", response_class=RedirectResponse)
async def add_orders_to_request(
    request_id: int,
    order_ids: List[int] = Form([]),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Добавление заказов в запрос (только для админа)"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    request_created_at = purchase_request.created_at
    new_items_count = 0
    
    if order_ids:
        orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
        for order in orders:
            if order not in purchase_request.orders:
                purchase_request.orders.append(order)
                # Проверяем, есть ли новые товары (заказ создан после запроса)
                if order.created_at and request_created_at and order.created_at > request_created_at:
                    new_items_count += len(order.items)
    
    # Создаём уведомление для админа о новых товарах
    if new_items_count > 0:
        admin_users = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).all()
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                type="purchase_request_new_item",
                title=f"Новые товары в запросе #{request_id}",
                message=f"В запрос добавлены новые товары ({new_items_count} позиций)",
                related_type="purchase_request",
                related_id=request_id,
            )
            db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/remove_order/{order_id}", response_class=RedirectResponse)
async def remove_order_from_request(
    request_id: int,
    order_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Удаление заказа из запроса"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    if not is_admin and getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    
    # Можно удалять заказы только из нового запроса или черновика
    if purchase_request.status not in ["NEW", "draft"]:
        raise HTTPException(status_code=400, detail="Можно удалять заказы только из нового запроса")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if order and order in purchase_request.orders:
        purchase_request.orders.remove(order)
        db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/update_status", response_class=RedirectResponse)
async def update_request_status(
    request_id: int,
    status: str = Form(...),
    admin_notes: Optional[str] = Form(None),
    actual_delivery_date: Optional[str] = Form(None),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Обновление статуса запроса (только для админа)"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    if status not in ["NEW", "draft", "submitted", "PENDING_APPROVAL", "partially_received", "fully_received", "cancelled"]:
        raise HTTPException(status_code=400, detail="Неверный статус")
    
    purchase_request.status = status
    if admin_notes:
        purchase_request.admin_notes = admin_notes
    
    if actual_delivery_date:
        try:
            purchase_request.actual_delivery_date = datetime.strptime(actual_delivery_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/redistribute", response_class=RedirectResponse)
async def redistribute_request_items(
    request_id: int,
    target_request_id: int = Form(...),
    order_ids: List[int] = Form([]),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Перераспределение заказов из одного запроса в другой"""
    source_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    target_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == target_request_id).first()
    
    if not source_request or not target_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    if source_request.status not in ["NEW", "draft", "submitted"]:
        raise HTTPException(status_code=400, detail="Можно перераспределять только из нового или отправленного запроса")
    
    if order_ids:
        orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
        for order in orders:
            if order in source_request.orders:
                source_request.orders.remove(order)
                if order not in target_request.orders:
                    target_request.orders.append(order)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)

@router.post("/{request_id}/change_price", response_class=RedirectResponse)
async def change_item_price(
    request_id: int,
    order_item_id: int = Form(...),
    new_price: str = Form(...),
    price_change_comment: str = Form(...),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Изменение цены товара в запросе с отправкой на подтверждение"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    order_item = db.query(OrderItem).filter(OrderItem.id == order_item_id).first()
    if not order_item:
        raise HTTPException(status_code=404, detail="Позиция заказа не найдена")
    
    # Проверяем, что позиция относится к заказу в этом запросе
    if order_item.order_id not in [o.id for o in purchase_request.orders]:
        raise HTTPException(status_code=400, detail="Позиция не относится к этому запросу")
    
    try:
        new_price_decimal = Decimal(new_price)
    except:
        raise HTTPException(status_code=400, detail="Неверная цена")
    
    # Создаём или обновляем запись о позиции в запросе
    request_item = db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.purchase_request_id == request_id,
        PurchaseRequestItem.order_item_id == order_item_id
    ).first()
    
    if not request_item:
        request_item = PurchaseRequestItem(
            purchase_request_id=request_id,
            order_item_id=order_item_id,
            original_price=order_item.cost_for_owner,
            proposed_price=new_price_decimal,
            status="pending_approval",
            price_change_comment=price_change_comment,
        )
        db.add(request_item)
    else:
        request_item.proposed_price = new_price_decimal
        request_item.status = "pending_approval"
        request_item.price_change_comment = price_change_comment
    
    # Создаём уведомление для партнёра
    notification = Notification(
        user_id=purchase_request.created_by_user_id,
        type="purchase_request_price_change",
        title=f"Изменение цены в запросе #{request_id}",
        message=f"Админ изменил цену товара. Новая цена: {new_price_decimal}. Комментарий: {price_change_comment}",
        related_type="purchase_request",
        related_id=request_id,
    )
    db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/approve_price/{item_id}", response_class=RedirectResponse)
async def approve_price_change(
    request_id: int,
    item_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Подтверждение изменения цены (партнёр или админ)"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    if not is_admin and getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    
    request_item = db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.id == item_id,
        PurchaseRequestItem.purchase_request_id == request_id
    ).first()
    
    if not request_item:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    
    # Администратор может подтверждать как pending_approval, так и new статусы
    # Партнёр может подтверждать только pending_approval
    if is_admin:
        if request_item.status not in ["pending_approval", "new"]:
            raise HTTPException(status_code=400, detail="Позиция не ожидает подтверждения")
    else:
        if request_item.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Позиция не ожидает подтверждения")
    
    # Обновляем цену в заказе, если есть предложенная цена
    order_item = request_item.order_item
    if order_item:
        if request_item.proposed_price:
            old_price = order_item.cost_for_owner
            order_item.cost_for_owner = request_item.proposed_price
            # Пересчитываем суммы заказа
            from app.services.order_pricing_service import recalc_order_totals
            recalc_order_totals(order_item.order, db)
            request_item.approved_price = request_item.proposed_price
    
    # Если подтверждает администратор, статус меняется на "confirmation" (подтверждение цены)
    # Если подтверждает партнёр, статус меняется на "approved"
    if is_admin:
        request_item.status = "confirmation"
    else:
        request_item.status = "approved"
        if request_item.proposed_price:
            request_item.approved_price = request_item.proposed_price
    
    # Создаём уведомление для админа (если подтвердил партнёр)
    if not is_admin:
        admin_users = db.query(User).join(User.role).filter(User.role.has(name="ADMIN")).all()
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                type="purchase_request_approval",
                title=f"Подтверждена цена в запросе #{request_id}",
                message=f"Партнёр подтвердил изменение цены товара",
                related_type="purchase_request",
                related_id=request_id,
            )
            db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/reject_price/{item_id}", response_class=RedirectResponse)
async def reject_price_change(
    request_id: int,
    item_id: int,
    admin_comment: str = Form(""),
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Отклонение изменения цены"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    if not is_admin and getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    
    request_item = db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.id == item_id,
        PurchaseRequestItem.purchase_request_id == request_id
    ).first()
    
    if not request_item:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    
    request_item.status = "rejected"
    request_item.admin_comment = admin_comment
    
    # Создаём уведомление
    notification = Notification(
        user_id=purchase_request.created_by_user_id if is_admin else purchase_request.partner.user_id,
        type="purchase_request_price_change",
        title=f"Отклонено изменение цены в запросе #{request_id}",
        message=f"Изменение цены отклонено. Комментарий: {admin_comment}",
        related_type="purchase_request",
        related_id=request_id,
    )
    db.add(notification)
    
    db.commit()
    
    return RedirectResponse(url=f"/purchase_requests/{request_id}", status_code=303)


@router.post("/{request_id}/delete", response_class=RedirectResponse)
async def delete_purchase_request(
    request_id: int,
    current_user: User = Depends(require_permission(["orders.view_all", "orders.view_own"])),
    db: Session = Depends(get_db),
):
    """Удаление запроса на закупку"""
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    is_admin = user_has_permission(current_user, db, "orders.view_all")
    
    # Проверка прав доступа
    if not is_admin and getattr(current_user, "partner_id", None) != purchase_request.partner_id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому запросу")
    
    # Можно удалять только новые запросы или отправленные запросы (не полученные)
    if purchase_request.status in ["partially_received", "fully_received", "PENDING_APPROVAL"]:
        raise HTTPException(status_code=400, detail="Нельзя удалить запрос, который уже отправлен на подтверждение или получен")
    
    # Удаляем все связанные PurchaseRequestItem
    db.query(PurchaseRequestItem).filter(
        PurchaseRequestItem.purchase_request_id == request_id
    ).delete()
    
    # Удаляем связи с заказами (связи в purchase_request_orders удалятся автоматически при удалении запроса)
    purchase_request.orders.clear()
    
    # Удаляем сам запрос
    db.delete(purchase_request)
    db.commit()
    
    return RedirectResponse(url="/purchase_requests/", status_code=303)
