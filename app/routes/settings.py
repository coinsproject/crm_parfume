from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import secrets

from app.db import get_db
from app.models import User, Role, Partner, Permission, RolePermission
from app.services.auth_service import require_roles, hash_password
from app.services.invitation_service import create_invitation
from app.logging_config import auth_logger

router = APIRouter(prefix="/settings", tags=["settings"])

templates = Jinja2Templates(directory="app/templates")

PERMISSION_GROUPS = {
    "dashboard": {
        "label": "Dashboard",
        "keys": ["dashboard.view"]
    },
    "clients": {
        "label": "Клиенты",
        "keys": ["clients.view_all", "clients.view_own", "clients.create"]
    },
    "orders": {
        "label": "Заказы",
        "keys": ["orders.view_all", "orders.view_own", "orders.create"]
    },
    "finance": {
        "label": "Финансы",
        "keys": ["prices.view_client", "prices.view_cost", "prices.view_margin", "prices.edit", "price.upload"]
    },
    "partners": {
        "label": "Партнёры",
        "keys": ["partners.view_all", "partners.view_own"]
    },
    "catalog": {
        "label": "Каталог",
        "keys": ["catalog.view_full", "catalog.view_client", "catalog.manage"]
    },
}

def _group_permissions(db: Session):
    permissions = db.query(Permission).all()
    perm_map = {perm.key: perm for perm in permissions}
    grouped = []
    for group_key, cfg in PERMISSION_GROUPS.items():
        group_perms = [perm_map[key] for key in cfg["keys"] if key in perm_map]
        grouped.append({
            "key": group_key,
            "label": cfg["label"],
            "permissions": group_perms
        })
    # add any permissions not mapped into "Прочее"
    mapped_keys = {k for cfg in PERMISSION_GROUPS.values() for k in cfg["keys"]}
    other_perms = [perm for key, perm in perm_map.items() if key not in mapped_keys]
    if other_perms:
        grouped.append({"key": "other", "label": "Прочее", "permissions": other_perms})
    return grouped


