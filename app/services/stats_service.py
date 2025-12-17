from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Dict
from app.models import User, Order, Client, Partner
from app.services.auth_service import user_has_permission


def _order_visibility_filter(current_user: User):
    return (Order.partner_id == getattr(current_user, "partner_id", None)) | (
        Order.created_by_user_id == current_user.id
    )


def get_dashboard_stats_for_user(db: Session, current_user: User) -> Dict:
    """Статистика дашборда с учётом прав/владения."""
    today = datetime.utcnow().date()
    first_day_of_month = today.replace(day=1)

    can_view_all_orders = user_has_permission(current_user, db, "orders.view_all")
    can_view_own_orders = user_has_permission(current_user, db, "orders.view_own")
    can_view_all_clients = user_has_permission(current_user, db, "clients.view_all")
    can_view_own_clients = user_has_permission(current_user, db, "clients.view_own")

    order_filters = []
    if not can_view_all_orders and can_view_own_orders:
        order_filters.append(_order_visibility_filter(current_user))

    client_filters = []
    if not can_view_all_clients and can_view_own_clients:
        client_filters.append(
            (Client.owner_partner_id == getattr(current_user, "partner_id", None))
            | (Client.owner_user_id == current_user.id)
        )

    # Кол-во заказов
    orders_total_query = db.query(Order)
    if order_filters:
        orders_total_query = orders_total_query.filter(*order_filters)
    orders_total = orders_total_query.count()

    # Заказы за сегодня
    orders_today_query = db.query(Order).filter(func.date(Order.created_at) == today)
    if order_filters:
        orders_today_query = orders_today_query.filter(*order_filters)
    orders_today = orders_today_query.count()

    # Сумма заказов (всего и за месяц) — используем total_client_amount
    orders_sum_total_query = db.query(func.coalesce(func.sum(Order.total_client_amount), 0))
    if order_filters:
        orders_sum_total_query = orders_sum_total_query.filter(*order_filters)
    orders_sum_total = orders_sum_total_query.scalar() or 0

    orders_sum_month_query = db.query(func.coalesce(func.sum(Order.total_client_amount), 0)).filter(
        func.date(Order.created_at) >= first_day_of_month
    )
    if order_filters:
        orders_sum_month_query = orders_sum_month_query.filter(*order_filters)
    orders_sum_month = orders_sum_month_query.scalar() or 0

    # Топ партнёров (только если есть доступ ко всем)
    top_partners = []
    if can_view_all_orders:
        top_partners_query = (
            db.query(
                Partner.name,
                func.sum(Order.total_client_amount).label("sum_amount"),
                func.count(Order.id).label("order_count"),
            )
            .join(Order, Partner.id == Order.partner_id)
            .group_by(Partner.id, Partner.name)
            .order_by(func.sum(Order.total_client_amount).desc())
            .limit(5)
        )
        top_partners = [
            {
                "name": row.name,
                "sum_amount": float(row.sum_amount or 0),
                "order_count": row.order_count,
            }
            for row in top_partners_query.all()
        ]

    # Топ клиентов (с учётом фильтра)
    top_clients_query = db.query(
        Client.name,
        func.sum(Order.total_client_amount).label("sum_amount"),
        func.count(Order.id).label("order_count"),
    ).join(Order, Client.id == Order.client_id)
    if order_filters:
        top_clients_query = top_clients_query.filter(*order_filters)
    if client_filters and not can_view_all_clients:
        top_clients_query = top_clients_query.filter(*client_filters)

    top_clients = [
        {
            "name": row.name,
            "sum_amount": float(row.sum_amount or 0),
            "order_count": row.order_count,
        }
        for row in top_clients_query.group_by(Client.id, Client.name)
        .order_by(func.sum(Order.total_client_amount).desc())
        .limit(5)
        .all()
    ]

    # Кол-во клиентов
    total_clients_query = db.query(Client)
    if client_filters and not can_view_all_clients:
        total_clients_query = total_clients_query.filter(*client_filters)
    total_clients = total_clients_query.count()

    return {
        "orders_total": orders_total,
        "orders_today": orders_today,
        "orders_sum_total": float(orders_sum_total),
        "orders_sum_month": float(orders_sum_month),
        "top_partners": top_partners,
        "top_clients": top_clients,
        "total_clients": total_clients,
    }


def get_orders_stats_for_user(db: Session, current_user: User) -> Dict:
    """Статистика по заказам по статусам"""
    can_view_all_orders = user_has_permission(current_user, db, "orders.view_all")
    order_filters = []
    if not can_view_all_orders:
        order_filters.append(_order_visibility_filter(current_user))

    status_counts = {}
    status_amounts = {}
    statuses = ["NEW", "IN_PROGRESS", "DONE", "CANCELLED", "WAITING_PAYMENT", "PAID", "SHIPPED"]

    for status in statuses:
        count_q = db.query(Order).filter(Order.status == status)
        if order_filters:
            count_q = count_q.filter(*order_filters)
        status_counts[status] = count_q.count()

        amt_q = db.query(func.sum(Order.total_client_amount)).filter(Order.status == status)
        if order_filters:
            amt_q = amt_q.filter(*order_filters)
        status_amounts[status] = float(amt_q.scalar() or 0)

    return {"status_counts": status_counts, "status_amounts": status_amounts}


def get_client_finance_stats(db: Session, current_user: User, client_id: int) -> Dict:
    """Агрегаты по клиенту с учётом видимости заказов."""
    can_view_all_orders = user_has_permission(current_user, db, "orders.view_all")
    order_q = db.query(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_client_amount), 0),
        func.coalesce(func.sum(Order.total_margin_for_owner), 0),
    ).filter(Order.client_id == client_id)

    if not can_view_all_orders:
        order_q = order_q.filter(_order_visibility_filter(current_user))

    count_orders, sum_client, sum_margin = order_q.first()
    avg_check = (sum_client / count_orders) if count_orders else 0

    return {
        "count_orders": count_orders or 0,
        "turnover": float(sum_client or 0),
        "margin": float(sum_margin or 0),
        "avg_check": float(avg_check or 0),
    }


def get_partner_finance_stats(db: Session, current_user: User, partner_id: int) -> Dict:
    """Агрегаты по партнёру (по его заказам)."""
    can_view_all_orders = user_has_permission(current_user, db, "orders.view_all")
    order_q = db.query(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_client_amount), 0),
        func.coalesce(func.sum(Order.total_cost_for_owner), 0),
        func.coalesce(func.sum(Order.total_margin_for_owner), 0),
    ).filter(Order.partner_id == partner_id)

    if not can_view_all_orders:
        order_q = order_q.filter(_order_visibility_filter(current_user))

    count_orders, sum_client, sum_cost, sum_margin = order_q.first()

    return {
        "count_orders": count_orders or 0,
        "turnover": float(sum_client or 0),
        "cost": float(sum_cost or 0),
        "margin": float(sum_margin or 0),
    }
