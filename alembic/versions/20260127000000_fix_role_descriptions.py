"""fix role descriptions to Russian

Revision ID: 20260127000000
Revises: 20260126015515
Create Date: 2026-01-27 00:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# revision identifiers, used by Alembic.
revision: str = '20260127000000'
down_revision: Union[str, Sequence[str], None] = '20260126015515'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    
    roles_table = table(
        "roles",
        column("id", sa.Integer),
        column("name", sa.String),
        column("description", sa.String),
        column("is_system", sa.Boolean),
    )
    
    # Обновляем описания ролей на русский язык
    role_updates = {
        "ADMIN": {
            "description": "Системная роль администратора",
            "is_system": True
        },
        "MANAGER": {
            "description": "Менеджер",
            "is_system": False
        },
        "PARTNER": {
            "description": "Партнёр",
            "is_system": False
        },
        "VIEWER": {
            "description": "Просмотр",
            "is_system": False
        },
    }
    
    for role_name, updates in role_updates.items():
        role = conn.execute(
            select(roles_table.c.id).where(roles_table.c.name == role_name)
        ).fetchone()
        
        if role:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.id == role.id)
                .values(
                    description=updates["description"],
                    is_system=updates["is_system"]
                )
            )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    
    roles_table = table(
        "roles",
        column("id", sa.Integer),
        column("name", sa.String),
        column("description", sa.String),
        column("is_system", sa.Boolean),
    )
    
    # Возвращаем английские описания
    role_updates = {
        "ADMIN": {
            "description": "System administrator",
            "is_system": True
        },
        "MANAGER": {
            "description": "Manager role",
            "is_system": True
        },
        "PARTNER": {
            "description": "Partner role",
            "is_system": True
        },
        "VIEWER": {
            "description": "Viewer role",
            "is_system": True
        },
    }
    
    for role_name, updates in role_updates.items():
        role = conn.execute(
            select(roles_table.c.id).where(roles_table.c.name == role_name)
        ).fetchone()
        
        if role:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.id == role.id)
                .values(
                    description=updates["description"],
                    is_system=updates["is_system"]
                )
            )

