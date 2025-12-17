"""
Маршруты для управления ароматами и каталогом
"""
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import pyotp
import qrcode
import secrets
from io import BytesIO
import base64
from app.db import get_db
from app.models import User, Fragrance, FragellaUsageLog, BackupCode
from app.services.auth_service import get_current_user_from_cookie, require_roles, verify_password, hash_password
from app.services.fragella_client import FragellaClient
from app.services.fragrance_import_service import FragranceImportService


router = APIRouter(prefix="/fragrances", tags=["fragrances"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def get_catalog(
    request: Request,
    q: Optional[str] = None,
    letter: Optional[str] = None,
    page: int = 1,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Страница каталога ароматов
    """
    # Проверяем права: все авторизованные пользователи могут просматривать каталог
    # Партнеры видят только свои ароматы, админы и менеджеры - все
    
    query = db.query(Fragrance)
    
    # Фильтрация по поисковому запросу
    if q:
        query = query.filter(
            (Fragrance.name.ilike(f"%{q}%")) | 
            (Fragrance.brand.ilike(f"%{q}%"))
        )
    
    # Фильтрация по первой букве бренда
    if letter:
        if letter == "0-9":
            # Фильтр для брендов, начинающихся с цифры
            query = query.filter(
                Fragrance.brand.startswith('0') |
                Fragrance.brand.startswith('1') |
                Fragrance.brand.startswith('2') |
                Fragrance.brand.startswith('3') |
                Fragrance.brand.startswith('4') |
                Fragrance.brand.startswith('5') |
                Fragrance.brand.startswith('6') |
                Fragrance.brand.startswith('7') |
                Fragrance.brand.startswith('8') |
                Fragrance.brand.startswith('9')
            )
        else:
            # Фильтр для брендов, начинающихся с определенной буквы
            query = query.filter(Fragrance.brand.ilike(f"{letter}%"))
    
    # Для партнеров показываем только их ароматы
    if current_user.role.name == "PARTNER" and hasattr(current_user, 'partner_id') and current_user.partner_id:
        query = query.filter(Fragrance.owner_partner_id == current_user.partner_id)
    
    # Пагинация (пока простая реализация)
    fragrances = query.offset((page - 1) * 20).limit(20).all()
    
    return templates.TemplateResponse("fragrances_list.html", {
        "request": request,
        "fragrances": fragrances,
        "q": q,
        "letter": letter,
        "page": page,
        "current_user": current_user,
        "active_menu": "fragrances"
    })


@router.get("/{fragrance_id}", response_class=HTMLResponse)
async def get_fragrance_detail(
    request: Request,
    fragrance_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Страница с деталями аромата
    """
    fragrance = db.query(Fragrance).filter(Fragrance.id == fragrance_id).first()
    
    if not fragrance:
        raise HTTPException(status_code=404, detail="Аромат не найден")
    
    # Проверяем права доступа к аромату
    if (current_user.role.name == "PARTNER" and 
        fragrance.owner_partner_id != current_user.partner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для просмотра этого аромата"
        )
    
    return templates.TemplateResponse("catalog_detail.html", {
        "request": request,
        "fragrance": fragrance,
        "current_user": current_user,
        "active_menu": "fragrances",
    })


# Маршруты для админки (управление каталогом)
admin_router = APIRouter(prefix="/admin/fragrances", tags=["admin-fragrances"])


@admin_router.get("/import", response_class=HTMLResponse)
async def get_import_page(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """
    Страница импорта ароматов из Fragella
    """
    return templates.TemplateResponse("admin_fragrance_import.html", {
        "request": request,
        "current_user": current_user
    })


@router.post("/admin/fragrances/import/search")
async def search_fragrances_for_import(
    query: str,
    limit: int = 5,
    current_user: User = Depends(require_roles(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """
    Поиск ароматов в Fragella для импорта
    """
    client = FragellaClient()
    try:
        results = await client.search_fragrances(query=query, limit=limit, db=db)
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при обращении к Fragella API: {str(e)}"
        )


@admin_router.post("/import/confirm")
async def confirm_import_fragrance(
    fragrance_data: dict,  # в реальном приложении использовался бы Pydantic-модель
    current_user: User = Depends(require_roles(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """
    Подтверждение импорта аромата
    """
    import_service = FragranceImportService()
    try:
        imported_fragrance = import_service.import_fragrance_from_external(fragrance_data, db)
        return {
            "success": True,
            "message": "Аромат успешно импортирован",
            "fragrance_id": imported_fragrance.id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при импорте аромата: {str(e)}"
        )


def generate_backup_codes(count: int = 10) -> list[str]:
    """
    Генерация резервных кодов
    """
    codes = []
    for _ in range(count):
        # Генерируем 8-символьный код из букв и цифр
        code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567') for _ in range(8))
        codes.append(code)
    return codes


# Подключаем маршруты администратора к основному роутеру
router.include_router(admin_router)
