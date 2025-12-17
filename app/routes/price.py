from datetime import datetime, date
from decimal import Decimal, ROUND_CEILING, InvalidOperation
import re
import time
from typing import List, Dict, Any
from io import BytesIO

from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db import get_db
from app.models import User, PriceProduct, PriceHistory, PriceUpload, OrderItem, Client
from app.services.auth_service import require_permission, user_has_permission
from app.services.catalog_sync_service import sync_catalog_from_price
from app.services.partner_pricing_service import get_partner_pricing_policy, get_total_markup_percent, calc_client_price
from app.logging_config import price_logger

router = APIRouter(prefix="/price", tags=["price"])
templates = Jinja2Templates(directory="app/templates")


def _parse_raw_name(raw: str) -> Dict[str, Any]:
    """Parse brand/volume/gender/category/product_name from raw_name without mutating raw."""
    if not raw:
        return {
            "brand": "",
            "product_name": "",
            "category": "",
            "volume_value": None,
            "volume_unit": None,
            "gender": None,
        }

    # 2.1 нормализация
    raw_norm = " ".join(raw.strip().split())

    # 2.2 объем
    vol_match = re.search(r"(\d+(?:[.,]\d+)?)(\s*)(мл|ml|г|гр|g)", raw_norm, re.IGNORECASE)
    volume_value = None
    volume_unit = None
    if vol_match:
        volume_value = Decimal(vol_match.group(1).replace(",", "."))
        unit_raw = vol_match.group(3).lower()
        if unit_raw in ["мл", "ml"]:
            volume_unit = "мл"
        elif unit_raw in ["г", "гр", "g"]:
            volume_unit = "г"

    raw_low = raw_norm.lower()

    # 2.3 gender
    gender = None
    if "жен" in raw_low:
        gender = "F"
    elif "муж" in raw_low:
        gender = "M"
    elif "унис" in raw_low:
        gender = "U"

    # 2.5 category
    category = ""
    category_keywords = [
        ("шампунь против перхоти", "Уход за волосами"),
        ("парфюмированная вода", "Парфюм"),
        ("туалетная вода", "Парфюм"),
        ("духи", "Парфюм"),
        ("шампунь", "Уход за волосами"),
        ("маска для волос", "Уход за волосами"),
        ("спрей для волос", "Уход за волосами"),
        ("губная помада", "Декоративная косметика"),
        ("тональный крем", "Декоративная косметика"),
        ("пудра", "Декоративная косметика"),
        ("сыворотка для лица", "Уход за кожей"),
        ("сыворотка для глаз", "Уход за кожей"),
        ("крем для лица", "Уход за кожей"),
    ]
    for kw, cat in category_keywords:
        if kw in raw_low:
            category = cat
            break

    # 2.4 бренд
    brand = ""
    product_name = raw_norm

    def detect_brand(text: str) -> str:
        # Если иерархия с '>' - берём первый сегмент после удаления ведущих чисел/мусора
        if ">" in text:
            segments = [seg.strip() for seg in text.split(">") if seg.strip()]
            if segments:
                seg = re.sub(r"^[0-9]+\s*", "", segments[0])
                seg = re.sub(r"^[^A-Za-zА-Яа-яЁё]+", "", seg)
                first_token = seg.split()[0] if seg else ""
                return first_token.title()
        tokens = text.split()
        brand_tokens = []
        started = False
        for tok in tokens:
            if not started and tok.isdigit():
                continue
            started = True
            if re.search(r"[а-яё]", tok, re.IGNORECASE):
                break
            if tok.lower() in {"женский", "мужской", "унисекс"}:
                break
            brand_tokens.append(tok)
        if brand_tokens:
            return " ".join(brand_tokens)
        return tokens[0] if tokens else ""

    brand = detect_brand(raw_norm)

    # 2.6 product_name: убираем бренд в начале, гендерные слова и объем
    product_part = raw_norm
    if ">" in raw_norm:
        segments = [seg.strip() for seg in raw_norm.split(">") if seg.strip()]
        if segments:
            product_part = segments[-1]
    if brand and product_part.lower().startswith(brand.lower()):
        product_part = product_part[len(brand):].strip()
    # убираем объемное совпадение
    if vol_match:
        product_part = re.sub(r"[ ,]*\d+(?:[.,]\d+)?\s*(мл|ml|г|гр|g)$", "", product_part, flags=re.IGNORECASE)
    product_part = re.sub(r"[ \t,\\.]+$", "", product_part)
    # убираем половые маркеры
    for marker in ["женский", "мужской", "унисекс"]:
        product_part = re.sub(marker, "", product_part, flags=re.IGNORECASE)
    product_part = " ".join(product_part.split()).strip()
    if not product_part:
        product_part = raw_norm

    return {
        "brand": brand,
        "product_name": product_part,
        "category": category,
        "volume_value": volume_value,
        "volume_unit": volume_unit,
        "gender": gender,
    }


