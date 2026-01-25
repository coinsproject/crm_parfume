"""add_catalog_enrichment_fields

Revision ID: 669e791786f9
Revises: 08054e09e2b8
Create Date: 2026-01-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '669e791786f9'
down_revision: Union[str, Sequence[str], None] = '08054e09e2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('catalog_items', sa.Column('external_source', sa.String(), nullable=True))
    op.add_column('catalog_items', sa.Column('external_key', sa.String(), nullable=True))
    op.add_column('catalog_items', sa.Column('enrich_status', sa.String(), nullable=True, server_default='pending'))
    op.add_column('catalog_items', sa.Column('enrich_confidence', sa.Numeric(precision=3, scale=2), nullable=True))
    op.add_column('catalog_items', sa.Column('enriched_json', sa.Text(), nullable=True))
    op.create_index(op.f('ix_catalog_items_external_key'), 'catalog_items', ['external_key'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_catalog_items_external_key'), table_name='catalog_items')
    op.drop_column('catalog_items', 'enriched_json')
    op.drop_column('catalog_items', 'enrich_confidence')
    op.drop_column('catalog_items', 'enrich_status')
    op.drop_column('catalog_items', 'external_key')
    op.drop_column('catalog_items', 'external_source')
