"""Add price.search permission

Revision ID: 011_add_price_search_permission
Revises: 010_add_price_uploads_and_permission
Create Date: 2025-12-02 02:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# revision identifiers, used by Alembic.
revision = '011_add_price_search_permission'
down_revision = '010_add_price_uploads_and_permission'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    permission_table = table(
        "permissions",
        column("id", sa.Integer),
        column("key", sa.String),
        column("label", sa.String),
    )
    role_table = table(
        "roles",
        column("id", sa.Integer),
        column("name", sa.String),
    )
    role_permissions_table = table(
        "role_permissions",
        column("id", sa.Integer),
        column("role_id", sa.Integer),
        column("permission_id", sa.Integer),
    )

    existing_keys = {row.key for row in conn.execute(select(permission_table.c.key))}
    if "price.search" not in existing_keys:
        conn.execute(permission_table.insert().values(key="price.search", label="Поиск по прайсу"))

    admin_role = conn.execute(select(role_table.c.id).where(role_table.c.name == "ADMIN")).fetchone()
    manager_role = conn.execute(select(role_table.c.id).where(role_table.c.name == "MANAGER")).fetchone()

    def grant(role_row):
        if not role_row:
            return
        perm = conn.execute(
            select(permission_table.c.id).where(permission_table.c.key == "price.search")
        ).fetchone()
        if not perm:
            return
        exists = conn.execute(
            select(role_permissions_table.c.id).where(
                role_permissions_table.c.role_id == role_row.id,
                role_permissions_table.c.permission_id == perm.id,
            )
        ).fetchone()
        if not exists:
            conn.execute(
                role_permissions_table.insert().values(role_id=role_row.id, permission_id=perm.id)
            )

    grant(admin_role)
    grant(manager_role)


def downgrade():
    conn = op.get_bind()
    permission_table = table(
        "permissions",
        column("id", sa.Integer),
        column("key", sa.String),
        column("label", sa.String),
    )
    role_permissions_table = table(
        "role_permissions",
        column("id", sa.Integer),
        column("role_id", sa.Integer),
        column("permission_id", sa.Integer),
    )

    perm_rows = conn.execute(
        select(permission_table.c.id).where(permission_table.c.key == "price.search")
    ).fetchall()
    perm_ids = [row.id for row in perm_rows]
    if perm_ids:
        conn.execute(
            role_permissions_table.delete().where(
                role_permissions_table.c.permission_id.in_(perm_ids)
            )
        )
        conn.execute(
            permission_table.delete().where(permission_table.c.id.in_(perm_ids))
        )
