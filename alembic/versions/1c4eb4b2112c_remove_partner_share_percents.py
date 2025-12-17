"""remove partner share percents

Revision ID: 1c4eb4b2112c
Revises: e49a30f6b35a
Create Date: 2025-12-14 02:42:05.355132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c4eb4b2112c'
down_revision: Union[str, Sequence[str], None] = 'e49a30f6b35a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("partners") as batch_op:
        batch_op.drop_column("admin_share_percent")
        batch_op.drop_column("partner_share_percent")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("partners") as batch_op:
        batch_op.add_column(sa.Column("partner_share_percent", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("admin_share_percent", sa.Numeric(5, 2), nullable=True))
