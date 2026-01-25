"""
Админка для управления брендами и алиасами
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional
from datetime import datetime

from app.db import get_db
from app.models import Brand, BrandAlias
from app.services.auth_service import require_roles
from app.services.key_normalization import normalize_key
from app.services.brand_bootstrap_service import (
    get_brand_candidates,
    create_brand_from_candidate,
    map_candidate_to_brand
)
from app.logging_config import price_logger


router = APIRouter(prefix="/admin/brands", tags=["admin_brands"])

templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def brands_list(
    request: Request,
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Список брендов с поиском"""
    per_page = 50
    page = max(1, page)
    
    # Базовый запрос - получаем ВСЕ бренды без фильтрации
    query = db.query(Brand)
    
    # Поиск
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        # Используем JOIN вместо IN для избежания проблем с большим количеством результатов
        query = query.outerjoin(BrandAlias, Brand.id == BrandAlias.brand_id).filter(
            or_(
                Brand.name_canonical.ilike(search_term),
                BrandAlias.alias_upper.ilike(search_term.upper())
            )
        ).distinct()
    
    # Подсчет общего количества
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 1
    page = min(page, pages) if pages > 0 else 1
    
    # Получаем бренды с количеством алиасов
    brands = (
        query.order_by(Brand.name_canonical)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    
    # Загружаем количество алиасов для каждого бренда
    for brand in brands:
        brand.aliases_count = db.query(BrandAlias).filter(BrandAlias.brand_id == brand.id).count()
    
    return templates.TemplateResponse("admin_brands_list.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "normalization",
        "brands": brands,
        "q": q or "",
        "page": page,
        "pages": pages,
        "total": total,
    })


