from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
from app.db import get_db
from app.models import User, Client, Partner, PartnerClientMarkup
from app.services.auth_service import require_permission, user_has_permission, resolve_current_partner
from app.services.stats_service import get_client_finance_stats
from app.services.partner_pricing_service import get_partner_pricing_policy
from app.logging_config import auth_logger

router = APIRouter(prefix="/clients", tags=["clients"])
templates = Jinja2Templates(directory="app/templates")


def _get_filters_for_user(current_user: User, can_view_all: bool, q: str = "", partner_id: int | None = None, city: str = ""):
    base = []
    if q:
        like_expr = f"%{q.lower()}%"
        base.append(
            (Client.name.ilike(like_expr)) |
            (Client.phone.ilike(like_expr)) |
            (Client.email.ilike(like_expr))
        )
    if city:
        base.append(Client.city.ilike(f"%{city.lower()}%"))
    if can_view_all:
        if partner_id is not None:
            if partner_id == 0:
                base.append((Client.partner_id.is_(None)))
            else:
                base.append(Client.partner_id == partner_id)
        return base

    # только свои
    partner_filter = getattr(current_user, "partner_id", None)
    base.append(
        (Client.owner_user_id == current_user.id)
        | (Client.owner_partner_id == partner_filter)
        | (Client.partner_id == partner_filter)
        | (Client.created_by_user_id == current_user.id)  # Клиенты, созданные текущим пользователем
    )
    return base


@router.get("/", response_class=HTMLResponse)
async def get_clients_list(
    request: Request,
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own"])),
    db: Session = Depends(get_db)
):
    """Список клиентов с учётом прав"""
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    can_view_own = user_has_permission(current_user, db, "clients.view_own")
    can_create = user_has_permission(current_user, db, "clients.create")
    can_edit = user_has_permission(current_user, db, "clients.create")
    q = (request.query_params.get("q") or "").strip()
    partner_filter_raw = request.query_params.get("partner_id")
    city = (request.query_params.get("city") or "").strip()
    partner_filter_id = None
    if partner_filter_raw not in (None, "", "all"):
        try:
            partner_filter_id = int(partner_filter_raw)
        except ValueError:
            partner_filter_id = None
    if not can_view_all and not can_view_own:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    query = db.query(Client)
    filters = _get_filters_for_user(current_user, can_view_all, q=q, partner_id=partner_filter_id, city=city)
    for flt in filters:
        query = query.filter(flt)
    clients = query.order_by(Client.created_at.desc()).all()

    partners = db.query(Partner).all() if can_view_all else []

    return templates.TemplateResponse("clients_list.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "clients",
        "clients": clients,
        "can_create": can_create,
        "can_edit": can_edit,
        "filters": {"q": q, "partner_id": partner_filter_id, "city": city},
        "partners": partners,
    })


@router.get("/new", response_class=HTMLResponse)
async def client_create_form(
    request: Request,
    return_to: Optional[str] = None,
    current_user: User = Depends(require_permission("clients.create")),
    db: Session = Depends(get_db)
):
    partners = db.query(Partner).all()
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    return templates.TemplateResponse("client_create.html", {
        "request": request,
        "current_user": current_user,
        "partners": partners,
        "active_menu": "clients",
        "can_choose_partner": can_view_all,
        "errors": {},
        "form": {},
        "return_to": return_to,
    })


