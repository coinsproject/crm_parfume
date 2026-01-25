from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Partner, PartnerClientMarkup


@dataclass(frozen=True)
class PartnerPricingPolicy:
    admin_markup_percent: Decimal
    max_partner_markup_percent: Optional[Decimal]
    partner_default_markup_percent: Decimal
    partner_price_markup_percent: Decimal


def _to_decimal(value) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _quantize_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_partner_pricing_policy(db: Session, partner_id: int) -> PartnerPricingPolicy:
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        return PartnerPricingPolicy(
            admin_markup_percent=Decimal("0"),
            max_partner_markup_percent=None,
            partner_default_markup_percent=Decimal("0"),
            partner_price_markup_percent=Decimal("0"),
        )
    max_partner = _to_decimal(partner.max_partner_markup_percent) if partner.max_partner_markup_percent is not None else None
    # Безопасное получение partner_price_markup_percent (на случай, если миграция еще не применена)
    partner_price_markup = getattr(partner, 'partner_price_markup_percent', None)
    return PartnerPricingPolicy(
        admin_markup_percent=_quantize_percent(_to_decimal(partner.admin_markup_percent)),
        max_partner_markup_percent=_quantize_percent(max_partner) if max_partner is not None else None,
        partner_default_markup_percent=_quantize_percent(_to_decimal(partner.partner_default_markup_percent)),
        partner_price_markup_percent=_quantize_percent(_to_decimal(partner_price_markup)),
    )


def get_partner_markup_for_client(db: Session, partner_id: int, client_id: int) -> Optional[Decimal]:
    row = (
        db.query(PartnerClientMarkup)
        .filter(
            PartnerClientMarkup.partner_id == partner_id,
            PartnerClientMarkup.client_id == client_id,
        )
        .first()
    )
    if not row:
        return None
    return _quantize_percent(_to_decimal(row.partner_markup_percent))


def get_effective_partner_markup_percent(
    db: Session,
    partner_id: int,
    client_id: Optional[int] = None,
) -> Decimal:
    """
    Возвращает процент партнёра (без админской надбавки) для расчёта цены клиенту.
    Если для клиента есть override — используется он, иначе partner_default_markup_percent.
    """
    policy = get_partner_pricing_policy(db, partner_id)
    value = policy.partner_default_markup_percent
    if client_id is not None:
        override = get_partner_markup_for_client(db, partner_id, client_id)
        if override is not None:
            value = override

    if policy.max_partner_markup_percent is not None:
        value = min(value, policy.max_partner_markup_percent)
    return _quantize_percent(max(Decimal("0"), value))


def get_total_markup_percent(
    db: Session,
    partner_id: int,
    client_id: Optional[int] = None,
) -> Decimal:
    policy = get_partner_pricing_policy(db, partner_id)
    partner_pct = get_effective_partner_markup_percent(db, partner_id, client_id=client_id)
    total = policy.admin_markup_percent + partner_pct
    return _quantize_percent(max(Decimal("0"), total))


def calc_client_price(
    base_price: Decimal,
    total_markup_percent: Decimal,
) -> Decimal:
    """
    base_price: базовая цена (например price_2 из прайса)
    total_markup_percent: admin + partner percent
    """
    base = _to_decimal(base_price)
    pct = _to_decimal(total_markup_percent)
    result = base * (Decimal("1") + pct / Decimal("100"))
    return _quantize_money(result)


def calc_partner_price(
    base_price: Decimal,
    partner_price_markup_percent: Decimal,
) -> Decimal:
    """
    base_price: базовая цена (например price_1 из прайса)
    partner_price_markup_percent: надбавка на прайс для партнёра
    """
    base = _to_decimal(base_price)
    pct = _to_decimal(partner_price_markup_percent)
    result = base * (Decimal("1") + pct / Decimal("100"))
    return _quantize_money(result)