@router.get("/create", response_class=HTMLResponse)
async def brand_create_form(
    request: Request,
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Форма создания бренда"""
    return templates.TemplateResponse("admin_brand_edit.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "normalization",
        "brand": None,
        "aliases": [],
    })


@router.post("/create", response_class=RedirectResponse)
async def brand_create(
    request: Request,
    name_canonical: str = Form(...),
    alias: str = Form(""),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Создание бренда"""
    name_canonical = name_canonical.strip()
    if not name_canonical:
        raise HTTPException(status_code=400, detail="Название бренда не может быть пустым")
    
    # Проверяем, нет ли уже такого бренда
    existing = db.query(Brand).filter(Brand.name_canonical.ilike(name_canonical)).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Бренд '{name_canonical}' уже существует")
    
    brand = Brand(name_canonical=name_canonical, key=normalize_key(name_canonical) or "")
    db.add(brand)
    db.flush()  # Получаем ID бренда
    
    # Если указан алиас, создаем его
    alias_text = alias.strip() if alias else ""
    if alias_text:
        alias_upper = alias_text.upper()
        # Проверяем, нет ли уже такого алиаса
        existing_alias = db.query(BrandAlias).filter(BrandAlias.alias_upper == alias_upper).first()
        if not existing_alias:
            alias_key = normalize_key(alias_text) or ""
            brand_alias = BrandAlias(
                brand_id=brand.id,
                alias_upper=alias_upper,
                alias_key=alias_key
            )
            db.add(brand_alias)
            price_logger.info(f"Admin {current_user.id} created brand {brand.id} with alias '{alias_upper}'")
    
    db.commit()
    db.refresh(brand)
    
    price_logger.info(f"Admin {current_user.id} created brand {brand.id}: {name_canonical}")
    
    return RedirectResponse(url=f"/admin/brands/{brand.id}", status_code=303)


@router.get("/bootstrap", response_class=HTMLResponse)
async def brands_bootstrap(
    request: Request,
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Страница бутстрапа брендов из прайса"""
    try:
        candidates = get_brand_candidates(db, limit=500)
        brands = db.query(Brand).order_by(Brand.name_canonical).all()
        
        return templates.TemplateResponse("admin_brand_bootstrap.html", {
            "request": request,
            "current_user": current_user,
            "active_menu": "normalization",
            "candidates": candidates or [],
            "brands": brands or [],
        })
    except Exception as e:
        price_logger.exception(f"Error loading bootstrap page: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при загрузке страницы бутстрапа: {str(e)[:200]}"
        )


@router.post("/bootstrap/create", response_class=JSONResponse)
async def bootstrap_create_brand(
    request: Request,
    candidate: str = Form(...),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Создание бренда и алиаса из кандидата"""
    try:
        brand, alias = create_brand_from_candidate(db, candidate)
        price_logger.info(f"Admin {current_user.id} created brand {brand.id} from candidate '{candidate}'")
        return {
            "success": True,
            "brand_id": brand.id,
            "brand_name": brand.name_canonical,
            "alias": alias.alias_upper
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        price_logger.exception(f"Error creating brand from candidate '{candidate}': {e}")
        return {
            "success": False,
            "error": f"Ошибка при создании бренда: {str(e)[:200]}"
        }


@router.post("/bootstrap/map", response_class=JSONResponse)
async def bootstrap_map_to_brand(
    request: Request,
    candidate: str = Form(...),
    brand_id: int = Form(...),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Привязка кандидата к существующему бренду"""
    try:
        alias = map_candidate_to_brand(db, candidate, brand_id)
        price_logger.info(f"Admin {current_user.id} mapped candidate '{candidate}' to brand {brand_id}")
        return {
            "success": True,
            "alias_id": alias.id,
            "alias": alias.alias_upper,
            "brand_id": brand_id
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        price_logger.exception(f"Error mapping candidate '{candidate}' to brand {brand_id}: {e}")
        return {
            "success": False,
            "error": f"Ошибка при привязке: {str(e)[:200]}"
        }


@router.get("/{brand_id}", response_class=HTMLResponse)
async def brand_edit_form(
    request: Request,
    brand_id: int,
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Форма редактирования бренда"""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    
    # Загружаем алиасы
    aliases = db.query(BrandAlias).filter(BrandAlias.brand_id == brand_id).order_by(BrandAlias.alias_upper).all()
    
    return templates.TemplateResponse("admin_brand_edit.html", {
        "request": request,
        "current_user": current_user,
        "active_menu": "normalization",
        "brand": brand,
        "aliases": aliases,
    })


@router.post("/{brand_id}", response_class=RedirectResponse)
async def brand_update(
    request: Request,
    brand_id: int,
    name_canonical: str = Form(...),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Обновление бренда"""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    
    name_canonical = name_canonical.strip()
    if not name_canonical:
        raise HTTPException(status_code=400, detail="Название бренда не может быть пустым")
    
    # Проверяем, нет ли уже такого бренда (кроме текущего)
    existing = db.query(Brand).filter(
        and_(
            Brand.name_canonical.ilike(name_canonical),
            Brand.id != brand_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Бренд '{name_canonical}' уже существует")
    
    old_name = brand.name_canonical
    brand.name_canonical = name_canonical
    brand.key = normalize_key(name_canonical) or ""
    brand.updated_at = datetime.utcnow()
    db.commit()
    
    price_logger.info(f"Admin {current_user.id} updated brand {brand_id}: {old_name} -> {name_canonical}")
    
    return RedirectResponse(url=f"/admin/brands/{brand_id}", status_code=303)


@router.post("/{brand_id}/aliases", response_class=RedirectResponse)
async def alias_add(
    request: Request,
    brand_id: int,
    alias: str = Form(...),
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Добавление алиаса"""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    
    alias_upper = alias.strip().upper()
    if not alias_upper:
        raise HTTPException(status_code=400, detail="Алиас не может быть пустым")
    
    # Проверяем, нет ли уже такого алиаса
    existing = db.query(BrandAlias).filter(BrandAlias.alias_upper == alias_upper).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Алиас '{alias}' уже существует")
    
    alias_key = normalize_key(alias) or ""
    brand_alias = BrandAlias(brand_id=brand_id, alias_upper=alias_upper, alias_key=alias_key)
    db.add(brand_alias)
    db.commit()
    
    price_logger.info(f"Admin {current_user.id} added alias '{alias_upper}' to brand {brand_id}")
    
    return RedirectResponse(url=f"/admin/brands/{brand_id}", status_code=303)


@router.post("/{brand_id}/aliases/{alias_id}/delete", response_class=RedirectResponse)
async def alias_delete(
    request: Request,
    brand_id: int,
    alias_id: int,
    current_user = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Удаление алиаса"""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    
    alias = db.query(BrandAlias).filter(
        BrandAlias.id == alias_id,
        BrandAlias.brand_id == brand_id
    ).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Алиас не найден")
    
    alias_upper = alias.alias_upper
    db.delete(alias)
    db.commit()
    
    price_logger.info(f"Admin {current_user.id} deleted alias '{alias_upper}' from brand {brand_id}")
    
    return RedirectResponse(url=f"/admin/brands/{brand_id}", status_code=303)