@router.get("/users", response_class=HTMLResponse)
async def get_users_list(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Вывод списка пользователей с индикацией статусов"""
    users = db.query(User).filter(User.deleted_at.is_(None)).all()

    for user in users:
        user.role = db.query(Role).filter(Role.id == user.role_id).first()
        if user.partner_id:
            user.partner = db.query(Partner).filter(Partner.id == user.partner_id).first()
        else:
            user.partner = None

    roles = db.query(Role).all()
    partners = db.query(Partner).all()
    pending_users = [user for user in users if user.pending_activation]

    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "pending_users": pending_users,
        "roles": roles,
        "partners": partners,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.get("/users/new", response_class=HTMLResponse)
async def get_create_user_form(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Форма для создания пользователя"""
    roles = db.query(Role).all()
    partners = db.query(Partner).all()

    return templates.TemplateResponse("admin_users_create.html", {
        "request": request,
        "roles": roles,
        "partners": partners,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.post("/users", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    full_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    role_id: int = Form(...),
    partner_id: Optional[int] = Form(None),
    is_active: bool = Form(False),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Создание пользователя админом"""
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    if email:
        existing_email_user = db.query(User).filter(User.email == email).first()
        if existing_email_user:
            raise HTTPException(status_code=400, detail="Email уже используется")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Роль не найдена")

    if partner_id:
        partner = db.query(Partner).filter(Partner.id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=400, detail="Партнёр не найден")

    import secrets
    temp_password = secrets.token_urlsafe(12)
    new_user = User(
        username=username,
        full_name=full_name,
        email=email if email else None,
        password_hash=hash_password(temp_password),
        role_id=role_id,
        partner_id=partner_id if partner_id else None,
        is_active=bool(is_active),
        pending_activation=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return templates.TemplateResponse("admin_users_success.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_users",
        "username": username,
        "full_name": full_name,
        "temp_password": temp_password
    })


@router.get("/users/{user_id:int}/edit", response_class=HTMLResponse)
async def get_edit_user_form(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Форма редактирования пользователя"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    roles = db.query(Role).all()
    partners = db.query(Partner).all()

    return templates.TemplateResponse("admin_users_edit.html", {
        "request": request,
        "user": user,
        "roles": roles,
        "partners": partners,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.post("/users/{user_id:int}", response_class=HTMLResponse)
async def update_user(
    request: Request,
    user_id: int,
    full_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    role_id: int = Form(...),
    partner_id: Optional[int] = Form(None),
    is_active: bool = Form(False),
    is_2fa_enabled: bool = Form(False),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Обновление пользователя"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if email:
        existing_email_user = db.query(User).filter(User.email == email, User.id != user_id).first()
        if existing_email_user:
            raise HTTPException(status_code=400, detail="Email уже используется")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Роль не найдена")

    if partner_id:
        partner = db.query(Partner).filter(Partner.id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=400, detail="Партнёр не найден")

    user.full_name = full_name
    user.email = email if email else None
    user.is_active = bool(is_active)
    user.is_2fa_enabled = is_2fa_enabled

    if current_user.id == user.id and user.role and user.role.name == "ADMIN":
        user.partner_id = partner_id
    else:
        user.role_id = role_id
        user.partner_id = partner_id

    db.commit()
    db.refresh(user)

    return templates.TemplateResponse("admin_users_updated.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "settings_users",
        "user": user
    })


@router.post("/users/{user_id:int}/activate", response_class=JSONResponse)
async def activate_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Активация учётки после приглашения"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not target_user.pending_activation:
        raise HTTPException(status_code=400, detail="Пользователь не ждёт активации")

    target_user.is_active = True
    target_user.pending_activation = False
    db.commit()

    auth_logger.info(f"Admin {current_user.username} activated user {target_user.username}")
    return {"success": True, "message": f"Пользователь {target_user.username} активирован"}


@router.post("/users/{user_id:int}/reject", response_class=JSONResponse)
async def reject_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Отклонение нового пользователя"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not target_user.pending_activation:
        raise HTTPException(status_code=400, detail="Пользователь не ждёт активации")

    db.delete(target_user)
    db.commit()

    auth_logger.info(f"Admin {current_user.username} rejected user registration for {target_user.username}")
    return {"success": True, "message": f"Регистрация {target_user.username} отменена"}


@router.post("/users/{user_id:int}/reset_password", response_class=JSONResponse)
async def reset_user_password_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Сброс пароля пользователю: выдаём новый временный пароль (для передачи вручную)."""
    if getattr(current_user, "id", None) == user_id:
        raise HTTPException(status_code=400, detail="Нельзя сбросить пароль самому себе здесь")

    target_user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    temp_password = secrets.token_urlsafe(8)
    target_user.password_hash = hash_password(temp_password)
    target_user.is_active = True
    target_user.pending_activation = False
    db.add(target_user)
    db.commit()

    auth_logger.info(f"Admin {current_user.username} reset password for user_id={user_id}")
    return {"success": True, "temp_password": temp_password}


@router.post("/users/{user_id:int}/delete", response_class=RedirectResponse)
async def delete_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Удаление пользователя:
    - Если нет заказов - полное удаление
    - Если есть заказы, но все завершены - полное удаление
    - Если есть незавершенные заказы - только блокировка
    """
    if getattr(current_user, "id", None) == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверяем наличие заказов пользователя
    from app.models import Order
    # Статусы, которые считаются завершенными полностью
    COMPLETED_STATUSES = ["DELIVERED", "CANCELLED", "RETURNED"]
    
    # Заказы, созданные пользователем
    created_orders = db.query(Order).filter(Order.created_by_user_id == user_id).all()
    
    # Заказы партнера пользователя (если пользователь связан с партнером)
    partner_orders = []
    if target_user.partner_id:
        partner_orders = db.query(Order).filter(Order.partner_id == target_user.partner_id).all()
    
    all_orders = created_orders + partner_orders
    orders_count = len(all_orders)
    
    # Проверяем, есть ли незавершенные заказы
    incomplete_orders = [o for o in all_orders if o.status not in COMPLETED_STATUSES]
    
    if orders_count == 0:
        # Нет заказов - полное удаление
        try:
            # Отвязываем primary user у партнёра, если он указывал на этого пользователя
            partner = db.query(Partner).filter(Partner.user_id == target_user.id).first()
            if partner:
                partner.user_id = None
                db.add(partner)
            
            # Удаляем пользователя
            db.delete(target_user)
            db.commit()
            auth_logger.info(f"Admin {current_user.username} fully deleted user_id={user_id} (no orders)")
        except Exception as e:
            db.rollback()
            auth_logger.error(f"Error deleting user_id={user_id}: {str(e)}")
            # При ошибке блокируем
            target_user.is_active = False
            target_user.deleted_at = datetime.utcnow()
            db.add(target_user)
            db.commit()
            raise HTTPException(status_code=500, detail="Ошибка при удалении пользователя")
    elif len(incomplete_orders) > 0:
        # Есть незавершенные заказы - только блокировка
        target_user.is_active = False
        target_user.deleted_at = datetime.utcnow()
        target_user.pending_activation = False
        target_user.email = None
        target_user.username = f"deleted_{target_user.id}_{int(target_user.deleted_at.timestamp())}"
        target_user.full_name = None
        target_user.password_hash = hash_password(secrets.token_urlsafe(32))
        
        # Отвязываем primary user у партнёра
        partner = db.query(Partner).filter(Partner.user_id == target_user.id).first()
        if partner:
            partner.user_id = None
            db.add(partner)
        
        db.add(target_user)
        db.commit()
        auth_logger.info(
            f"Admin {current_user.username} blocked user_id={user_id} (has {len(incomplete_orders)} incomplete orders)"
        )
    else:
        # Все заказы завершены - можно удалить
        try:
            # Отвязываем primary user у партнёра
            partner = db.query(Partner).filter(Partner.user_id == target_user.id).first()
            if partner:
                partner.user_id = None
                db.add(partner)
            
            # Удаляем пользователя
            db.delete(target_user)
            db.commit()
            auth_logger.info(
                f"Admin {current_user.username} fully deleted user_id={user_id} (all {orders_count} orders completed)"
            )
        except Exception as e:
            db.rollback()
            auth_logger.error(f"Error deleting user_id={user_id}: {str(e)}")
            # При ошибке блокируем
            target_user.is_active = False
            target_user.deleted_at = datetime.utcnow()
            db.add(target_user)
            db.commit()
            raise HTTPException(status_code=500, detail="Ошибка при удалении пользователя")

    return RedirectResponse(url="/settings/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/users/{user_id:int}/delete", response_class=RedirectResponse)
async def delete_user_get(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Удаление через GET (если кнопка отправила запрос не POST)."""
    return await delete_user_endpoint(user_id=user_id, current_user=current_user, db=db)


@router.post("/users/invitations", response_class=JSONResponse)
async def create_invitation_endpoint(
    email: str = Form(...),
    role_id: str = Form(...),
    partner_id: Optional[str] = Form(None),
    partner_full_name: Optional[str] = Form(None),
    partner_phone: Optional[str] = Form(None),
    partner_telegram: Optional[str] = Form(None),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Создание приглашения и выдача ссылки"""
    try:
        role_id_int = int(role_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный role_id")

    role = db.query(Role).filter(Role.id == role_id_int).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Роль не найдена")

    partner_id_int: Optional[int] = None
    if partner_id not in (None, "", "None", "null"):
        try:
            partner_id_int = int(partner_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный partner_id")

    # Если роль PARTNER, проверяем обязательные поля
    if role.name == "PARTNER":
        partner_full_name_clean = (partner_full_name or "").strip()
        if not partner_full_name_clean or len(partner_full_name_clean) < 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите ФИО партнёра (минимум 5 символов)")
        phone_clean = "".join(ch for ch in (partner_phone or "") if ch.isdigit())
        if not phone_clean or len(phone_clean) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите телефон партнёра (не меньше 10 цифр)")
        # Telegram будет заполнен партнером при принятии приглашения, не проверяем здесь

    if partner_id_int:
        partner = db.query(Partner).filter(Partner.id == partner_id_int).first()
        if not partner:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Партнёр не найден")

    try:
        invitation = create_invitation(
            email=email,
            role=role,
            db=db,
            partner_id=partner_id_int,
            created_by_user=current_user,
            partner_full_name=(partner_full_name or "").strip() if partner_full_name else None,
            partner_phone=(partner_phone or "").strip() if partner_phone else None,
            partner_telegram=(partner_telegram or "").strip() if partner_telegram else None,
        )

        auth_logger.info(f"Admin {current_user.username} created invitation {invitation.id} for email {email}")

        return {
            "success": True,
            "invitation_token": invitation.token,
            "invitation_link": f"/invite/{invitation.token}",
            "expires_at": invitation.expires_at.isoformat()
        }
    except Exception as e:
        auth_logger.error(f"Error creating invitation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании приглашения: {str(e)}"
        )


@router.get("/roles", response_class=HTMLResponse)
async def list_roles(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    roles = db.query(Role).all()
    for role in roles:
        role.permissions = db.query(Permission).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).filter(RolePermission.role_id == role.id).all()

    return templates.TemplateResponse("admin_roles.html", {
        "request": request,
        "roles": roles,
        "current_user": current_user,
        "active_menu": "settings_roles"
    })


@router.get("/roles/new", response_class=HTMLResponse)
async def create_role_form(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    grouped_permissions = _group_permissions(db)
    return templates.TemplateResponse("admin_role_form.html", {
        "request": request,
        "role": None,
        "grouped_permissions": grouped_permissions,
        "selected_keys": set(),
        "current_user": current_user,
        "active_menu": "settings_roles",
        "mode": "create"
    })


@router.post("/roles")
async def create_role(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    permission_keys: List[str] = Form([]),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    existing = db.query(Role).filter(Role.name == name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="�������� � ⮣� ������ 㦥 �������")

    role = Role(name=name, description=description, is_system=False)
    db.add(role)
    db.commit()
    db.refresh(role)

    if permission_keys:
        permissions = db.query(Permission).filter(Permission.key.in_(permission_keys)).all()
        for perm in permissions:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()

    return RedirectResponse(url="/settings/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/roles/{role_id}/edit", response_class=HTMLResponse)
async def edit_role_form(
    request: Request,
    role_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="���� �� ������")

    role.permissions = db.query(Permission).join(
        RolePermission, RolePermission.permission_id == Permission.id
    ).filter(RolePermission.role_id == role.id).all()

    grouped_permissions = _group_permissions(db)
    selected_keys = {perm.key for perm in role.permissions}

    return templates.TemplateResponse("admin_role_form.html", {
        "request": request,
        "role": role,
        "grouped_permissions": grouped_permissions,
        "selected_keys": selected_keys,
        "current_user": current_user,
        "active_menu": "settings_roles",
        "mode": "edit"
    })


@router.post("/roles/{role_id}")
async def update_role(
    role_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    permission_keys: List[str] = Form([]),
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="���� �� ������")

    # ����⨢��塞 ��� �� �ப� ���ᥣ��
    if not role.is_system or role.name != "ADMIN":
        role.name = name
    role.description = description

    # ������塞 permissions
    if role.name == "ADMIN":
        # ADMIN ����� ��� ���� � UI ����������
        permission_keys = [perm.key for perm in db.query(Permission).all()]

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    if permission_keys:
        permissions = db.query(Permission).filter(Permission.key.in_(permission_keys)).all()
        for perm in permissions:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()

    return RedirectResponse(url="/settings/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/roles/{role_id}/delete", response_class=JSONResponse)
async def delete_role(
    role_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="���� �� ������")
    if role.is_system or role.name == "ADMIN":
        raise HTTPException(status_code=400, detail="Системную роль удалить нельзя")

    users_with_role = db.query(User).filter(User.role_id == role_id, User.deleted_at.is_(None)).count()
    if users_with_role > 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить роль, пока к ней привязаны пользователи")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.delete(role)
    db.commit()

    return {"success": True}
