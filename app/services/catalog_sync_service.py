from datetime import datetime
import re
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.models import CatalogItem, PriceProduct, CatalogVariant


def parse_fragrance_from_raw_name(pp: PriceProduct) -> Dict[str, Any]:
    """
    Грубый парсер строки прайса: извлекает бренд, название аромата, пол, тип, объём и флаг тестера.
    """
    brand = (pp.brand or "").strip()
    raw = (pp.raw_name or pp.product_name or "").strip()
    # убираем бренд из начала строки (игнорируем ведущие цифры)
    raw_no_brand = raw
    if brand:
        cleaned = re.sub(r"^[0-9]+\s*", "", raw, flags=re.IGNORECASE)
        if cleaned.lower().startswith(brand.lower()):
            raw_no_brand = cleaned[len(brand):].strip()
    # если есть иерархия через ">", берём последний сегмент
    if ">" in raw_no_brand:
        segments = [seg.strip() for seg in raw_no_brand.split(">") if seg.strip()]
        if segments:
            raw_no_brand = segments[-1]

    # tester
    is_tester = "(тестер" in raw_no_brand.lower()

    # gender
    gender = None
    if "унисекс" in raw_no_brand.lower():
        gender = "Унисекс"
    elif "жен" in raw_no_brand.lower():
        gender = "Женский"
    elif "муж" in raw_no_brand.lower():
        gender = "Мужской"
    elif pp.gender:
        gender_map = {"U": "Унисекс", "F": "Женский", "M": "Мужской"}
        gender = gender_map.get(str(pp.gender).upper(), pp.gender)

    # kind
    kind = None
    for k in ["парфюмерная вода", "туалетная вода", "духи", "парфюмированная вода", "eau de parfum", "eau de toilette"]:
        if k in raw_no_brand.lower():
            kind = k
            break
    if not kind and pp.category:
        kind = pp.category

    # volume
    volume_value = pp.volume_value
    volume_unit = pp.volume_unit
    if volume_value is None or not volume_unit:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(мл|ml|г|gr|g)", raw_no_brand, re.IGNORECASE)
        if m:
            try:
                volume_value = Decimal(m.group(1).replace(",", "."))
            except Exception:
                volume_value = None
            volume_unit = m.group(2)

    # fragrance name — убираем гендер, тип, объем, tester
    fragrance_name = raw_no_brand
    # удаляем скобки (тестер)
    fragrance_name = re.sub(r"\(тестер\)", "", fragrance_name, flags=re.IGNORECASE)
    if gender:
        fragrance_name = re.sub(gender, "", fragrance_name, flags=re.IGNORECASE)
    if kind:
        fragrance_name = re.sub(kind, "", fragrance_name, flags=re.IGNORECASE)
    fragrance_name = re.sub(r"\d+(?:[.,]\d+)?\s*(мл|ml|г|gr|g)", "", fragrance_name, flags=re.IGNORECASE)
    fragrance_name = re.sub(r"[ \t,\.]+$", "", fragrance_name)
    if brand and fragrance_name.lower().startswith(brand.lower()):
        fragrance_name = fragrance_name[len(brand):].strip()
    fragrance_name = re.sub(r"\s{2,}", " ", fragrance_name).strip(" -_,")
    if not fragrance_name:
        fragrance_name = pp.product_name or raw_no_brand or brand

    return {
        "brand": brand,
        "fragrance_name": fragrance_name.strip(),
        "gender": gender,
        "kind": kind,
        "is_tester": bool(is_tester),
        "volume_value": volume_value,
        "volume_unit": volume_unit,
    }


def sync_catalog_from_price(db: Session) -> None:
    """Синхронизация прайса в каталог (items + variants)."""
    products = db.query(PriceProduct).all()

    # кэш существующих items по (brand, fragrance_name)
    items_map: Dict[tuple, CatalogItem] = {
        (ci.brand or "", ci.name): ci for ci in db.query(CatalogItem).all()
    }
    variants_map: Dict[int, CatalogVariant] = {
        v.price_product_id: v for v in db.query(CatalogVariant).all()
    }

    for pp in products:
        parsed = parse_fragrance_from_raw_name(pp)
        is_ai_ok = pp.ai_status == "ok" and bool(pp.ai_group_key)
        brand = (pp.ai_brand if is_ai_ok else parsed.get("brand") or pp.brand or "").strip()
        base_name = (pp.ai_base_name if is_ai_ok else parsed.get("fragrance_name") or pp.product_name or pp.raw_name or f"PP-{pp.id}").strip()
        frag_name = base_name
        kind_value = (pp.ai_kind if is_ai_ok else None) or parsed.get("kind") or (pp.category if pp.category else None)
        gender_value = parsed.get("gender") or pp.gender
        display_name = f"{brand} {frag_name}".strip()
        key = (brand, frag_name)

        item = items_map.get(key)
        if not item:
            default_desc = None
            if not is_ai_ok:
                default_desc = f"{display_name}. Товар из прайса. Описание будет дополнено."
            item = CatalogItem(
                article=pp.external_article,
                brand=brand,
                name=frag_name,
                display_name=display_name,
                type=kind_value,
                gender=gender_value,
                description_short=default_desc,
                visible=True,
                in_stock=False,
            )
            db.add(item)
            db.flush()
            items_map[key] = item
        else:
            # обновляем только пустые поля, чтобы не трогать админские правки
            if not item.display_name:
                item.display_name = display_name
            if not item.type and kind_value:
                item.type = kind_value
            if not item.gender and gender_value:
                item.gender = gender_value
            if not item.description_short and not is_ai_ok:
                item.description_short = f"{display_name}. Товар из прайса. Описание будет дополнено."

        variant = variants_map.get(pp.id)
        in_stock = bool(pp.is_in_stock if pp.is_in_stock is not None else pp.is_active)
        if not variant:
            variant = CatalogVariant(
                catalog_item_id=item.id,
                price_product_id=pp.id,
                volume_value=parsed.get("volume_value") or pp.volume_value,
                volume_unit=parsed.get("volume_unit") or pp.volume_unit,
                is_tester=parsed.get("is_tester", False),
                gender=gender_value,
                kind=kind_value,
                in_stock=in_stock,
                request_payload=pp.raw_name,
            )
            db.add(variant)
            variants_map[pp.id] = variant
        else:
            variant.catalog_item_id = item.id
            variant.volume_value = parsed.get("volume_value") or pp.volume_value
            variant.volume_unit = parsed.get("volume_unit") or pp.volume_unit
            variant.is_tester = parsed.get("is_tester", False)
            variant.gender = gender_value
            variant.kind = kind_value
            variant.in_stock = in_stock
            variant.request_payload = pp.raw_name

    # Обновляем in_stock карточек: если есть хоть один активный вариант
    db.flush()
    items_with_stock = (
        db.query(CatalogVariant.catalog_item_id)
        .filter(CatalogVariant.in_stock.is_(True))
        .distinct()
        .all()
    )
    stock_ids = {row.catalog_item_id for row in items_with_stock}
    db.query(CatalogItem).update({"in_stock": False}, synchronize_session=False)
    if stock_ids:
        # SQLite ограничивает количество параметров в IN, поэтому обновляем батчами
        stock_ids_list = list(stock_ids)
        chunk_size = 900
        for i in range(0, len(stock_ids_list), chunk_size):
            chunk = stock_ids_list[i : i + chunk_size]
            db.query(CatalogItem).filter(CatalogItem.id.in_(chunk)).update(
                {"in_stock": True}, synchronize_session=False
            )
    db.commit()
