from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Fragrance, PartnerPrice, PriceProduct, PriceHistory


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
    """
    partner_id = order.partner_id
    client_price = None
    cost_for_owner = None

    if price_product:
        # Берём цену из последней записи PriceHistory (база: new_price_2, fallback: price)
        history = (
            db.query(PriceHistory)
            .filter(PriceHistory.price_product_id == price_product.id)
            .order_by(PriceHistory.created_at.desc())
            .first()
        )
        if history is not None:
            val = history.new_price_2 if history.new_price_2 is not None else history.price
            if val is not None:
                client_price = val

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
            client_price = partner_price.recommended_client_price

    # Fallback на базовые цены аромата (если позиция задана ароматом)
    if fragrance is not None:
        if cost_for_owner is None:
            cost_for_owner = fragrance.base_cost
        if client_price is None:
            client_price = fragrance.base_retail_price or fragrance.price

    # Последний fallback: чтобы расчёты не падали даже при пустых данных
    if cost_for_owner is None:
        cost_for_owner = Decimal(0)
    if client_price is None:
        client_price = Decimal(0)

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
    item.line_margin_percent = (
        (item.line_margin / item.line_client_amount * 100)
        if item.line_client_amount
        else None
    )

    # Для обратной совместимости можно дублировать цену в старое поле price
    item.price = item.client_price


def recalc_order_totals(order: Order) -> None:
    """Пересчитать суммы и маржу заказа на основе позиций."""
    total_client = Decimal(0)
    total_cost = Decimal(0)

    for item in order.items or []:
        total_client += _to_decimal(item.line_client_amount)
        total_cost += _to_decimal(item.line_cost_amount)

    order.total_client_amount = total_client
    order.total_cost_for_owner = total_cost
    order.total_margin_for_owner = total_client - total_cost
    order.total_margin_percent = (
        (order.total_margin_for_owner / total_client * 100) if total_client else None
    )

    # Сохраняем сумму в legacy поле total_amount для существующих экранов
    order.total_amount = order.total_client_amount
