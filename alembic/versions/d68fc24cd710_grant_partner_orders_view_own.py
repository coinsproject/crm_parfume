"""grant_partner_orders_view_own

Revision ID: d68fc24cd710
Revises: ef9cc58f409e
Create Date: 2026-01-19 01:45:00.299302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select


# revision identifiers, used by Alembic.
revision: str = 'd68fc24cd710'
down_revision: Union[str, Sequence[str], None] = 'ef9cc58f409e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    
    permission_table = table(
        "permissions",
        column("id", sa.Integer),
        column("key", sa.String),
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
    
    # Получаем роль PARTNER
    partner_role = conn.execute(
        select(role_table.c.id).where(role_table.c.name == "PARTNER")
    ).fetchone()
    
    if not partner_role:
        return  # Роль не найдена, пропускаем
    
    partner_role_id = partner_role.id
    
    # Права, которые нужны партнёру для работы с запросами на закупку
    needed_permissions = ["orders.view_own", "orders.create"]
    
    def grant(permission_key):
        # Получаем permission
        perm = conn.execute(
            select(permission_table.c.id).where(permission_table.c.key == permission_key)
        ).fetchone()
        
        if not perm:
            return  # Право не найдено
        
        perm_id = perm.id
        
        # Проверяем, есть ли уже это право у роли
        exists = conn.execute(
            select(role_permissions_table.c.id).where(
                role_permissions_table.c.role_id == partner_role_id,
                role_permissions_table.c.permission_id == perm_id,
            )
        ).fetchone()
        
        if not exists:
            # Добавляем право
            conn.execute(
                role_permissions_table.insert().values(
                    role_id=partner_role_id,
                    permission_id=perm_id,
                )
            )
    
    for perm_key in needed_permissions:
        grant(perm_key)


def downgrade() -> None:
    """Downgrade schema."""
    # Не удаляем права при откате, так как они могут быть нужны
    pass
