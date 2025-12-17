"""
Каталог ароматов
"""
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Fragrance, Client
from app.services.auth_service import require_permission

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


def _client_catalog_allowed(db: Session, user: User) -> bool:
    # проверяем наличие клиента с флагом can_access_catalog, привязанного к пользователю/партнёру
    return db.query(Client).filter(
        Client.can_access_catalog == True,
        ((Client.owner_user_id == user.id) | (Client.owner_partner_id == getattr(user, "partner_id", None)))
    ).first() is not None


@router.get("/catalog", response_class=HTMLResponse)
async def get_catalog(
    request: Request,
    q: str = None,
    letter: str = None,
    page: int = 1,
    current_user: User = Depends(require_permission(["catalog.view_full", "catalog.manage"])),
    db: Session = Depends(get_db)
):
    query = db.query(Fragrance)

    if q:
        query = query.filter((Fragrance.name.ilike(f"%{q}%")) | (Fragrance.brand.ilike(f"%{q}%")))
    if letter:
        if letter == "0-9":
            query = query.filter(Fragrance.brand.like('0%') | Fragrance.brand.like('1%') | Fragrance.brand.like('2%') | Fragrance.brand.like('3%') | Fragrance.brand.like('4%') | Fragrance.brand.like('5%') | Fragrance.brand.like('6%') | Fragrance.brand.like('7%') | Fragrance.brand.like('8%') | Fragrance.brand.like('9%'))
        else:
            query = query.filter(Fragrance.brand.ilike(f"{letter}%"))

    if current_user.role.name == "PARTNER" and getattr(current_user, 'partner_id', None):
        query = query.filter(Fragrance.owner_partner_id == current_user.partner_id)

    fragrances = query.offset((page - 1) * 20).limit(20).all()

    return templates.TemplateResponse("catalog_list.html", {
        "request": request,
        "fragrances": fragrances,
        "q": q,
        "letter": letter,
        "page": page,
        "current_user": current_user,
        "active_menu": "catalog"
    })


@router.get("/catalog/{fragrance_id}", response_class=HTMLResponse)
async def get_fragrance_detail(
    request: Request,
    fragrance_id: int,
    current_user: User = Depends(require_permission(["catalog.view_full", "catalog.manage"])),
    db: Session = Depends(get_db)
):
    fragrance = db.query(Fragrance).filter(Fragrance.id == fragrance_id).first()
    if not fragrance:
        raise HTTPException(status_code=404, detail="Аромат не найден")

    if current_user.role.name == "PARTNER" and getattr(current_user, 'partner_id', None):
        if fragrance.owner_partner_id and fragrance.owner_partner_id != current_user.partner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому аромату")

    return templates.TemplateResponse("catalog_detail.html", {
        "request": request,
        "fragrance": fragrance,
        "current_user": current_user,
        "active_menu": "catalog"
    })


@router.get("/client/catalog", response_class=HTMLResponse)
async def client_catalog_list(
    request: Request,
    q: str = None,
    letter: str = None,
    page: int = 1,
    current_user: User = Depends(require_permission("catalog.view_client")),
    db: Session = Depends(get_db)
):
    if not _client_catalog_allowed(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Каталог недоступен")

    query = db.query(Fragrance)
    if q:
        query = query.filter((Fragrance.name.ilike(f"%{q}%")) | (Fragrance.brand.ilike(f"%{q}%")))
    if letter:
        if letter == "0-9":
            query = query.filter(Fragrance.brand.like('0%') | Fragrance.brand.like('1%') | Fragrance.brand.like('2%') | Fragrance.brand.like('3%') | Fragrance.brand.like('4%') | Fragrance.brand.like('5%') | Fragrance.brand.like('6%') | Fragrance.brand.like('7%') | Fragrance.brand.like('8%') | Fragrance.brand.like('9%'))
        else:
            query = query.filter(Fragrance.brand.ilike(f"{letter}%"))
    fragrances = query.offset((page - 1) * 20).limit(20).all()
    return templates.TemplateResponse("catalog_client_list.html", {
        "request": request,
        "fragrances": fragrances,
        "q": q,
        "letter": letter,
        "page": page,
    })


@router.get("/client/catalog/{fragrance_id}", response_class=HTMLResponse)
async def client_catalog_detail(
    request: Request,
    fragrance_id: int,
    current_user: User = Depends(require_permission("catalog.view_client")),
    db: Session = Depends(get_db)
):
    if not _client_catalog_allowed(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Каталог недоступен")
    fragrance = db.query(Fragrance).filter(Fragrance.id == fragrance_id).first()
    if not fragrance:
        raise HTTPException(status_code=404, detail="Аромат не найден")
    return templates.TemplateResponse("catalog_client_detail.html", {
        "request": request,
        "fragrance": fragrance,
    })
