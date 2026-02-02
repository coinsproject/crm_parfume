from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.routes.dashboard import dashboard_router
from app.routes.auth import router as auth_router
from app.routes.settings import router as settings_router
from app.routes.admin_users import router as admin_users_router
from app.routes.admin_brands import router as admin_brands_router
from app.routes.settings_2fa import router as settings_2fa_router
from app.routes.clients import router as clients_router
from app.routes.orders import router as orders_router
from app.routes.price import router as price_router
from app.routes.normalization import router as normalization_router
from app.routes.partners import router as partners_router
from app.routes.purchase_requests import router as purchase_requests_router
from app.routes.notifications import router as notifications_router
from app.routes.release_notes import router as release_notes_router
from app.routes.actions import router as actions_router
from app.routes.invite import router as invite_router
from app.routes.catalog_api import router as catalog_api_router
from app.routes.admin_catalog import router as admin_catalog_router
from app.routes.internal_catalog import router as internal_catalog_router
from app.routes.catalog_items import router as catalog_items_router
from app.routes.mobile_api import router as mobile_api_router
from app.routes.documentation import router as documentation_router
# Инициализация кастомных логгеров, чтобы они точно повесили хендлеры
from app.logging_config import partners_logger, orders_logger  # noqa: F401
from app.services.auth_service import get_current_user_from_cookie, get_user_permission_keys
from app.db import SessionLocal
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="CRM System")

# Подключение статических файлов
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Подключение шаблонов
templates = Jinja2Templates(directory="app/templates")

# Добавляем фильтр для парсинга JSON
import json
def from_json_filter(value):
    """Фильтр Jinja2 для парсинга JSON"""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}

templates.env.filters["from_json"] = from_json_filter

# Добавляем фильтр date для Jinja2
from datetime import datetime, date
def date_filter(value, format='%Y-%m-%d'):
    """Фильтр Jinja2 для форматирования даты"""
    if value == 'now':
        return datetime.now().strftime(format)
    if isinstance(value, datetime):
        return value.strftime(format)
    if isinstance(value, date):
        return value.strftime(format)
    return value

templates.env.filters["date"] = date_filter

# Добавляем версию в глобальный контекст шаблонов
from app.version import __version__
templates.env.globals["current_version"] = __version__


class PermissionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Всегда задаём атрибуты, чтобы шаблоны могли безопасно читать их
        request.state.permission_keys = set()
        request.state.is_admin = False

        db = None
        try:
            db = SessionLocal()
            try:
                user = None
                if request.cookies.get("access_token"):
                    try:
                        user = get_current_user_from_cookie(request, db)
                    except HTTPException:
                        user = None
                if user:
                    keys = get_user_permission_keys(user, db)
                    request.state.permission_keys = keys
                    request.state.is_admin = ("*" in keys)
            finally:
                db.close()
        except Exception:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

        return await call_next(request)


app.add_middleware(PermissionsMiddleware)

# Подключение маршрутов
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(admin_users_router)
app.include_router(admin_brands_router)
app.include_router(settings_2fa_router)
app.include_router(clients_router)
app.include_router(orders_router)
app.include_router(price_router)
app.include_router(normalization_router)
app.include_router(partners_router)
app.include_router(purchase_requests_router)
app.include_router(notifications_router)
app.include_router(release_notes_router)
app.include_router(actions_router)
app.include_router(invite_router)
app.include_router(catalog_api_router)
app.include_router(admin_catalog_router)
app.include_router(internal_catalog_router)
app.include_router(catalog_items_router)
app.include_router(mobile_api_router)
app.include_router(documentation_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/auth/login")
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return HTMLResponse("<h3>Недостаточно прав</h3>", status_code=403)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработчик ошибок валидации запросов"""
    errors = exc.errors()
    
    # Формируем понятное сообщение об ошибке
    error_messages = []
    for error in errors:
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        msg = error.get("msg", "Validation error")
        error_type = error.get("type", "")
        
        # Более понятные сообщения для типичных ошибок
        if error_type == "missing":
            field_name = loc.split(" -> ")[-1] if " -> " in loc else loc
            if field_name in ["username", "password"]:
                error_messages.append(f"Не указано обязательное поле: {field_name}")
            else:
                error_messages.append(f"Отсутствует обязательное поле: {field_name}")
        elif error_type == "value_error":
            error_messages.append(f"Некорректное значение в поле {loc}: {msg}")
        else:
            error_messages.append(f"Ошибка валидации в {loc}: {msg}")
    
    # Если это API запрос, возвращаем JSON
    accept = request.headers.get("accept", "")
    if "application/json" in accept or request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": error_messages if error_messages else "Ошибка валидации данных",
                "errors": errors
            }
        )
    
    # Для HTML запросов возвращаем простое сообщение
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": error_messages if error_messages else "Ошибка валидации данных"
        }
    )

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    # Используем новую зависимость для получения текущего пользователя из cookie
    from app.services.auth_service import get_current_user_from_cookie
    from app.logging_config import auth_logger
    try:
        current_user = get_current_user_from_cookie(request, db)
        auth_logger.info(f"Root endpoint - Current user: {current_user.username if current_user else 'None'}")
        return RedirectResponse(url="/dashboard")
    except Exception as e:
        auth_logger.error(f"Root endpoint - Error: {e}")
        return RedirectResponse(url="/auth/login")

@app.get("/health")
async def health():
    return {"status": "ok"}
