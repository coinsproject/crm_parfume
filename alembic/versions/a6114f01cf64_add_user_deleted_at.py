"""add user deleted_at

Revision ID: a6114f01cf64
Revises: 1c4eb4b2112c
Create Date: 2025-12-14 22:49:35.639674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6114f01cf64'
down_revision: Union[str, Sequence[str], None] = '1c4eb4b2112c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("deleted_at")
