"""add partner fields to invitation

Revision ID: 20260127010000
Revises: 20260127000000
Create Date: 2026-01-27 01:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260127010000'
down_revision: Union[str, Sequence[str], None] = '20260127000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем поля для хранения данных партнера в приглашении
    with op.batch_alter_table("invitations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("partner_full_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("partner_phone", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("partner_telegram", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("invitations", schema=None) as batch_op:
        batch_op.drop_column("partner_telegram")
        batch_op.drop_column("partner_phone")
        batch_op.drop_column("partner_full_name")

