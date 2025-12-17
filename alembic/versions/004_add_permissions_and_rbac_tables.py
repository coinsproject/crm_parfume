"""Add permissions and role_permissions tables, seed base permissions

Revision ID: 004_add_permissions_and_rbac_tables
Revises: 003_add_full_name_and_make_email_nullable
Create Date: 2025-12-01 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select


# revision identifiers
revision = '004_add_permissions_and_rbac_tables'
down_revision = '003_add_full_name_and_make_email_nullable'
branch_labels = None
depends_on = None


PERMISSIONS = [
    ("dashboard.view", "Просмотр дашборда"),
    ("clients.view_all", "Клиенты: просмотр всех"),
    ("clients.view_own", "Клиенты: просмотр своих"),
    ("clients.create", "Клиенты: создание"),
    ("orders.view_all", "Заказы: просмотр всех"),
    ("orders.view_own", "Заказы: просмотр своих"),
    ("orders.create", "Заказы: создание"),
    ("partners.view_all", "Партнёры: просмотр всех"),
    ("partners.view_own", "Партнёры: просмотр своих"),
    ("catalog.view_full", "Каталог: полный режим"),
    ("catalog.view_client", "Каталог: клиентский режим"),
    ("catalog.manage", "Каталог: управление данными"),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("key", sa.String(), nullable=False, unique=True),
            sa.Column("label", sa.String(), nullable=False),
        )
    if not inspector.has_table("role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
            sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id"), nullable=False),
            sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        )

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
        column("description", sa.String),
        column("is_system", sa.Boolean),
    )
    role_permissions_table = table(
        "role_permissions",
        column("id", sa.Integer),
        column("role_id", sa.Integer),
        column("permission_id", sa.Integer),
    )

    # вставляем недостающие разрешения
    existing_keys = {row.key for row in bind.execute(select(permission_table.c.key)).fetchall()} if inspector.has_table("permissions") else set()
    for key, label in PERMISSIONS:
        if key not in existing_keys:
            bind.execute(permission_table.insert().values(key=key, label=label))

    admin_role = bind.execute(select(role_table.c.id).where(role_table.c.name == "ADMIN")).fetchone()

    if admin_role is None:
        bind.execute(
            role_table.insert().values(
                name="ADMIN",
                description="Системная роль администратора",
                is_system=True,
            )
        )
        # SQLite может не вернуть inserted_primary_key, поэтому читаем повторно
        admin_role = bind.execute(select(role_table.c.id).where(role_table.c.name == "ADMIN")).fetchone()

    admin_role_id = admin_role.id if admin_role is not None else None
    if admin_role_id is None:
        raise RuntimeError("Не удалось создать или получить роль ADMIN")

    # Grant all permissions to ADMIN (без дубликатов)
    permission_rows = bind.execute(select(permission_table.c.id)).fetchall()
    existing_rps = {
        (row.role_id, row.permission_id)
        for row in bind.execute(select(role_permissions_table.c.role_id, role_permissions_table.c.permission_id)).fetchall()
    } if inspector.has_table("role_permissions") else set()
    for perm_row in permission_rows:
        if (admin_role_id, perm_row.id) not in existing_rps:
            bind.execute(
                role_permissions_table.insert().values(
                    role_id=admin_role_id,
                    permission_id=perm_row.id,
                )
            )


def downgrade():
    op.drop_table("role_permissions")
    op.drop_table("permissions")
