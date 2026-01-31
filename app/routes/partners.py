import secrets
from decimal import Decimal
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Partner, Role
from app.services.auth_service import (
    require_permission,
    user_has_permission,
    require_roles,
    hash_password,
    verify_password,
    resolve_current_partner,
)
from app.services.stats_service import get_partner_finance_stats
from app.logging_config import partners_logger

router = APIRouter(prefix="/partners", tags=["partners"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def get_partners_list(
    request: Request,
    current_user: User = Depends(require_permission(["partners.view_all", "partners.view_own"])),
    db: Session = Depends(get_db)
):
    """Список партнёров"""
    can_manage = user_has_permission(current_user, db, "partners.view_all")
    q = (request.query_params.get("q") or "").strip()
    status_filter = request.query_params.get("status") or "all"

    query = db.query(Partner)
    if q:
        like_expr = f"%{q.lower()}%"
        query = query.filter(
            (Partner.full_name.ilike(like_expr)) |
            (Partner.phone.ilike(like_expr)) |
            (Partner.name.ilike(like_expr))
        )
    if status_filter in ("active", "paused", "blocked"):
        query = query.filter(Partner.status == status_filter)

    if not can_manage:
        current_partner = resolve_current_partner(db, current_user)
        if current_partner:
            query = query.filter(Partner.id == current_partner.id)
        else:
            query = query.filter(False)
    partners = query.order_by(Partner.created_at.desc().nullslast()).all()
    return templates.TemplateResponse("partners_list.html", {
        "request": request,
        "current_user": current_user,
        "partners": partners,
        "can_manage": can_manage,
        "filters": {"q": q, "status": status_filter},
        "active_menu": "partners"
    })


@router.get("/new", response_class=HTMLResponse)
async def new_partner_form(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    return templates.TemplateResponse(
        "partner_form.html",
        {
            "request": request,
            "current_user": current_user,
            "partner": None,
            "temp_password": None,
            "active_menu": "partners",
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def create_partner(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    telegram: str = Form(""),
    telegram_nick: str = Form(""),
    notes: str = Form(""),
    comment: str = Form(""),
    partner_price_markup_percent: str = Form(""),
    admin_markup_percent: str = Form(""),
    max_partner_markup_percent: str = Form(""),
    partner_default_markup_percent: str = Form(""),
    can_edit_prices: bool = Form(False),
    can_access_catalog: bool = Form(False),
    status: str = Form("active"),
    is_active: bool = Form(True),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    errors = {}
    name_normalized = (full_name or "").strip()
    if not name_normalized or len(name_normalized) < 5:
        errors["full_name"] = "Укажите ФИО (минимум 5 символов)"
    phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not phone_clean or len(phone_clean) < 10:
        errors["phone"] = "Укажите телефон (не меньше 10 цифр)"
    telegram_nick_clean = (telegram_nick or "").strip()
    if not telegram_nick_clean:
        errors["telegram_nick"] = "Укажите Telegram (ник) или другой мессенджер"
    if not email:
        errors["email"] = "Укажите email для входа"

    def _parse_pct(raw: str, field: str) -> Decimal | None:
        if raw in ("", None):
            return None
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except Exception as exc:
            errors[field] = "Некорректное число"
            partners_logger.error("[PARTNER_CREATE] invalid %s=%s err=%s", field, raw, exc)
            return None

    partner_price_markup = _parse_pct(partner_price_markup_percent, "partner_price_markup_percent") or Decimal("0.00")
    admin_markup = _parse_pct(admin_markup_percent, "admin_markup_percent") or Decimal("0.00")
    max_partner_markup = _parse_pct(max_partner_markup_percent, "max_partner_markup_percent")
    partner_default_markup = _parse_pct(partner_default_markup_percent, "partner_default_markup_percent") or Decimal("0.00")
    if partner_price_markup < 0:
        errors["partner_price_markup_percent"] = "Должно быть от 0"
    if admin_markup < 0:
        errors["admin_markup_percent"] = "Должно быть от 0"
    if max_partner_markup is not None and max_partner_markup < 0:
        errors["max_partner_markup_percent"] = "Должно быть от 0"
    if partner_default_markup < 0:
        errors["partner_default_markup_percent"] = "Должно быть от 0"
    if max_partner_markup is not None and partner_default_markup > max_partner_markup:
        errors["partner_default_markup_percent"] = f"Должно быть не больше {max_partner_markup}%"
    # email уникальный
    existing_email = None
    if email:
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            errors["email"] = "Такой email уже используется"
    if errors:
        partners = db.query(Partner).order_by(Partner.created_at.desc().nullslast()).all()
        return templates.TemplateResponse("partner_form.html", {
            "request": request,
            "current_user": current_user,
            "partner": None,
            "errors": errors,
            "form": {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "telegram": telegram,
                "telegram_nick": telegram_nick,
                "comment": comment,
                "partner_price_markup_percent": partner_price_markup_percent,
                "admin_markup_percent": admin_markup_percent,
                "max_partner_markup_percent": max_partner_markup_percent,
                "partner_default_markup_percent": partner_default_markup_percent,
                "can_edit_prices": can_edit_prices,
                "can_access_catalog": can_access_catalog,
                "status": status or "active",
            },
            "active_menu": "partners",
        })
    name_normalized = name_normalized or "Партнёр"
    partner_role = db.query(Role).filter(Role.name == "PARTNER").first()
    if not partner_role:
        raise HTTPException(status_code=400, detail="Роль PARTNER не найдена. Добавьте роль в таблицу roles.")

    temp_password = secrets.token_urlsafe(8)
    user = User(
        username=username.strip() or (email.strip() if email else None) or f"partner_{secrets.randbelow(9999)}",
        email=email.strip() or None,
        full_name=name_normalized,
        password_hash=hash_password(temp_password),
        role_id=partner_role.id,
        role_name="partner",
        is_active=bool(is_active),
        pending_activation=False,
    )
    db.add(user)
    db.flush()  # чтобы получить user.id

    partner = Partner(
        name=name_normalized,
        full_name=name_normalized,
        phone=phone or None,
        telegram=telegram or None,
        telegram_nick=telegram_nick_clean or None,
        notes=notes or None,
        comment=comment or None,
        is_active=bool(is_active),
        can_access_catalog=bool(can_access_catalog),
        can_edit_prices=bool(can_edit_prices),
        partner_price_markup_percent=partner_price_markup,
        admin_markup_percent=admin_markup,
        max_partner_markup_percent=max_partner_markup,
        partner_default_markup_percent=partner_default_markup,
        status=status or "active",
        user_id=user.id,
    )
    db.add(partner)
    db.flush()

    user.partner_id = partner.id
    db.add(user)
    db.commit()
    db.refresh(partner)

    partners_logger.info(
        "[PARTNER_CREATE] saved partner_id=%s user_id=%s username=%s temp_password=%s status=%s",
        partner.id, user.id, user.username, temp_password, status,
    )
    return RedirectResponse(url=f"/partners/{partner.id}?temp_password={temp_password}", status_code=303)


@router.post("/{partner_id}/delete", response_class=RedirectResponse)
async def delete_partner(
    partner_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse
    from fastapi import Request
    
    partners_logger.info(
        "[PARTNER_DELETE] start partner_id=%s user_id=%s",
        partner_id,
        getattr(current_user, "id", None),
    )
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        partners_logger.error("[PARTNER_DELETE] partner_id=%s not found", partner_id)
        return RedirectResponse(url="/partners", status_code=303)

    # Проверяем наличие заказов партнера
    from app.models import Order
    # Статусы, которые считаются завершенными полностью
    COMPLETED_STATUSES = ["DELIVERED", "CANCELLED", "RETURNED"]
    
    # Заказы партнера
    partner_orders = db.query(Order).filter(Order.partner_id == partner_id).all()
    
    # Заказы клиентов партнера
    client_ids = [c.id for c in partner.clients] if partner.clients else []
    client_orders = []
    if client_ids:
        client_orders = db.query(Order).filter(Order.client_id.in_(client_ids)).all()
    
    all_orders = partner_orders + client_orders
    orders_count = len(all_orders)
    
    # Проверяем, есть ли незавершенные заказы
    incomplete_orders = [o for o in all_orders if o.status not in COMPLETED_STATUSES]
    
    if orders_count == 0:
        # Нет заказов - полное удаление
        try:
            # Удаляем связанные данные
            # Удаляем накрутки партнера для клиентов
            from app.models import PartnerClientMarkup
            db.query(PartnerClientMarkup).filter(PartnerClientMarkup.partner_id == partner_id).delete()
            
            # Отвязываем пользователей от партнера
            from app.models import User
            db.query(User).filter(User.partner_id == partner_id).update({"partner_id": None})
            
            # Удаляем партнера
            db.delete(partner)
            db.commit()
            partners_logger.info("[PARTNER_DELETE] fully deleted partner_id=%s (no orders)", partner_id)
        except Exception as e:
            db.rollback()
            partners_logger.error("[PARTNER_DELETE] error deleting partner_id=%s: %s", partner_id, str(e))
            return RedirectResponse(url="/partners?error=delete_failed", status_code=303)
    elif len(incomplete_orders) > 0:
        # Есть незавершенные заказы - только блокировка
        partner.is_active = False
        partner.status = "blocked"
        db.add(partner)
        db.commit()
        partners_logger.info(
            "[PARTNER_DELETE] blocked partner_id=%s (has %d incomplete orders)",
            partner_id,
            len(incomplete_orders)
        )
    else:
        # Все заказы завершены - можно удалить
        try:
            # Удаляем связанные данные
            from app.models import PartnerClientMarkup
            db.query(PartnerClientMarkup).filter(PartnerClientMarkup.partner_id == partner_id).delete()
            
            # Отвязываем пользователей от партнера
            from app.models import User
            db.query(User).filter(User.partner_id == partner_id).update({"partner_id": None})
            
            # Удаляем партнера
            db.delete(partner)
            db.commit()
            partners_logger.info(
                "[PARTNER_DELETE] fully deleted partner_id=%s (all %d orders completed)",
                partner_id,
                orders_count
            )
        except Exception as e:
            db.rollback()
            partners_logger.error("[PARTNER_DELETE] error deleting partner_id=%s: %s", partner_id, str(e))
            # При ошибке блокируем
            partner.is_active = False
            partner.status = "blocked"
            db.add(partner)
            db.commit()
            return RedirectResponse(url="/partners?error=delete_failed", status_code=303)
    
    return RedirectResponse(url="/partners", status_code=303)


@router.get("/{partner_id}/delete", response_class=RedirectResponse)
async def delete_partner_get(
    partner_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Удаление через GET (если форма/кнопка отправила запрос не POST)."""
    partners_logger.info(
        "[PARTNER_DELETE_GET] partner_id=%s user_id=%s",
        partner_id,
        getattr(current_user, "id", None),
    )
    return await delete_partner(partner_id, current_user, db)


@router.get("/{partner_id}/edit", response_class=HTMLResponse)
async def edit_partner_form(
    request: Request,
    partner_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")

    return templates.TemplateResponse(
        "partner_form.html",
        {
            "request": request,
            "current_user": current_user,
            "partner": partner,
            "active_menu": "partners",
        },
    )


@router.post("/{partner_id}/edit", response_class=HTMLResponse)
async def update_partner(
    request: Request,
    partner_id: int,
    full_name: str = Form(""),
    phone: str = Form(""),
    telegram: str = Form(""),
    telegram_nick: str = Form(""),
    notes: str = Form(""),
    comment: str = Form(""),
    partner_price_markup_percent: str = Form(""),
    admin_markup_percent: str = Form(""),
    max_partner_markup_percent: str = Form(""),
    partner_default_markup_percent: str = Form(""),
    can_edit_prices: bool = Form(False),
    can_access_catalog: bool = Form(False),
    status: str = Form("active"),
    is_active: bool = Form(True),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    errors = {}
    name_normalized = (full_name or partner.full_name or partner.name or "").strip()
    if not name_normalized or len(name_normalized) < 5:
        errors["full_name"] = "Укажите ФИО (минимум 5 символов)"
    phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not phone_clean or len(phone_clean) < 10:
        errors["phone"] = "Укажите телефон (не меньше 10 цифр)"

    def _parse_pct(raw: str, field: str) -> Decimal | None:
        if raw in ("", None):
            return None
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except Exception as exc:
            errors[field] = "Некорректное число"
            partners_logger.error("[PARTNER_UPDATE] invalid %s=%s err=%s", field, raw, exc)
            return None

    partner_price_markup = _parse_pct(partner_price_markup_percent, "partner_price_markup_percent")
    admin_markup = _parse_pct(admin_markup_percent, "admin_markup_percent")
    max_partner_markup = _parse_pct(max_partner_markup_percent, "max_partner_markup_percent")
    partner_default_markup = _parse_pct(partner_default_markup_percent, "partner_default_markup_percent")

    # Если поле пустое, сохраняем текущее значение, а не сбрасываем в 0
    if partner_price_markup is None:
        partner_price_markup = getattr(partner, 'partner_price_markup_percent', None)
        if partner_price_markup is None:
            partner_price_markup = Decimal("0.00")
    if admin_markup is None:
        admin_markup = partner.admin_markup_percent or Decimal("0.00")
    if partner_default_markup is None:
        partner_default_markup = partner.partner_default_markup_percent or Decimal("0.00")

    if partner_price_markup < 0:
        errors["partner_price_markup_percent"] = "Должно быть от 0"
    if admin_markup < 0:
        errors["admin_markup_percent"] = "Должно быть от 0"
    if max_partner_markup is not None and max_partner_markup < 0:
        errors["max_partner_markup_percent"] = "Должно быть от 0"
    if partner_default_markup < 0:
        errors["partner_default_markup_percent"] = "Должно быть от 0"
    if max_partner_markup is not None and partner_default_markup > max_partner_markup:
        errors["partner_default_markup_percent"] = f"Должно быть не больше {max_partner_markup}%"

    if errors:
        return templates.TemplateResponse(
            "partner_form.html",
            {
                "request": request,
                "current_user": current_user,
                "partner": partner,
                "errors": errors,
                "form": {
                    "full_name": full_name,
                    "phone": phone,
                    "telegram": telegram,
                    "telegram_nick": telegram_nick,
                    "comment": comment,
                    "partner_price_markup_percent": partner_price_markup_percent,
                    "admin_markup_percent": admin_markup_percent,
                    "max_partner_markup_percent": max_partner_markup_percent,
                    "partner_default_markup_percent": partner_default_markup_percent,
                    "can_edit_prices": can_edit_prices,
                    "can_access_catalog": can_access_catalog,
                    "status": status or partner.status or "active",
                },
                "active_menu": "partners",
            },
        )
    name_normalized = name_normalized or "Партнёр"

    partners_logger.info(
        "[PARTNER_UPDATE] partner_id=%s input name=%s phone=%s tg=%s active=%s catalog=%s can_edit_prices=%s status=%s",
        partner_id, name_normalized, phone, telegram, is_active, can_access_catalog, can_edit_prices, status
    )

    partner.name = name_normalized
    partner.full_name = name_normalized
    partner.phone = phone or None
    partner.telegram = telegram or None
    partner.telegram_nick = telegram_nick or None
    partner.notes = notes or None
    partner.comment = comment or None
    partner.is_active = bool(is_active)
    partner.can_access_catalog = bool(can_access_catalog)
    partner.can_edit_prices = bool(can_edit_prices)
    partner.partner_price_markup_percent = partner_price_markup
    partner.admin_markup_percent = admin_markup
    partner.max_partner_markup_percent = max_partner_markup
    partner.partner_default_markup_percent = partner_default_markup
    partner.status = status or partner.status or "active"
    partners_logger.info(
        "[PARTNER_UPDATE] saved partner_id=%s name=%s phone=%s",
        partner.id, partner.name, partner.phone
    )
    db.add(partner)
    db.commit()
    return RedirectResponse(url=f"/partners/{partner.id}", status_code=303)


@router.post("/me/markup", response_class=RedirectResponse)
async def update_my_partner_markup(
    partner_default_markup_percent: str = Form(""),
    next: str = Form(""),
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    partner = resolve_current_partner(db, current_user)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    raw = (partner_default_markup_percent or "").strip()
    try:
        pct = Decimal(str(raw)).quantize(Decimal("0.01")) if raw not in ("", "None", "null") else Decimal("0.00")
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректное число")
    if pct < 0:
        pct = Decimal("0.00")
    if partner.max_partner_markup_percent is not None and pct > Decimal(str(partner.max_partner_markup_percent)):
        raise HTTPException(status_code=400, detail=f"Максимум {partner.max_partner_markup_percent}%")
    partner.partner_default_markup_percent = pct
    db.add(partner)
    db.commit()
    redirect_to = "/partners/me"
    if next and isinstance(next, str) and next.startswith("/"):
        redirect_to = next
    return RedirectResponse(url=redirect_to, status_code=303)

@router.get("/me", response_class=HTMLResponse)
async def get_my_partner_settings(
    request: Request,
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    partner = resolve_current_partner(db, current_user)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    pw = request.query_params.get("pw")
    profile = request.query_params.get("profile")
    return templates.TemplateResponse(
        "partner_me.html",
        {
            "request": request,
            "current_user": current_user,
            "partner": partner,
            "pw": pw,
            "profile": profile,
            "active_menu": "partners",
        },
    )


@router.get("/me/orders/new", response_class=RedirectResponse)
async def partner_new_order(
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    """Перенаправление партнёра на форму создания заказа"""
    partner = resolve_current_partner(db, current_user)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    # Перенаправляем на стандартную форму заказа, которая автоматически определит партнёра
    return RedirectResponse(url="/orders/new", status_code=303)


@router.post("/me/profile", response_class=RedirectResponse)
async def update_my_partner_profile(
    full_name: str = Form(""),
    phone: str = Form(""),
    telegram: str = Form(""),
    telegram_nick: str = Form(""),
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    partner = resolve_current_partner(db, current_user)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")

    name_normalized = (full_name or "").strip()
    if name_normalized and len(name_normalized) < 5:
        return RedirectResponse(url="/partners/me?profile=bad_name", status_code=303)

    phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
    if phone and (not phone_clean or len(phone_clean) < 10):
        return RedirectResponse(url="/partners/me?profile=bad_phone", status_code=303)

    partner.full_name = name_normalized or partner.full_name
    partner.phone = phone_clean or None
    partner.telegram = (telegram or "").strip() or None
    partner.telegram_nick = (telegram_nick or "").strip() or None
    db.add(partner)
    db.commit()
    return RedirectResponse(url="/partners/me?profile=ok", status_code=303)


@router.post("/me/change_password", response_class=RedirectResponse)
async def change_my_password(
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    current_user: User = Depends(require_roles(["PARTNER"])),
    db: Session = Depends(get_db),
):
    partner = resolve_current_partner(db, current_user)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")

    if not verify_password(current_password or "", current_user.password_hash or ""):
        return RedirectResponse(url="/partners/me?pw=bad_old", status_code=303)

    if not new_password or len(new_password) < 6:
        return RedirectResponse(url="/partners/me?pw=bad_new", status_code=303)

    if new_password != new_password_confirm:
        return RedirectResponse(url="/partners/me?pw=bad_confirm", status_code=303)

    current_user.password_hash = hash_password(new_password)
    db.add(current_user)
    db.commit()
    return RedirectResponse(url="/partners/me?pw=ok", status_code=303)


@router.get("/{partner_id}", response_class=HTMLResponse)
async def get_partner_detail(
    request: Request,
    partner_id: int,
    current_user: User = Depends(require_permission(["partners.view_all", "partners.view_own"])),
    db: Session = Depends(get_db)
):
    """Детали партнёра"""
    partners_logger.info(
        "[PARTNER_DETAIL] request partner_id=%s user_id=%s role=%s partner_link=%s",
        partner_id,
        getattr(current_user, "id", None),
        getattr(current_user.role, "name", None) if getattr(current_user, "role", None) else None,
        getattr(current_user, "partner_id", None),
    )
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        partners_logger.error(
            "[PARTNER_DETAIL] partner_id=%s not found for user_id=%s",
            partner_id,
            getattr(current_user, "id", None),
        )
        return RedirectResponse(url="/partners", status_code=303)

    can_view_all = user_has_permission(current_user, db, "partners.view_all")
    if not can_view_all and getattr(current_user, "partner_id", None) != partner_id:
        partners_logger.error(
            "[PARTNER_DETAIL] access denied partner_id=%s user_id=%s can_view_all=%s user_partner_id=%s",
            partner_id,
            getattr(current_user, "id", None),
            can_view_all,
            getattr(current_user, "partner_id", None),
        )
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    finance = get_partner_finance_stats(db, current_user, partner_id)
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")
    can_view_cost = user_has_permission(current_user, db, "prices.view_cost")

    temp_password = request.query_params.get("temp_password")

    return templates.TemplateResponse("partner_detail.html", {
        "request": request,
        "current_user": current_user,
        "partner": partner,
        "finance": finance,
        "can_view_margin": can_view_margin,
        "can_view_cost": can_view_cost,
        "active_menu": "partners",
        "temp_password": temp_password,
    })
