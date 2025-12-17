"""Add price permissions

Revision ID: 008_add_price_permissions
Revises: 007_add_price_and_margin_fields
Create Date: 2025-12-02 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# revision identifiers, used by Alembic.
revision = '008_add_price_permissions'
down_revision = '007_add_price_and_margin_fields'
branch_labels = None
depends_on = None


PERMISSIONS = [
    ("prices.view_client", "Просмотр цен для клиента"),
    ("prices.view_cost", "Просмотр себестоимости/закупа"),
    ("prices.view_margin", "Просмотр маржи"),
    ("prices.edit", "Редактирование цен"),
]


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
    for key, label in PERMISSIONS:
        if key not in existing_keys:
            conn.execute(permission_table.insert().values(key=key, label=label))

    admin_role = conn.execute(
        select(role_table.c.id).where(role_table.c.name == "ADMIN")
    ).fetchone()
    partner_role = conn.execute(
        select(role_table.c.id).where(role_table.c.name == "PARTNER")
    ).fetchone()

    def grant(role_row, keys):
        if not role_row:
            return
        role_id = role_row.id
        for key in keys:
            perm = conn.execute(
                select(permission_table.c.id).where(permission_table.c.key == key)
            ).fetchone()
            if not perm:
                continue
            exists = conn.execute(
                select(role_permissions_table.c.id).where(
                    role_permissions_table.c.role_id == role_id,
                    role_permissions_table.c.permission_id == perm.id,
                )
            ).fetchone()
            if not exists:
                conn.execute(
                    role_permissions_table.insert().values(
                        role_id=role_id, permission_id=perm.id
                    )
                )

    admin_keys = [key for key, _ in PERMISSIONS]
    grant(admin_role, admin_keys)
    if partner_role:
        grant(partner_role, ["prices.view_client", "prices.view_margin", "prices.view_cost"])


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
        select(permission_table.c.id, permission_table.c.key).where(
            permission_table.c.key.in_([key for key, _ in PERMISSIONS])
        )
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