def _get_latest_price(price_product: PriceProduct) -> Decimal:
    if not price_product.price_history:
        return Decimal(0)
    last = sorted(price_product.price_history, key=lambda h: h.created_at or datetime.min)[-1]
    return Decimal((last.new_price_2 if last.new_price_2 is not None else last.price) or 0)


def _calc_price_fields(price_1: Decimal) -> (Decimal, Decimal):
    """Возвращает округленную цену для партнёра и delta."""
    # Правило округления:
    # - до 1000 руб: кратность 50
    # - от 1000 руб: кратность 500
    step = Decimal("50") if price_1 < Decimal("1000") else Decimal("500")
    price_2 = (price_1 / step).to_integral_value(rounding=ROUND_CEILING) * step
    round_delta = price_2 - price_1
    return price_2, round_delta


def _parse_decimal(value) -> Decimal:
    if value is None:
        return None
    try:
        num = Decimal(str(value).replace(" ", "").replace("\u00a0", ""))
        return num.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _ensure_price_indexes(db: Session):
    # ����� ���������, ���� �� ����쭮� ����� �� �� �����.
    db.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_price_products_article ON price_products(external_article)"))
    db.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_price_products_active ON price_products(is_active)"))
    db.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_price_products_brand ON price_products(brand)"))
    db.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_price_products_category ON price_products(category)"))
    db.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_price_history_upload ON price_history(price_upload_id)"))
    db.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_price_history_pid_created "
            "ON price_history(price_product_id, created_at DESC)"
        )
    )


@router.get("/", response_class=HTMLResponse)
async def price_index(
    request: Request,
    current_user: User = Depends(require_permission("price.search")),
    db: Session = Depends(get_db),
):
    # Для партнёра стартовая страница прайса должна быть поиск, а не админский обзор загрузок.
    if getattr(current_user, "partner_id", None) and not user_has_permission(current_user, db, "price.upload"):
        return RedirectResponse(url="/price/search", status_code=303)

    t0 = time.perf_counter()
    price_logger.info("[PRICE_INDEX] start")

    t1 = time.perf_counter()
    uploads = (
        db.query(PriceUpload)
        .order_by(PriceUpload.uploaded_at.desc())
        .limit(5)
        .all()
    )
    price_logger.info("[PRICE_INDEX] uploads loaded in %.3f sec", time.perf_counter() - t1)
    latest_upload = uploads[0] if uploads else None
    items_by_change: Dict[str, List[PriceHistory]] = {"NEW": [], "UP": [], "DOWN": [], "REMOVED": []}
    if latest_upload:
        def _last_changes(ct: str, limit: int = 50):
            return (
                db.query(PriceHistory)
                .options(sa.orm.joinedload(PriceHistory.price_product))
                .filter(
                    PriceHistory.price_upload_id == latest_upload.id,
                    PriceHistory.change_type == ct,
                )
                .order_by(PriceHistory.id.desc())
                .limit(limit)
                .all()
            )

        t2 = time.perf_counter()
        items_by_change["NEW"] = _last_changes("NEW", 50)
        items_by_change["UP"] = _last_changes("UP", 50)
        items_by_change["DOWN"] = _last_changes("DOWN", 50)
        items_by_change["REMOVED"] = _last_changes("REMOVED", 50)
        price_logger.info("[PRICE_INDEX] history chunks loaded in %.3f sec", time.perf_counter() - t2)

    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")
    can_upload = user_has_permission(current_user, db, "price.upload")

    t4 = time.perf_counter()
    resp = templates.TemplateResponse(
        "price_index.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "price",
            "uploads": uploads,
            "latest_upload": latest_upload,
            "items_by_change": items_by_change,
            "can_view_cost": can_view_cost,
            "can_view_margin": can_view_margin,
            "can_upload": can_upload,
        },
    )
    price_logger.info("[PRICE_INDEX] template rendered in %.3f sec", time.perf_counter() - t4)
    price_logger.info("[PRICE_INDEX] total time %.3f sec", time.perf_counter() - t0)
    return resp


