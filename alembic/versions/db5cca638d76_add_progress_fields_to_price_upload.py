"""add_progress_fields_to_price_upload

Revision ID: db5cca638d76
Revises: 1c82b7a3fc72
Create Date: 2026-01-05 03:04:36.548823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db5cca638d76'
down_revision: Union[str, Sequence[str], None] = '1c82b7a3fc72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('price_uploads', sa.Column('processed_rows', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('price_uploads', sa.Column('progress_percent', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0.0'))
    op.add_column('price_uploads', sa.Column('cancelled', sa.Boolean(), nullable=True, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('price_uploads', 'cancelled')
    op.drop_column('price_uploads', 'progress_percent')
    op.drop_column('price_uploads', 'processed_rows')
