import re
from sqlalchemy.orm import Session

from app.models import PriceProduct


def _strip_volume(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[ ,]*\d+(?:[.,]\d+)?\s*(мл|ml|г|гр|g)\.?$", "", text, flags=re.IGNORECASE)
    return cleaned.strip(" ,.-")


def _detect_kind(text: str) -> str:
    tlow = (text or "").lower()
    if any(k in tlow for k in ["шампун", "shampoo"]):
        return "shampoo"
    if any(k in tlow for k in ["маск", "mask"]):
        return "mask"
    if any(k in tlow for k in ["кондиционер", "conditioner", "бальзам"]):
        return "conditioner"
    if any(k in tlow for k in ["парфюм", "духи", "toilette", "parfum"]):
        return "perfume"
    return "product"


def normalize_price_product(pp: PriceProduct) -> dict:
    """
    Заглушка для ИИ-нормализации прайсовой строки.
    Возвращает словарь с ai_* полями.
    """
    brand = (pp.ai_brand or pp.brand or "").strip()
    base_raw = (pp.ai_base_name or pp.product_name or pp.raw_name or "").strip()
    base_name = _strip_volume(base_raw)
    kind_text = pp.ai_kind or pp.category or base_raw
    ai_kind = _detect_kind(kind_text)
    ai_group_key = None
    if brand or base_name:
        ai_group_key = f"{brand}|{base_name}"
    return {
        "ai_brand": brand,
        "ai_base_name": base_name or base_raw,
        "ai_line": pp.ai_line,
        "ai_kind": ai_kind,
        "ai_group_key": ai_group_key,
    }


def apply_ai_normalization(db: Session, pp: PriceProduct) -> None:
    try:
        data = normalize_price_product(pp)
        pp.ai_brand = data.get("ai_brand")
        pp.ai_base_name = data.get("ai_base_name")
        pp.ai_line = data.get("ai_line")
        pp.ai_kind = data.get("ai_kind")
        pp.ai_group_key = data.get("ai_group_key")
        pp.ai_status = "ok" if pp.ai_group_key else "failed"
    except Exception:
        pp.ai_status = "failed"
    db.add(pp)
