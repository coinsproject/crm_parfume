from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Fragrance, PartnerPrice, PriceProduct, PriceHistory, CatalogItem
from app.services.partner_pricing_service import (
    get_total_markup_percent, 
    calc_client_price,
    calc_partner_price,
    get_partner_pricing_policy,
    get_effective_partner_markup_percent
)


def _to_decimal(value: Optional[Decimal]) -> Decimal:
    """Безопасно привести к Decimal, подставляя 0 при None."""
    return Decimal(value or 0)


def fill_item_prices(
    order: Order,
    item: OrderItem,
    fragrance: Optional[Fragrance],
    db: Session,
    price_product: Optional[PriceProduct] = None,
) -> None:
    """
    Подставить цены для позиции в зависимости от партнёра и прайса.
    Заполняет client_price, cost_for_owner и пересчитывает суммы/маржу по строке.
    Цена для клиента рассчитывается с учетом накруток админа и партнера.
    """
    partner_id = order.partner_id
    client_id = order.client_id
    base_price = None  # Базовая цена для клиента (после надбавки на прайс)
    price_1 = None  # Закупочная цена (себестоимость админа)
    price_2 = None  # Цена партнера (себестоимость партнера)
    client_price = None
    cost_for_owner = None
    base_price_raw = None  # Базовая цена из прайса (price_1, fallback price_2)

    # Если price_product не передан, но есть catalog_item, пытаемся получить price_product из него
    if not price_product and item.catalog_item_id:
        catalog_item = db.query(CatalogItem).filter(CatalogItem.id == item.catalog_item_id).first()
        if catalog_item and catalog_item.price_product_id:
            price_product = db.query(PriceProduct).filter(PriceProduct.id == catalog_item.price_product_id).first()

    # Получаем цены из прайса
    if price_product:
        # Берём цены из последней записи PriceHistory
        history = (
            db.query(PriceHistory)
            .filter(PriceHistory.price_product_id == price_product.id)
            .order_by(PriceHistory.created_at.desc())
            .first()
        )
        if history is not None:
            # Сохраняем price_1 и price_2 для расчета маржи
            if history.new_price_1 is not None:
                price_1 = history.new_price_1
            elif history.old_price_1 is not None:
                price_1 = history.old_price_1
            
            if history.new_price_2 is not None:
                price_2 = history.new_price_2
            elif history.price is not None:
                price_2 = history.price
            
            # Базовая цена прайса: предпочитаем price_1
            if price_1 is not None:
                base_price_raw = price_1
            elif price_2 is not None:
                base_price_raw = price_2

    # Если есть партнер и аромат, проверяем PartnerPrice для цены партнера
    # PartnerPrice имеет приоритет над расчетом по прайсу
    if partner_id and fragrance:
        partner_price: Optional[PartnerPrice] = (
            db.query(PartnerPrice)
            .filter(
                PartnerPrice.partner_id == partner_id,
                PartnerPrice.fragrance_id == fragrance.id,
            )
            .first()
        )
        if partner_price:
            cost_for_owner = partner_price.purchase_price_for_partner
            # Если используется PartnerPrice, то price_2 = purchase_price_for_partner для расчета маржи
            if price_2 is None:
                price_2 = partner_price.purchase_price_for_partner
            # Не используем recommended_client_price напрямую, 
            # а применяем накрутки к базовой цене из прайса

    # Fallback на базовые цены аромата (если позиция задана ароматом)
    if fragrance is not None:
        if cost_for_owner is None:
            cost_for_owner = fragrance.base_cost
            if price_1 is None:
                price_1 = fragrance.base_cost
        if base_price is None:
            base_price = fragrance.base_retail_price or fragrance.price
            if price_2 is None:
                price_2 = fragrance.base_retail_price or fragrance.price

    # Рассчитываем цену партнера с учетом надбавки на прайс
    if partner_id is not None:
        try:
            partner_id_int = int(partner_id) if partner_id is not None else None
        except (ValueError, TypeError):
            partner_id_int = None
        if partner_id_int is not None:
            policy = get_partner_pricing_policy(db, partner_id_int)
            partner_price_markup_pct = policy.partner_price_markup_percent
        else:
            partner_price_markup_pct = Decimal(0)
        
        if cost_for_owner is None:
            # Берем базовую цену прайса и применяем надбавку на прайс
            if base_price_raw is None:
                base_price_raw = base_price if base_price is not None else Decimal(0)
            cost_for_owner = calc_partner_price(base_price_raw, partner_price_markup_pct)
        # Для расчетов маржи и клиентской цены используем цену партнера
        price_2 = cost_for_owner
        base_price = cost_for_owner
    else:
        # Для админа базовая цена = price_1 (закупка) / fallback
        if base_price is None:
            base_price = base_price_raw if base_price_raw is not None else Decimal(0)
        if cost_for_owner is None:
            cost_for_owner = price_1 if price_1 is not None else Decimal(0)

    # Последний fallback: чтобы расчёты не падали даже при пустых данных
    if base_price is None:
        base_price = Decimal(0)
    if cost_for_owner is None:
        cost_for_owner = Decimal(0)

    # Применяем накрутки админа и партнера к базовой цене
    # ВАЖНО: накрутки применяются всегда, когда есть partner_id и базовая цена определена
    if partner_id is not None and base_price is not None:
        # Убеждаемся, что partner_id - это целое число
        try:
            partner_id_int = int(partner_id) if partner_id is not None else None
        except (ValueError, TypeError):
            partner_id_int = None
        
        if partner_id_int is not None:
            total_markup = get_total_markup_percent(db, partner_id_int, client_id=client_id)
            client_price = calc_client_price(base_price, total_markup)
        else:
            # Если partner_id невалидный, используем базовую цену без накруток
            client_price = base_price if base_price is not None else Decimal(0)
    else:
        # Если нет партнера, используем базовую цену без накруток
        client_price = base_price if base_price is not None else Decimal(0)

    item.cost_for_owner = cost_for_owner
    item.client_price = client_price

    # Пересчёт сумм и маржи по строке
    unit_client_price = _to_decimal(item.client_price)
    unit_cost = _to_decimal(item.cost_for_owner)
    qty = _to_decimal(item.qty)
    discount = _to_decimal(item.discount)

    item.line_client_amount = unit_client_price * qty - discount
    item.line_cost_amount = unit_cost * qty
    item.line_margin = item.line_client_amount - item.line_cost_amount
    
    # Расчет раздельной маржи админа и партнера
    if partner_id is not None and price_2 is not None:
        # Есть партнер: общая маржа = накрутка от price_2
        unit_price_2 = _to_decimal(price_2)
        
        # Получаем проценты накруток админа и партнера
        # Убеждаемся, что partner_id - это целое число
        try:
            partner_id_int = int(partner_id) if partner_id is not None else None
        except (ValueError, TypeError):
            partner_id_int = None
        
        if partner_id_int is not None:
            policy = get_partner_pricing_policy(db, partner_id_int)
            partner_pct = get_effective_partner_markup_percent(db, partner_id_int, client_id=client_id)
            admin_pct = policy.admin_markup_percent
        else:
            # Fallback если partner_id невалидный
            admin_pct = Decimal(0)
            partner_pct = Decimal(0)
        
        # Общая маржа = накрутка от price_2 (сумма процентов админа и партнера)
        total_markup_pct = admin_pct + partner_pct
        unit_total_margin = unit_price_2 * (total_markup_pct / 100)
        
        # Разделенная маржа: процент админа и партнера от price_2
        unit_admin_margin = unit_price_2 * (admin_pct / 100)
        unit_partner_margin = unit_price_2 * (partner_pct / 100)
        
        item.line_admin_margin = unit_admin_margin * qty
        item.line_partner_margin = unit_partner_margin * qty
        
        # Процент общей маржи считается от price_2
        item.line_margin_percent = (
            (total_markup_pct)
            if unit_price_2 and unit_price_2 > 0
            else None
        )
        
        # Проценты маржи админа и партнера - это проценты из настроек
        item.line_admin_margin_percent = admin_pct if admin_pct > 0 else None
        item.line_partner_margin_percent = partner_pct if partner_pct > 0 else None
        
    elif partner_id is None and price_1 is not None:
        # Нет партнера: вся маржа админа = client_price - price_1
        unit_price_1 = _to_decimal(price_1)
        unit_admin_margin = unit_client_price - unit_price_1
        
        item.line_admin_margin = unit_admin_margin * qty
        item.line_partner_margin = Decimal(0)
        
        # Процент маржи админа считается от себестоимости (price_1)
        item.line_margin_percent = (
            (unit_admin_margin / unit_price_1 * 100)
            if unit_price_1 and unit_price_1 > 0
            else None
        )
        item.line_admin_margin_percent = item.line_margin_percent
        item.line_partner_margin_percent = None
    else:
        # Fallback: используем общую маржу
        item.line_admin_margin = item.line_margin
        item.line_partner_margin = Decimal(0)
        item.line_margin_percent = (
            (item.line_margin / item.line_cost_amount * 100)
            if item.line_cost_amount and item.line_cost_amount > 0
            else None
        )
        item.line_admin_margin_percent = item.line_margin_percent
        item.line_partner_margin_percent = None

    # Для обратной совместимости можно дублировать цену в старое поле price
    item.price = item.client_price