def _ensure_can_edit_client(client: Client, current_user: User, db: Session):
    """Проверка прав на изменение/удаление клиента."""
    if user_has_permission(current_user, db, "clients.create") or user_has_permission(current_user, db, "clients.view_all"):
        return
    if user_has_permission(current_user, db, "clients.view_own"):
        if client.owner_user_id == current_user.id:
            return
        if getattr(current_user, "partner_id", None) and (client.owner_partner_id == current_user.partner_id or client.partner_id == current_user.partner_id):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit_form(
    request: Request,
    client_id: int,
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own", "clients.create"])),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    _ensure_can_edit_client(client, current_user, db)
    partners = db.query(Partner).all()
    partner_markup = None
    can_set_markup = False
    max_partner_markup = None
    if getattr(current_user, "partner_id", None):
        can_set_markup = True
        policy = get_partner_pricing_policy(db, current_user.partner_id)
        max_partner_markup = float(policy.max_partner_markup_percent) if policy.max_partner_markup_percent is not None else None
        existing = (
            db.query(PartnerClientMarkup)
            .filter(
                PartnerClientMarkup.partner_id == current_user.partner_id,
                PartnerClientMarkup.client_id == client.id,
            )
            .first()
        )
        if existing and existing.partner_markup_percent is not None:
            partner_markup = float(existing.partner_markup_percent)
    return templates.TemplateResponse("client_edit.html", {
        "request": request,
        "current_user": current_user,
        "partners": partners,
        "client": client,
        "partner_markup_percent": partner_markup,
        "can_set_partner_markup": can_set_markup,
        "max_partner_markup_percent": max_partner_markup,
        "errors": {},
        "form": {},
        "active_menu": "clients"
    })


@router.post("/")
async def create_client(
    request: Request,
    full_name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    partner_id: Optional[str] = Form(None),
    can_access_catalog: bool = Form(False),
    return_to: Optional[str] = Form(None),
    current_user: User = Depends(require_permission("clients.create")),
    db: Session = Depends(get_db)
):
    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    can_view_own = user_has_permission(current_user, db, "clients.view_own")

    errors = {}
    name_normalized = (full_name or "").strip()
    if not name_normalized:
        errors["full_name"] = "Укажите ФИО клиента"
    phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not phone_clean or len(phone_clean) < 10:
        errors["phone"] = "Укажите телефон (не меньше 10 цифр)"

    owner_user_id = None
    owner_partner_id = None
    partner_id_value = None

    # нормализуем partner_id
    partner_id_int = int(partner_id) if partner_id not in (None, "", "None") else None

    if can_view_all:
        if partner_id_int:
            partner = db.query(Partner).filter(Partner.id == partner_id_int).first()
            if not partner:
                errors["partner_id"] = "Партнёр не найден"
            owner_partner_id = partner_id_int
            partner_id_value = partner_id_int
        # админ может не указывать партнёра, тогда остаётся None
    elif can_view_own:
        owner_user_id = current_user.id
        owner_partner_id = getattr(current_user, "partner_id", None)
        partner_obj = resolve_current_partner(db, current_user)
        partner_id_value = partner_obj.id if partner_obj else None
    else:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if errors:
        partners = db.query(Partner).all()
        return templates.TemplateResponse("client_create.html", {
            "request": request,
            "current_user": current_user,
            "partners": partners,
            "can_choose_partner": can_view_all,
            "errors": errors,
            "form": {
                "full_name": full_name,
                "phone": phone,
                "email": email,
                "city": city,
                "notes": notes,
                "partner_id": partner_id,
                "can_access_catalog": can_access_catalog,
            },
            "active_menu": "clients",
            "return_to": return_to,
        })

    client = Client(
        name=name_normalized,
        phone=phone,
        email=email,
        city=city,
        notes=notes,
        partner_id=partner_id_value,
        owner_user_id=owner_user_id,
        owner_partner_id=owner_partner_id,
        created_by_user_id=current_user.id,
        can_access_catalog=bool(can_access_catalog)
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    # Если есть return_to, возвращаемся туда с параметром client_id
    if return_to:
        separator = "&" if "?" in return_to else "?"
        return RedirectResponse(url=f"{return_to}{separator}client_id={client.id}", status_code=status.HTTP_303_SEE_OTHER)
    
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{client_id}/edit")
async def update_client(
    request: Request,
    client_id: int,
    full_name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    partner_id: Optional[str] = Form(None),
    can_access_catalog: bool = Form(False),
    partner_markup_percent: Optional[str] = Form(None),
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own", "clients.create"])),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    _ensure_can_edit_client(client, current_user, db)

    errors = {}
    name_normalized = (full_name or "").strip()
    if not name_normalized:
        errors["full_name"] = "Укажите ФИО клиента"
    phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not phone_clean or len(phone_clean) < 10:
        errors["phone"] = "Укажите телефон (не меньше 10 цифр)"

    partner_id_int = int(partner_id) if partner_id not in (None, "", "None") else None
    if partner_id_int:
        partner = db.query(Partner).filter(Partner.id == partner_id_int).first()
        if not partner:
            errors["partner_id"] = "Партнёр не найден"

    if errors:
        partners = db.query(Partner).all()
        max_partner_markup = None
        if getattr(current_user, "partner_id", None):
            policy = get_partner_pricing_policy(db, current_user.partner_id)
            max_partner_markup = float(policy.max_partner_markup_percent) if policy.max_partner_markup_percent is not None else None
        return templates.TemplateResponse("client_edit.html", {
            "request": request,
            "current_user": current_user,
            "partners": partners,
            "client": client,
            "errors": errors,
            "form": {
                "full_name": full_name,
                "phone": phone,
                "email": email,
                "city": city,
                "notes": notes,
                "partner_id": partner_id_int,
                "can_access_catalog": can_access_catalog,
            },
            "partner_markup_percent": partner_markup_percent,
            "can_set_partner_markup": bool(getattr(current_user, "partner_id", None)),
            "max_partner_markup_percent": max_partner_markup,
            "active_menu": "clients"
        })

    # Партнёр может установить индивидуальную наценку для клиента (в пределах лимита)
    if getattr(current_user, "partner_id", None):
        raw = (partner_markup_percent or "").strip()
        if raw in ("", "None", "null"):
            (
                db.query(PartnerClientMarkup)
                .filter(
                    PartnerClientMarkup.partner_id == current_user.partner_id,
                    PartnerClientMarkup.client_id == client.id,
                )
                .delete()
            )
        else:
            try:
                pct = Decimal(str(raw)).quantize(Decimal("0.01"))
            except Exception:
                partners = db.query(Partner).all()
                policy = get_partner_pricing_policy(db, current_user.partner_id)
                max_partner_markup = float(policy.max_partner_markup_percent) if policy.max_partner_markup_percent is not None else None
                return templates.TemplateResponse("client_edit.html", {
                    "request": request,
                    "current_user": current_user,
                    "partners": partners,
                    "client": client,
                    "errors": {"partner_markup_percent": "Некорректное число"},
                    "form": {
                        "full_name": full_name,
                        "phone": phone,
                        "email": email,
                        "city": city,
                        "notes": notes,
                        "partner_id": partner_id_int,
                        "can_access_catalog": can_access_catalog,
                    },
                    "partner_markup_percent": partner_markup_percent,
                    "can_set_partner_markup": True,
                    "max_partner_markup_percent": max_partner_markup,
                    "active_menu": "clients",
                })

            if pct < 0:
                pct = Decimal("0.00")
            policy = get_partner_pricing_policy(db, current_user.partner_id)
            if policy.max_partner_markup_percent is not None and pct > policy.max_partner_markup_percent:
                partners = db.query(Partner).all()
                return templates.TemplateResponse("client_edit.html", {
                    "request": request,
                    "current_user": current_user,
                    "partners": partners,
                    "client": client,
                    "errors": {"partner_markup_percent": f"Максимум {policy.max_partner_markup_percent}%"},
                    "form": {
                        "full_name": full_name,
                        "phone": phone,
                        "email": email,
                        "city": city,
                        "notes": notes,
                        "partner_id": partner_id_int,
                        "can_access_catalog": can_access_catalog,
                    },
                    "partner_markup_percent": partner_markup_percent,
                    "can_set_partner_markup": True,
                    "max_partner_markup_percent": float(policy.max_partner_markup_percent),
                    "active_menu": "clients",
                })

            row = (
                db.query(PartnerClientMarkup)
                .filter(
                    PartnerClientMarkup.partner_id == current_user.partner_id,
                    PartnerClientMarkup.client_id == client.id,
                )
                .first()
            )
            if not row:
                row = PartnerClientMarkup(
                    partner_id=current_user.partner_id,
                    client_id=client.id,
                    partner_markup_percent=pct,
                )
                db.add(row)
            else:
                row.partner_markup_percent = pct

    client.name = name_normalized
    client.phone = phone
    client.email = email
    client.city = city
    client.notes = notes
    client.owner_partner_id = partner_id_int
    client.partner_id = partner_id_int
    client.can_access_catalog = bool(can_access_catalog)

    db.commit()
    db.refresh(client)
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{client_id}/delete")
async def delete_client(
    request: Request,
    client_id: int,
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own", "clients.create"])),
    db: Session = Depends(get_db)
):
    from fastapi.responses import JSONResponse
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        # Проверяем, это AJAX запрос?
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Клиент не найден"}
            )
        raise HTTPException(status_code=404, detail="Клиент не найден")
    
    _ensure_can_edit_client(client, current_user, db)
    
    # Проверяем наличие связанных заказов
    from app.models import Order, PartnerClientMarkup
    orders_count = db.query(Order).filter(Order.client_id == client_id).count()
    if orders_count > 0:
        auth_logger.warning(f"Попытка удаления клиента {client_id} с {orders_count} заказ(ами) пользователем {current_user.username}")
        error_msg = f"Невозможно удалить клиента: у него есть {orders_count} заказ(ов). Сначала удалите или измените заказы."
        # Проверяем, это AJAX запрос?
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": error_msg}
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # Проверяем наличие связанных накруток партнера и удаляем их
    markups_count = db.query(PartnerClientMarkup).filter(PartnerClientMarkup.client_id == client_id).count()
    if markups_count > 0:
        try:
            db.query(PartnerClientMarkup).filter(PartnerClientMarkup.client_id == client_id).delete(synchronize_session=False)
            auth_logger.info(f"Удалено {markups_count} накруток партнера для клиента {client_id}")
        except Exception as e:
            auth_logger.error(f"Ошибка при удалении накруток партнера для клиента {client_id}: {str(e)}")
            db.rollback()
            error_msg = f"Ошибка при удалении связанных данных: {str(e)}"
            # Проверяем, это AJAX запрос?
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"success": False, "error": error_msg}
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    try:
        db.delete(client)
        db.commit()
        auth_logger.info(f"Клиент {client_id} ({client.name}) успешно удален пользователем {current_user.username}")
    except Exception as e:
        db.rollback()
        auth_logger.error(f"Ошибка при удалении клиента {client_id}: {str(e)}", exc_info=True)
        error_msg = "Ошибка при удалении клиента. Проверьте логи для деталей."
        # Проверяем, это AJAX запрос?
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": error_msg}
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )
    
    # Проверяем, это AJAX запрос?
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Клиент успешно удален"}
        )
    
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{client_id}", response_class=HTMLResponse)
async def get_client_detail(
    request: Request,
    client_id: int,
    current_user: User = Depends(require_permission(["clients.view_all", "clients.view_own"])),
    db: Session = Depends(get_db)
):
    """Детали клиента с проверкой доступа"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    can_view_all = user_has_permission(current_user, db, "clients.view_all")
    can_view_own = user_has_permission(current_user, db, "clients.view_own")
    if not can_view_all:
        allowed = False
        if can_view_own:
            if client.owner_user_id == current_user.id:
                allowed = True
            if getattr(current_user, "partner_id", None) and (client.owner_partner_id == current_user.partner_id or client.partner_id == current_user.partner_id):
                allowed = True
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    finance = get_client_finance_stats(db, current_user, client_id)
    can_view_margin = user_has_permission(current_user, db, "prices.view_margin")

    return templates.TemplateResponse("client_detail.html", {
        "request": request,
        "current_user": current_user,
        "client": client,
        "active_menu": "clients",
        "finance": finance,
        "can_view_margin": can_view_margin,
    })
