"""partners roles refactor base fields

Revision ID: 024_partners_roles_refactor
Revises: 023_price_import_stage1
Create Date: 2025-12-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select
from datetime import datetime

# revision identifiers, used by Alembic.
revision = "024_partners_roles_refactor"
down_revision = "023_price_import_stage1"
branch_labels = None
depends_on = None


def _col_exists(inspector, table_name, col_name):
    return col_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"

    # users.role_name (строковое название роли для простого маппинга admin/partner)
    if _col_exists(insp, "users", "role_name") is False:
        op.add_column("users", sa.Column("role_name", sa.String(), nullable=True))

    # partners расширенные поля
    if _col_exists(insp, "partners", "user_id") is False:
        # в SQLite добавляем без FK, чтобы избежать ограничений ALTER TABLE
        op.add_column("partners", sa.Column("user_id", sa.Integer(), nullable=True))
    if _col_exists(insp, "partners", "full_name") is False:
        op.add_column("partners", sa.Column("full_name", sa.String(), nullable=True))
    if _col_exists(insp, "partners", "telegram_nick") is False:
        op.add_column("partners", sa.Column("telegram_nick", sa.String(), nullable=True))
    if _col_exists(insp, "partners", "partner_share_percent") is False:
        op.add_column("partners", sa.Column("partner_share_percent", sa.Numeric(5, 2), nullable=True))
    if _col_exists(insp, "partners", "admin_share_percent") is False:
        op.add_column("partners", sa.Column("admin_share_percent", sa.Numeric(5, 2), nullable=True))
    if _col_exists(insp, "partners", "can_edit_prices") is False:
        op.add_column("partners", sa.Column("can_edit_prices", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    if _col_exists(insp, "partners", "status") is False:
        op.add_column("partners", sa.Column("status", sa.String(), nullable=False, server_default="active"))
    if _col_exists(insp, "partners", "comment") is False:
        op.add_column("partners", sa.Column("comment", sa.Text(), nullable=True))
    if _col_exists(insp, "partners", "created_at") is False:
        col = sa.Column("created_at", sa.DateTime(), nullable=True, server_default=None if is_sqlite else sa.text("CURRENT_TIMESTAMP"))
        op.add_column("partners", col)
    if _col_exists(insp, "partners", "updated_at") is False:
        col = sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=None if is_sqlite else sa.text("CURRENT_TIMESTAMP"))
        op.add_column("partners", col)

    # clients новые связи
    if _col_exists(insp, "clients", "partner_id") is False:
        op.add_column("clients", sa.Column("partner_id", sa.Integer(), nullable=True))
    if _col_exists(insp, "clients", "created_by_user_id") is False:
        op.add_column("clients", sa.Column("created_by_user_id", sa.Integer(), nullable=True))

    # заполнить базовые значения для admin_share_percent если partner_share_percent задан
    partners_table = table(
        "partners",
        column("id", sa.Integer),
        column("full_name", sa.String),
        column("name", sa.String),
        column("first_name", sa.String),
        column("last_name", sa.String),
        column("partner_share_percent", sa.Numeric),
        column("admin_share_percent", sa.Numeric),
    )

    if insp.has_table("partners"):
        rows = list(bind.execute(select(partners_table.c.id, partners_table.c.full_name, partners_table.c.name, partners_table.c.first_name, partners_table.c.last_name, partners_table.c.partner_share_percent, partners_table.c.admin_share_percent)))
        for row in rows:
            full_name_val = row.full_name
            if not full_name_val:
                parts = [row.last_name or "", row.first_name or ""]
                joined = " ".join(p for p in parts if p).strip()
                full_name_val = joined or row.name
            admin_share = row.admin_share_percent
            partner_share = row.partner_share_percent
            if partner_share is not None and admin_share is None:
                admin_share = 100 - float(partner_share)
            upd_values = {}
            if full_name_val:
                upd_values["full_name"] = full_name_val
            if admin_share is not None:
                upd_values["admin_share_percent"] = admin_share
            if upd_values:
                bind.execute(
                    partners_table.update().where(partners_table.c.id == row.id).values(**upd_values)
                )


def downgrade():
    op.drop_column("clients", "created_by_user_id")
    op.drop_column("clients", "partner_id")
    op.drop_column("partners", "updated_at")
    op.drop_column("partners", "created_at")
    op.drop_column("partners", "comment")
    op.drop_column("partners", "status")
    op.drop_column("partners", "can_edit_prices")
    op.drop_column("partners", "admin_share_percent")
    op.drop_column("partners", "partner_share_percent")
    op.drop_column("partners", "telegram_nick")
    op.drop_column("partners", "full_name")
    op.drop_column("partners", "user_id")
    op.drop_column("users", "role_name")