def recalc_order_totals(order: Order, db: Session) -> None:
    """Пересчитать суммы и маржу заказа на основе позиций."""
    total_client = Decimal(0)
    total_cost = Decimal(0)
    total_admin_margin = Decimal(0)
    total_partner_margin = Decimal(0)

    for item in order.items or []:
        total_client += _to_decimal(item.line_client_amount)
        total_cost += _to_decimal(item.line_cost_amount)
        total_admin_margin += _to_decimal(item.line_admin_margin) if hasattr(item, 'line_admin_margin') and item.line_admin_margin is not None else Decimal(0)
        total_partner_margin += _to_decimal(item.line_partner_margin) if hasattr(item, 'line_partner_margin') and item.line_partner_margin is not None else Decimal(0)

    order.total_client_amount = total_client
    order.total_cost_for_owner = total_cost
    order.total_margin_for_owner = total_client - total_cost
    order.total_admin_margin = total_admin_margin
    order.total_partner_margin = total_partner_margin
    
    if order.partner_id is not None:
        # Есть партнер: общая маржа = накрутка от price_2
        # Получаем проценты накруток админа и партнера
        # Убеждаемся, что partner_id - это целое число
        try:
            partner_id_int = int(order.partner_id) if order.partner_id is not None else None
        except (ValueError, TypeError):
            partner_id_int = None
        
        if partner_id_int is not None:
            policy = get_partner_pricing_policy(db, partner_id_int)
            partner_pct = get_effective_partner_markup_percent(db, partner_id_int, client_id=order.client_id)
            admin_pct = policy.admin_markup_percent
        else:
            # Fallback если partner_id невалидный
            admin_pct = Decimal(0)
            partner_pct = Decimal(0)
        
        # Общая маржа = сумма процентов админа и партнера (накрутка от price_2)
        total_markup_pct = admin_pct + partner_pct
        
        # Проценты маржи админа и партнера - это проценты из настроек
        order.total_admin_margin_percent = admin_pct if admin_pct > 0 else None
        order.total_partner_margin_percent = partner_pct if partner_pct > 0 else None
        
        # Общий процент маржи = сумма процентов админа и партнера
        order.total_margin_percent = total_markup_pct if total_markup_pct > 0 else None
    else:
        # Нет партнера: процент маржи считается от себестоимости
        order.total_margin_percent = (
            (order.total_margin_for_owner / total_cost * 100) if total_cost and total_cost > 0 else None
        )
        order.total_admin_margin_percent = order.total_margin_percent
        order.total_partner_margin_percent = None

    # Сохраняем сумму в legacy поле total_amount для существующих экранов
    order.total_amount = order.total_client_amount