@router.get("/upload_page", response_class=HTMLResponse)
async def price_upload_page(
    request: Request,
    current_user: User = Depends(require_permission("price.upload")),
    ct: str = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    t0 = time.perf_counter()
    price_logger.info("[PRICE_UPLOAD_PAGE] start")

    t1 = time.perf_counter()
    uploads = (
        db.query(PriceUpload)
        .order_by(PriceUpload.uploaded_at.desc())
        .limit(10)
        .all()
    )
    price_logger.info("[PRICE_UPLOAD_PAGE] uploads loaded in %.3f sec", time.perf_counter() - t1)
    latest_upload = uploads[0] if uploads else None
    items_by_change: Dict[str, List[PriceHistory]] = {"NEW": [], "UP": [], "DOWN": [], "REMOVED": []}
    counts_by_change: Dict[str, int] = {"NEW": 0, "UP": 0, "DOWN": 0, "REMOVED": 0, "UNCHANGED": 0}
    pages_count = 1
    page = max(int(page or 1), 1)
    selected_change = ct if ct in items_by_change else "NEW"
    PAGE_SIZE = 50
    if latest_upload:
        latest_rows = db.query(
            PriceHistory.id,
            PriceHistory.price_product_id,
            PriceHistory.new_price_1,
            PriceHistory.old_price_1,
            PriceHistory.new_price_2,
            PriceHistory.old_price_2,
            PriceHistory.price,
        ).filter(PriceHistory.price_upload_id == latest_upload.id).all()

        prev_upload = (
            db.query(PriceUpload).filter(PriceUpload.id != latest_upload.id).order_by(PriceUpload.uploaded_at.desc()).first()
        )
        prev_map: Dict[int, Decimal] = {}
        if prev_upload:
            prev_rows = db.query(
                PriceHistory.price_product_id,
                PriceHistory.new_price_1,
            ).filter(PriceHistory.price_upload_id == prev_upload.id).all()
            for r in prev_rows:
                prev_map[r.price_product_id] = Decimal(str(r.new_price_1)) if r.new_price_1 is not None else None

        buckets: Dict[str, List[int]] = {k: [] for k in items_by_change.keys()}
        unchanged_ids: List[int] = []
        for r in latest_rows:
            new_price_1 = Decimal(str(r.new_price_1)) if r.new_price_1 is not None else None
            old_price_1_prev = prev_map.get(r.price_product_id)
            if old_price_1_prev is None:
                bucket = "NEW"
            elif new_price_1 is None:
                bucket = "REMOVED"
            else:
                if new_price_1 > (old_price_1_prev or Decimal(0)):
                    bucket = "UP"
                elif new_price_1 < (old_price_1_prev or Decimal(0)):
                    bucket = "DOWN"
                else:
                    bucket = "UNCHANGED"
            if bucket in buckets:
                buckets[bucket].append(r.id)
            elif bucket == "UNCHANGED":
                unchanged_ids.append(r.id)

        counts_by_change["NEW"] = len(buckets["NEW"])
        counts_by_change["UP"] = len(buckets["UP"])
        counts_by_change["DOWN"] = len(buckets["DOWN"])
        counts_by_change["REMOVED"] = len(buckets["REMOVED"])
        counts_by_change["UNCHANGED"] = len(unchanged_ids)

        def _changes(ct_val: str, offset: int = 0, limit: int = PAGE_SIZE):
            ids = buckets.get(ct_val, [])
            slice_ids = ids[offset : offset + limit]
            if not slice_ids:
                return []
            return (
                db.query(PriceHistory)
                .options(sa.orm.joinedload(PriceHistory.price_product))
                .filter(PriceHistory.id.in_(slice_ids))
                .order_by(PriceHistory.id.desc())
                .all()
            )

        t2 = time.perf_counter()
        total = counts_by_change.get(selected_change, 0)
        pages_count = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
        offset = (page - 1) * PAGE_SIZE
        items_by_change[selected_change] = _changes(selected_change, offset=offset, limit=PAGE_SIZE)
        price_logger.info("[PRICE_UPLOAD_PAGE] history chunks loaded in %.3f sec", time.perf_counter() - t2)

    t3 = time.perf_counter()
    resp = templates.TemplateResponse(
        "price_upload.html",
        {
            "request": request,
            "current_user": current_user,
        "uploads": uploads,
        "latest_upload": latest_upload,
        "items_by_change": items_by_change,
        "counts_by_change": counts_by_change,
        "selected_change": selected_change,
        "page": page,
        "pages_count": pages_count,
        "can_upload": True,
    },
)
    price_logger.info("[PRICE_UPLOAD_PAGE] template rendered in %.3f sec", time.perf_counter() - t3)
    price_logger.info("[PRICE_UPLOAD_PAGE] total time %.3f sec", time.perf_counter() - t0)
    return resp


@router.post("/upload", response_class=RedirectResponse)
async def upload_price(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        price_logger.exception("openpyxl not installed: %s", e)
        raise HTTPException(status_code=500, detail="openpyxl не установлен, загрузка XLSX недоступна")

    upload = None
    try:
        content = await file.read()
        wb = load_workbook(filename=BytesIO(content))
        preferred_sheets = [
            "Позиции",
            "Флаконы",
        ]
        sheet_name = None
        ws = None
        for name in preferred_sheets:
            if name in wb.sheetnames:
                sheet_name = name
                ws = wb[name]
                break
        if ws is None:
            if not wb.sheetnames:
                raise HTTPException(status_code=400, detail="Файл не содержит листов")
            sheet_name = wb.sheetnames[0]
            ws = wb[sheet_name]
        row_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(row_iter)
        except StopIteration:
            raise HTTPException(status_code=400, detail="Пустой файл")

        headers = [str(h).strip() if h is not None else "" for h in header_row]

        def _idx(name: str, default: int):
            return headers.index(name) if name in headers else default

        idx_article = _idx("Артикул", 0)
        idx_name = _idx("Наименование", 1)
        idx_price = _idx("Цена", 2)

        upload = PriceUpload(
            filename=file.filename,
            source_date=date.today(),
            status="in_progress",
            created_by_user_id=current_user.id if current_user else None,
        )
        db.add(upload)
        db.flush()

        prev_in_pricelist_ids = {
            pid for (pid,) in db.query(PriceProduct.id).filter(PriceProduct.is_in_current_pricelist.is_(True)).all()
        }
        if not prev_in_pricelist_ids:
            prev_in_pricelist_ids = {
                pid for (pid,) in db.query(PriceProduct.id).filter(PriceProduct.is_active.is_(True)).all()
            }

        def _safe_parse(raw: str) -> Dict[str, Any]:
            try:
                return _parse_raw_name(raw or "")
            except Exception as e:
                price_logger.exception("Parse raw_name failed for '%s': %s", raw, e)
                return {
                    "brand": None,
                    "product_name": raw or "",
                    "category": None,
                    "volume_value": None,
                    "volume_unit": None,
                    "gender": None,
                }

        total_rows = 0
        added_count = updated_price_count = unchanged_count = 0
        up_count = down_count = 0
        marked_out_of_stock_count = 0
        seen_product_ids: List[int] = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row) <= idx_article:
                continue
            external_article = row[idx_article]
            if external_article in (None, "", "None"):
                continue
            external_article = str(external_article).strip()
            if external_article.lower().startswith("артикул"):
                continue
            raw_name = str(row[idx_name]).strip() if len(row) > idx_name and row[idx_name] is not None else ""
            if raw_name.strip().lower().startswith("наименован"):
                continue
            price_val = row[idx_price] if len(row) > idx_price else None
            price_1 = _parse_decimal(price_val)
            if price_1 is None:
                price_logger.warning("[PRICE_UPLOAD] skip row without valid price: article=%s raw=%s val=%s", external_article, raw_name, price_val)
                continue

            price_2, round_delta = _calc_price_fields(price_1)
            parsed = _safe_parse(raw_name)
            now = datetime.utcnow()

            product = db.query(PriceProduct).filter(PriceProduct.external_article == external_article).first()
            if product:
                if product.price_2 is None:
                    last_hist = (
                        db.query(PriceHistory)
                        .filter(PriceHistory.price_product_id == product.id)
                        .order_by(PriceHistory.created_at.desc())
                        .first()
                    )
                    if last_hist:
                        fallback_price = last_hist.new_price_2 if last_hist.new_price_2 is not None else last_hist.price
                        product.price_2 = fallback_price
                        product.price_1 = last_hist.new_price_1 if last_hist.new_price_1 is not None else product.price_1
                old_price_1 = Decimal(product.price_1) if product.price_1 is not None else None
                old_price_2 = Decimal(product.price_2) if product.price_2 is not None else None
                old_round_delta = Decimal(product.round_delta) if product.round_delta is not None else None
                # определяем изменения по price_2
                if old_price_2 is None or price_2 > old_price_2:
                    change_type = "UP"
                    updated_price_count += 1
                    price_changed = True
                elif price_2 < (old_price_2 or Decimal(0)):
                    change_type = "DOWN"
                    updated_price_count += 1
                    price_changed = True
                else:
                    change_type = "UNCHANGED"
                    unchanged_count += 1
                    price_changed = False

                product.raw_name = raw_name
                product.product_name = parsed.get("product_name") or raw_name
                if parsed.get("brand"):
                    product.brand = parsed["brand"]
                if parsed.get("category"):
                    product.category = parsed["category"]
                if parsed.get("volume_value") is not None:
                    product.volume_value = parsed["volume_value"]
                if parsed.get("volume_unit"):
                    product.volume_unit = parsed["volume_unit"]
                if parsed.get("gender"):
                    product.gender = parsed["gender"]
                product.is_active = True
                product.is_in_stock = True
                product.is_in_current_pricelist = True
                product.price_1 = price_1
                product.price_2 = price_2
                product.round_delta = round_delta
                if price_changed:
                    product.last_price_change_at = now

                if change_type == "UP":
                    up_count += 1
                elif change_type == "DOWN":
                    down_count += 1

                db.add(product)
                db.add(
                    PriceHistory(
                        price_product_id=product.id,
                        price=price_2,
                        old_price_1=old_price_1,
                        new_price_1=price_1,
                        old_price_2=old_price_2,
                        new_price_2=price_2,
                        old_round_delta=old_round_delta,
                        new_round_delta=round_delta,
                        currency="RUB",
                        source_date=date.today(),
                        source_filename=file.filename,
                        change_type=change_type,
                        price_upload_id=upload.id,
                        changed_at=now,
                    )
                )
            else:
                product = PriceProduct(
                    external_article=external_article,
                    raw_name=raw_name,
                    product_name=parsed.get("product_name") or raw_name,
                    brand=parsed.get("brand"),
                    category=parsed.get("category"),
                    volume_value=parsed.get("volume_value"),
                    volume_unit=parsed.get("volume_unit"),
                    gender=parsed.get("gender"),
                    is_active=True,
                    is_in_stock=True,
                    is_in_current_pricelist=True,
                    price_1=price_1,
                    price_2=price_2,
                    round_delta=round_delta,
                    last_price_change_at=now,
                )
                db.add(product)
                db.flush()
                added_count += 1
                up_count += 1  # новое считаем как повышение относительно 0 для статистики трендов

                db.add(
                    PriceHistory(
                        price_product_id=product.id,
                        price=price_2,
                        old_price_1=None,
                        new_price_1=price_1,
                        old_price_2=None,
                        new_price_2=price_2,
                        old_round_delta=None,
                        new_round_delta=round_delta,
                        currency="RUB",
                        source_date=date.today(),
                        source_filename=file.filename,
                        change_type="NEW",
                        price_upload_id=upload.id,
                        changed_at=now,
                    )
                )

            seen_product_ids.append(product.id)
            total_rows += 1

        # REMOVED для отсутствующих
        removed_ids = set(prev_in_pricelist_ids) - set(seen_product_ids)
        if removed_ids:
            for prod in db.query(PriceProduct).filter(PriceProduct.id.in_(list(removed_ids))):
                old_price_1 = Decimal(prod.price_1) if prod.price_1 is not None else None
                old_price_2 = Decimal(prod.price_2) if prod.price_2 is not None else None
                old_round_delta = Decimal(prod.round_delta) if prod.round_delta is not None else None
                prod.is_active = False
                prod.is_in_stock = False
                prod.is_in_current_pricelist = False
                db.add(prod)
                db.add(
                    PriceHistory(
                        price_product_id=prod.id,
                        price=None,
                        old_price_1=old_price_1,
                        new_price_1=None,
                        old_price_2=old_price_2,
                        new_price_2=None,
                        old_round_delta=old_round_delta,
                        new_round_delta=None,
                        currency="RUB",
                        source_date=date.today(),
                        source_filename=file.filename,
                        change_type="REMOVED",
                        price_upload_id=upload.id,
                        changed_at=datetime.utcnow(),
                    )
                )
                marked_out_of_stock_count += 1
                down_count += 1

        upload.total_rows = total_rows
        upload.total_count = total_rows  # legacy
        upload.added_count = added_count
        upload.new_count = added_count  # legacy
        upload.updated_price_count = updated_price_count
        upload.up_count = up_count
        upload.down_count = down_count
        upload.marked_out_of_stock_count = marked_out_of_stock_count
        upload.removed_count = marked_out_of_stock_count  # legacy
        upload.unchanged_count = unchanged_count
        upload.status = "done"

        sync_catalog_from_price(db)
        db.commit()
        price_logger.info(
            "Price upload success file=%s total=%s added=%s updated=%s unchanged=%s out_of_stock=%s",
            file.filename,
            upload.total_rows,
            upload.added_count,
            upload.updated_price_count,
            upload.unchanged_count,
            upload.marked_out_of_stock_count,
        )
        return RedirectResponse(url="/price/upload_page", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        price_logger.exception("Price upload failed for file=%s: %s", file.filename if file else "unknown", e)
        if upload:
            db.rollback()
            # фиксируем неуспешную попытку, чтобы было видно в истории
            failed_upload = PriceUpload(
                filename=file.filename if file else None,
                source_date=date.today(),
                status="failed",
                created_by_user_id=current_user.id if current_user else None,
            )
            db.add(failed_upload)
            db.commit()
        else:
            db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при загрузке прайса, попробуйте ещё раз")


@router.post("/upload/{upload_id}/delete", response_class=RedirectResponse)
async def delete_price_upload(
    upload_id: int,
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    upload = db.query(PriceUpload).filter(PriceUpload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Загрузка не найдена")

    # запомним затронутые товары
    affected_product_ids = [
        pid for (pid,) in db.query(PriceHistory.price_product_id).filter(PriceHistory.price_upload_id == upload.id).distinct()
    ]
    # удаляем связанные записи истории
    db.query(PriceHistory).filter(PriceHistory.price_upload_id == upload.id).delete()
    db.delete(upload)
    db.flush()

    if affected_product_ids:
        chunk_size = 800
        for i in range(0, len(affected_product_ids), chunk_size):
            chunk = affected_product_ids[i : i + chunk_size]
            sub = (
                db.query(
                    PriceHistory.price_product_id.label("pid"),
                    sa.func.max(PriceHistory.created_at).label("max_created"),
                )
                .filter(PriceHistory.price_product_id.in_(chunk))
                .group_by(PriceHistory.price_product_id)
                .subquery()
            )
            latest_rows = (
                db.query(PriceHistory)
                .join(sub, (PriceHistory.price_product_id == sub.c.pid) & (PriceHistory.created_at == sub.c.max_created))
                .all()
            )
            latest_map = {r.price_product_id: r for r in latest_rows}

            # обновим только затронутые товары
            for pid in chunk:
                hist = latest_map.get(pid)
                if hist:
                    ct = hist.change_type
                    is_active = bool(ct) and ct != "REMOVED"
                    db.query(PriceProduct).filter(PriceProduct.id == pid).update(
                        {
                            "is_active": is_active,
                            "is_in_stock": is_active,
                            "is_in_current_pricelist": is_active,
                            "price_1": hist.new_price_1,
                            "price_2": hist.new_price_2 or hist.price,
                            "round_delta": hist.new_round_delta,
                        }
                    )
                else:
                    db.query(PriceProduct).filter(PriceProduct.id == pid).update(
                        {"is_active": False, "is_in_stock": False, "is_in_current_pricelist": False}
                    )

    db.commit()
    return RedirectResponse(url="/price/upload_page", status_code=303)


@router.get("/upload/{upload_id}/delete", response_class=RedirectResponse)
async def delete_price_upload_get(
    upload_id: int,
    current_user: User = Depends(require_permission("price.upload")),
    db: Session = Depends(get_db),
):
    # удобный путь для удаления через ссылку
    return await delete_price_upload(upload_id, current_user, db)


@router.get("/search", response_class=HTMLResponse)
async def price_search_page(
    request: Request,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    upload_id: int = None,
    client_id: str | None = None,
    current_user: User = Depends(require_permission("price.search")),
    db: Session = Depends(get_db),
):
    t0 = time.perf_counter()
    price_logger.info("[PRICE_SEARCH] start q='%s' page=%s size=%s upload=%s", q, page, page_size, upload_id)
    page_size = max(10, min(int(page_size or 20), 20))
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_client = user_has_permission(current_user, db, "prices.view_client") or can_view_cost
    can_create_orders = user_has_permission(current_user, db, "orders.create")
    t1 = time.perf_counter()
    if upload_id is None:
        latest_upload = db.query(PriceUpload).order_by(PriceUpload.uploaded_at.desc()).first()
        if latest_upload:
            upload_id = latest_upload.id
    price_logger.info("[PRICE_SEARCH] upload selection %.3f sec", time.perf_counter() - t1)

    t2 = time.perf_counter()
    products, total = _search_products(db, q, page, page_size, upload_id)
    price_logger.info("[PRICE_SEARCH] query products %.3f sec (total=%s)", time.perf_counter() - t2, total)
    t3 = time.perf_counter()
    last_history = _last_history_map(db, [p.id for p in products])
    base_price_map = _latest_price_map(db, [p.id for p in products])
    price_map = base_price_map if can_view_cost else {}
    price_1_map = _latest_price_map(db, [p.id for p in products], field="price_1") if can_view_cost else {}
    price_logger.info("[PRICE_SEARCH] history maps %.3f sec", time.perf_counter() - t3)
    pages_count = (total + page_size - 1) // page_size if total else 1

    client_id_int = None
    if client_id not in (None, "", "None", "null"):
        try:
            client_id_int = int(client_id)
        except ValueError:
            client_id_int = None

    client = db.query(Client).filter(Client.id == client_id_int).first() if client_id_int else None

    partner_pricing = None
    if getattr(current_user, "partner_id", None) and can_view_client:
        partner_id = current_user.partner_id
        policy = get_partner_pricing_policy(db, partner_id)
        admin_pct = policy.admin_markup_percent
        total_pct = get_total_markup_percent(db, partner_id, client_id=client.id) if client else get_total_markup_percent(db, partner_id)
        admin_price_map = {pid: calc_client_price(price, admin_pct) for pid, price in base_price_map.items()}
        total_price_map = {pid: calc_client_price(price, total_pct) for pid, price in base_price_map.items()}
        partner_pricing = {
            "admin_markup_percent": admin_pct,
            "partner_markup_percent": (total_pct - admin_pct) if total_pct is not None else None,
            "total_markup_percent": total_pct,
            "partner_default_markup_percent": policy.partner_default_markup_percent,
            "max_partner_markup_percent": policy.max_partner_markup_percent,
            "base_price_map": base_price_map,
            "admin_price_map": admin_price_map,
            "total_price_map": total_price_map,
        }

    t4 = time.perf_counter()
    resp = templates.TemplateResponse(
        "price_search.html",
        {
            "request": request,
            "current_user": current_user,
            "active_menu": "price",
            "q": q,
            "products": products,
            "page": page,
            "page_size": page_size,
            "pages_count": pages_count,
            "can_view_cost": can_view_cost,
            "can_view_client": can_view_client,
            "can_create_orders": can_create_orders,
            "price_map": price_map,
            "price_1_map": price_1_map,
            "last_history": last_history,
            "upload_id": upload_id,
            "client": client,
            "client_id": client.id if client else None,
            "partner_pricing": partner_pricing,
            "base_price_map": base_price_map if can_view_client else {},
        },
    )
    price_logger.info("[PRICE_SEARCH] render %.3f sec", time.perf_counter() - t4)
    price_logger.info("[PRICE_SEARCH] total %.3f sec", time.perf_counter() - t0)
    return resp


@router.get("/api/search", response_class=JSONResponse)
async def price_search_api(
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    upload_id: int = None,
    current_user: User = Depends(require_permission("price.search")),
    db: Session = Depends(get_db),
):
    page_size = max(10, min(int(page_size or 20), 20))
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    if upload_id is None:
        latest_upload = db.query(PriceUpload).order_by(PriceUpload.uploaded_at.desc()).first()
        if latest_upload:
            upload_id = latest_upload.id
    products, total = _search_products(db, q, page, page_size, upload_id)
    last_history = _last_history_map(db, [p.id for p in products])
    price_map = _latest_price_map(db, [p.id for p in products]) if can_view_cost else {}
    price_1_map = _latest_price_map(db, [p.id for p in products], field="price_1") if can_view_cost else {}
    return [
        {
            "id": p.id,
            "external_article": p.external_article,
            "brand": p.brand,
            "product_name": p.product_name,
            "category": p.category,
            "volume_value": float(p.volume_value or 0),
            "volume_unit": p.volume_unit,
            "change_type": last_history.get(p.id).change_type if last_history.get(p.id) else None,
            "price": float(price_map.get(p.id, 0)) if can_view_cost and p.id in price_map else None,
            "price_1": float(price_1_map.get(p.id, 0)) if can_view_cost and p.id in price_1_map else None,
        }
        for p in products
    ]


def _search_products(
    db: Session,
    q: str,
    page: int,
    page_size: int,
    upload_id: int = None,
):
    dialect = db.bind.dialect.name if db.bind else None
    tokens = [t.strip() for t in (q or "").replace(",", " ").split() if t.strip()]

    # Попытка FTS для SQLite
    if dialect == "sqlite" and tokens:
        try:
            match_expr = " AND ".join(tokens)
            fts_table = sa.text("price_products_fts")
            base = (
                db.query(PriceProduct)
                .join(fts_table, sa.text("price_products_fts.rowid = price_products.id"))
                .filter(sa.text("price_products_fts MATCH :match"))
                .params(match=match_expr)
            ).filter(
                PriceProduct.is_in_stock.is_(True),
                PriceProduct.is_in_current_pricelist.is_(True),
                PriceProduct.is_active.is_(True),
            )
            if upload_id:
                base = base.filter(
                    sa.exists().where(
                        (PriceHistory.price_upload_id == upload_id)
                        & (PriceHistory.price_product_id == PriceProduct.id)
                    )
                )
            total = base.count()
            items = (
                base.order_by(PriceProduct.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return items, total
        except Exception as e:
            price_logger.exception("FTS search failed, fallback to ILIKE: %s", e)

    # Fallback: обычные ILIKE
    base_query = db.query(PriceProduct).filter(
        PriceProduct.is_in_stock.is_(True),
        PriceProduct.is_in_current_pricelist.is_(True),
        PriceProduct.is_active.is_(True),
    )
    if upload_id:
        base_query = base_query.filter(
            sa.exists().where(
                (PriceHistory.price_upload_id == upload_id)
                & (PriceHistory.price_product_id == PriceProduct.id)
            )
        )
    for tok in tokens:
        like = f"%{tok}%"
        base_query = base_query.filter(
            (PriceProduct.external_article.ilike(like))
            | (PriceProduct.raw_name.ilike(like))
            | (PriceProduct.product_name.ilike(like))
        )
    total = base_query.count()
    items = (
        base_query.order_by(PriceProduct.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _last_history_map(db: Session, product_ids: List[int]) -> Dict[int, PriceHistory]:
    if not product_ids:
        return {}
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
        db.query(PriceHistory)
        .join(sub, (PriceHistory.price_product_id == sub.c.pid) & (PriceHistory.created_at == sub.c.max_created))
        .all()
    )
    return {r.price_product_id: r for r in rows}


def _latest_price_map(db: Session, product_ids: List[int], field: str = "price_2") -> Dict[int, Decimal]:
    if not product_ids:
        return {}
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
        db.query(
            PriceHistory.price_product_id,
            PriceHistory.new_price_2,
            PriceHistory.new_price_1,
            PriceHistory.price,
        )
        .join(sub, (PriceHistory.price_product_id == sub.c.pid) & (PriceHistory.created_at == sub.c.max_created))
        .all()
    )
    result = {}
    for pid, new_price_2, new_price_1, price in rows:
        if field == "price_1":
            val = new_price_1 if new_price_1 is not None else new_price_2 if new_price_2 is not None else price
        else:
            val = new_price_2 if new_price_2 is not None else price
        result[pid] = Decimal(val or 0)
    return result


def _to_float(val):
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


@router.get("/product/{product_id}", response_class=HTMLResponse)
async def price_product_detail(
    request: Request,
    product_id: int,
    current_user: User = Depends(require_permission("price.search")),
    db: Session = Depends(get_db),
):
    product = db.query(PriceProduct).filter(PriceProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.price_product_id == product.id)
        .order_by(PriceHistory.created_at.desc())
        .limit(200)
        .all()
    )
    orders = []  # Заказы пока не используем
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")
    can_view_client = user_has_permission(current_user, db, "prices.view_client") or can_view_cost
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    partner_pricing = None
    if getattr(current_user, "partner_id", None) and can_view_client and history:
        last = history[0]
        base_price = Decimal((last.new_price_2 if last.new_price_2 is not None else last.price) or 0)
        partner_id = current_user.partner_id
        policy = get_partner_pricing_policy(db, partner_id)
        admin_pct = policy.admin_markup_percent
        total_pct = get_total_markup_percent(db, partner_id)
        partner_pricing = {
            "admin_markup_percent": admin_pct,
            "partner_markup_percent": (total_pct - admin_pct) if total_pct is not None else None,
            "total_markup_percent": total_pct,
            "base_price": base_price,
            "admin_price": calc_client_price(base_price, admin_pct),
            "total_price": calc_client_price(base_price, total_pct),
        }
    return templates.TemplateResponse(
        "price_product_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "product": product,
            "history": history,
            "orders": orders,
            "can_view_cost": can_view_cost,
            "can_view_client": can_view_client,
            "can_view_margin": can_view_margin,
            "partner_pricing": partner_pricing,
        },
    )
