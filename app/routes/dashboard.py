from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Partner
from app.services.stats_service import get_dashboard_stats_for_user
from app.services.auth_service import get_current_user_from_cookie, get_user_permission_keys

dashboard_router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


def _first_allowed_path(permission_keys: set[str]) -> str | None:
    is_admin = "*" in permission_keys
    if is_admin or "dashboard.view" in permission_keys:
        return "/dashboard"
    if is_admin or "price.search" in permission_keys or "price.upload" in permission_keys:
        return "/price/search"
    if is_admin or {"clients.view_all", "clients.view_own", "clients.create"}.intersection(permission_keys):
        return "/clients"
    if is_admin or {"orders.view_all", "orders.view_own", "orders.create"}.intersection(permission_keys):
        return "/orders"
    if is_admin or "partners.view_all" in permission_keys:
        return "/partners"
    if "partners.view_own" in permission_keys:
        return "/partners/me"
    if is_admin or {"catalog.view_full", "catalog.view_client", "catalog.manage"}.intersection(permission_keys):
        return "/catalog"
    return None


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    perms = get_user_permission_keys(current_user, db)
    if "*" not in perms and "dashboard.view" not in perms:
        dest = _first_allowed_path(perms)
        if dest and dest != "/dashboard":
            return RedirectResponse(url=dest, status_code=303)
        return RedirectResponse(url="/auth/logout", status_code=303)

    stats = get_dashboard_stats_for_user(db, current_user)
    dashboard_data = {
        "total_customers": stats.get("total_clients", 0),
        "total_orders": stats["orders_total"],
        "active_partners": db.query(Partner).filter(Partner.is_active == True).count(),
        "orders_today": stats["orders_today"],
        "customer_growth": "+12%",
        "order_growth": "+8%",
        "partner_growth": "+5%",
        "today_growth": "+3%",
        "orders_sum_total": stats["orders_sum_total"],
        "orders_sum_month": stats["orders_sum_month"],
        "top_partners": stats["top_partners"],
        "top_clients": stats["top_clients"],
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_menu": "dashboard",
        "current_user": current_user,
        **dashboard_data
    })
