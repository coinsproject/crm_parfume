"""
REST API для мобильных приложений
Поддерживает аутентификацию через Bearer токен в заголовке Authorization
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal

from app.db import get_db
from app.models import User, Client, Order, OrderItem, Partner, Notification
from app.services.auth_service import get_current_user_from_request, require_permission, user_has_permission
from app.routes.clients import _get_filters_for_user
from app.routes.orders import ORDER_STATUSES, ORDER_STATUS_LABELS

router = APIRouter(prefix="/api/v1", tags=["mobile_api"])


# Pydantic схемы для валидации данных

class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None  # Используем str вместо EmailStr для гибкости
    city: Optional[str] = None
    notes: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    can_access_catalog: bool = False


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None  # Используем str вместо EmailStr для гибкости
    city: Optional[str] = None
    notes: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    can_access_catalog: Optional[bool] = None


class ClientResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    city: Optional[str]
    notes: Optional[str]
    telegram: Optional[str]
    instagram: Optional[str]
    can_access_catalog: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderItemCreate(BaseModel):
    fragrance_id: Optional[int] = None
    price_product_id: Optional[int] = None
    catalog_item_id: Optional[int] = None
    qty: int
    discount: Optional[Decimal] = None


class OrderCreate(BaseModel):
    client_id: int
    partner_id: Optional[int] = None
    status: str = "NEW"
    payment_method: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_tracking: Optional[str] = None
    items: List[OrderItemCreate]


class OrderUpdate(BaseModel):
    client_id: Optional[int] = None
    partner_id: Optional[int] = None
    status: Optional[str] = None
    payment_method: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_tracking: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: int
    fragrance_id: Optional[int]
    price_product_id: Optional[int]
    catalog_item_id: Optional[int]
    qty: int
    discount: Optional[Decimal]
    client_price: Optional[Decimal]
    cost_for_owner: Optional[Decimal]
    line_client_amount: Optional[Decimal]
    line_cost_amount: Optional[Decimal]
    line_margin: Optional[Decimal]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    client_id: int
    partner_id: Optional[int]
    status: str
    total_amount: Decimal
    total_client_amount: Optional[Decimal]
    payment_method: Optional[str]
    delivery_type: Optional[str]
    delivery_tracking: Optional[str]
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True


# Зависимость для получения текущего пользователя из токена
async def get_current_user_api(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Получение текущего пользователя из Bearer токена"""
    user = await get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ========== КЛИЕНТЫ ==========

@router.get("/clients", response_model=List[ClientResponse])
async def get_clients_api(
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Получить список клиентов"""
    if not user_has_permission(current_user, db, "clients.view_all") and not user_has_permission(current_user, db, "clients.view_own"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    query = db.query(Client)
    filters = _get_filters_for_user(current_user, can_view_all, q=q or "")
    for flt in filters:
        query = query.filter(flt)
    
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    
    clients = query.order_by(Client.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return clients


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client_api(
    client_id: int,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Получить клиента по ID"""
    if not user_has_permission(current_user, db, "clients.view_all") and not user_has_permission(current_user, db, "clients.view_own"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    if not can_view_all:
        can_view_own = user_has_permission(current_user, db, "clients.view_own")
        if can_view_own:
            partner_id = getattr(current_user, "partner_id", None)
            if not (client.owner_user_id == current_user.id or 
                   client.owner_partner_id == partner_id or 
                   client.partner_id == partner_id or
                   client.created_by_user_id == current_user.id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    return client


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client_api(
    client_data: ClientCreate,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Создать нового клиента"""
    if not user_has_permission(current_user, db, "clients.create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Валидация
    if not client_data.name or not client_data.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Имя клиента обязательно")
    
    phone_clean = "".join(ch for ch in (client_data.phone or "") if ch.isdigit())
    if client_data.phone and len(phone_clean) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Телефон должен содержать минимум 10 цифр")
    
    # Определяем owner
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    owner_user_id = None
    owner_partner_id = None
    partner_id_value = None
    
    if can_view_all:
        # Админ может не указывать партнёра
        partner_id_value = None
    else:
        owner_user_id = current_user.id
        owner_partner_id = getattr(current_user, "partner_id", None)
        partner_id_value = owner_partner_id
    
    client = Client(
        name=client_data.name.strip(),
        phone=client_data.phone,
        email=client_data.email,
        city=client_data.city,
        notes=client_data.notes,
        telegram=client_data.telegram,
        instagram=client_data.instagram,
        partner_id=partner_id_value,
        owner_user_id=owner_user_id,
        owner_partner_id=owner_partner_id,
        created_by_user_id=current_user.id,
        can_access_catalog=client_data.can_access_catalog
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    
    return client


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client_api(
    client_id: int,
    client_data: ClientUpdate,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Обновить клиента"""
    if not user_has_permission(current_user, db, "clients.create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    if not can_view_all:
        partner_id = getattr(current_user, "partner_id", None)
        if not (client.owner_user_id == current_user.id or 
               client.owner_partner_id == partner_id or 
               client.partner_id == partner_id or
               client.created_by_user_id == current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Обновляем поля
    if client_data.name is not None:
        client.name = client_data.name.strip()
    if client_data.phone is not None:
        phone_clean = "".join(ch for ch in client_data.phone if ch.isdigit())
        if client_data.phone and len(phone_clean) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Телефон должен содержать минимум 10 цифр")
        client.phone = client_data.phone
    if client_data.email is not None:
        client.email = client_data.email
    if client_data.city is not None:
        client.city = client_data.city
    if client_data.notes is not None:
        client.notes = client_data.notes
    if client_data.telegram is not None:
        client.telegram = client_data.telegram
    if client_data.instagram is not None:
        client.instagram = client_data.instagram
    if client_data.can_access_catalog is not None:
        client.can_access_catalog = client_data.can_access_catalog
    
    db.commit()
    db.refresh(client)
    
    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_api(
    client_id: int,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Удалить клиента"""
    if not user_has_permission(current_user, db, "clients.create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    if not can_view_all:
        partner_id = getattr(current_user, "partner_id", None)
        if not (client.owner_user_id == current_user.id or 
               client.owner_partner_id == partner_id or 
               client.partner_id == partner_id or
               client.created_by_user_id == current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Проверяем наличие связанных заказов
    from app.models import Order, PartnerClientMarkup
    orders_count = db.query(Order).filter(Order.client_id == client_id).count()
    if orders_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Невозможно удалить клиента: у него есть {orders_count} заказ(ов). Сначала удалите или измените заказы."
        )
    
    # Удаляем связанные накрутки партнера
    try:
        db.query(PartnerClientMarkup).filter(PartnerClientMarkup.client_id == client_id).delete(synchronize_session=False)
        db.delete(client)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при удалении клиента: {str(e)}"
        )
    
    return None


# ========== ЗАКАЗЫ ==========

@router.get("/orders", response_model=List[OrderResponse])
async def get_orders_api(
    page: int = 1,
    page_size: int = 50,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Получить список заказов"""
    if not user_has_permission(current_user, db, "orders.view_all") and not user_has_permission(current_user, db, "orders.view_own"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    query = db.query(Order)
    
    if not can_view_all:
        can_view_own = user_has_permission(current_user, db, "orders.view_own")
        if can_view_own:
            partner_id = getattr(current_user, "partner_id", None)
            query = query.filter(
                (Order.created_by_user_id == current_user.id) |
                (Order.partner_id == partner_id)
            )
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return orders


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order_api(
    order_id: int,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Получить заказ по ID"""
    if not user_has_permission(current_user, db, "orders.view_all") and not user_has_permission(current_user, db, "orders.view_own"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    if not can_view_all:
        can_view_own = user_has_permission(current_user, db, "orders.view_own")
        if can_view_own:
            partner_id = getattr(current_user, "partner_id", None)
            if not (order.created_by_user_id == current_user.id or order.partner_id == partner_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    return order


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order_api(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Создать новый заказ"""
    if not user_has_permission(current_user, db, "orders.create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Проверяем клиента
    client = db.query(Client).filter(Client.id == order_data.client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    
    # Проверяем статус
    valid_statuses = [code for code, _ in ORDER_STATUSES]
    if order_data.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неверный статус. Допустимые: {', '.join(valid_statuses)}")
    
    # Определяем partner_id
    partner_id = order_data.partner_id
    if not partner_id:
        partner_id = getattr(current_user, "partner_id", None)
    
    # Создаем заказ
    order = Order(
        client_id=order_data.client_id,
        partner_id=partner_id,
        created_by_user_id=current_user.id,
        status=order_data.status,
        payment_method=order_data.payment_method,
        delivery_type=order_data.delivery_type,
        delivery_tracking=order_data.delivery_tracking,
        total_amount=Decimal(0),
        total_client_amount=Decimal(0),
    )
    db.add(order)
    db.flush()
    
    # Добавляем позиции
    from app.services.order_pricing_service import fill_item_prices
    from app.models import Fragrance, PriceProduct, CatalogItem
    
    for item_data in order_data.items:
        fragrance = None
        price_product = None
        
        if item_data.fragrance_id:
            fragrance = db.query(Fragrance).filter(Fragrance.id == item_data.fragrance_id).first()
        elif item_data.price_product_id:
            price_product = db.query(PriceProduct).filter(PriceProduct.id == item_data.price_product_id).first()
        elif item_data.catalog_item_id:
            catalog_item = db.query(CatalogItem).filter(CatalogItem.id == item_data.catalog_item_id).first()
            if catalog_item and catalog_item.price_product_id:
                price_product = db.query(PriceProduct).filter(PriceProduct.id == catalog_item.price_product_id).first()
            if catalog_item and catalog_item.fragrance_id:
                fragrance = db.query(Fragrance).filter(Fragrance.id == catalog_item.fragrance_id).first()
        
        item = OrderItem(
            order_id=order.id,
            fragrance_id=item_data.fragrance_id,
            price_product_id=item_data.price_product_id,
            catalog_item_id=item_data.catalog_item_id,
            qty=item_data.qty,
            discount=item_data.discount or Decimal(0),
        )
        fill_item_prices(order, item, fragrance, db, price_product)
        order.items.append(item)
    
    # Пересчитываем итоги
    from app.services.order_pricing_service import recalc_order_totals
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
    
    return order


@router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order_api(
    order_id: int,
    order_data: OrderUpdate,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Обновить заказ"""
    if not user_has_permission(current_user, db, "orders.create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    
    # Проверка прав доступа
    can_view_all = user_has_permission(current_user, db, "orders.view_all")
    if not can_view_all:
        can_view_own = user_has_permission(current_user, db, "orders.view_own")
        if can_view_own:
            partner_id = getattr(current_user, "partner_id", None)
            if not (order.created_by_user_id == current_user.id or order.partner_id == partner_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Обновляем поля
    if order_data.client_id is not None:
        client = db.query(Client).filter(Client.id == order_data.client_id).first()
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
        order.client_id = order_data.client_id
    
    if order_data.partner_id is not None:
        order.partner_id = order_data.partner_id
    
    if order_data.status is not None:
        valid_statuses = [code for code, _ in ORDER_STATUSES]
        if order_data.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неверный статус. Допустимые: {', '.join(ORDER_STATUSES)}")
        order.status = order_data.status
    
    if order_data.payment_method is not None:
        order.payment_method = order_data.payment_method
    
    if order_data.delivery_type is not None:
        order.delivery_type = order_data.delivery_type
    
    if order_data.delivery_tracking is not None:
        order.delivery_tracking = order_data.delivery_tracking
    
    db.commit()
    db.refresh(order)
    
    return order


# ========== ПОИСК ПРАЙСА ==========

@router.get("/price/search")
async def search_price_api(
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    client_id: Optional[int] = None,
    partner_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Поиск в прайсе"""
    if not user_has_permission(current_user, db, "price.search"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    
    # Используем существующий эндпоинт из orders.py
    from app.routes.orders import order_price_search_api
    
    return await order_price_search_api(
        q=q,
        page=page,
        page_size=page_size,
        client_id=str(client_id) if client_id else None,
        partner_id=str(partner_id) if partner_id else None,
        current_user=current_user,
        db=db
    )


# ========== АУТЕНТИФИКАЦИЯ ==========

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


@router.post("/auth/login", response_model=LoginResponse)
async def login_api(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Вход через API (возвращает Bearer токен)"""
    from app.services.auth_service import verify_password, create_access_token
    from datetime import timedelta
    from app.config import settings
    
    user = db.query(User).filter(
        User.username == login_data.username,
        User.deleted_at.is_(None)
    ).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль"
        )
    
    # Проверяем 2FA (если включена)
    if user.totp_secret:
        # Для мобильных приложений можно вернуть флаг о необходимости 2FA
        # или требовать 2FA в отдельном эндпоинте
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Требуется двухфакторная аутентификация. Используйте /api/v1/auth/2fa/verify"
        )
    
    # Создаем токен
    access_token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role_id": user.role_id
    }
    access_token = create_access_token(
        data=access_token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username
    }


# ========== ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ ==========

@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db)
):
    """Получить информацию о текущем пользователе"""
    from app.services.auth_service import get_user_permission_keys
    
    permissions = get_user_permission_keys(current_user, db)
    partner_id = getattr(current_user, "partner_id", None)
    
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "partner_id": partner_id,
        "permissions": list(permissions),
        "is_admin": "*" in permissions
    }

