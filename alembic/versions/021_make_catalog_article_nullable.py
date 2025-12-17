"""make catalog_items.article nullable

Revision ID: 021_make_catalog_article_nullable
Revises: 020_catalog_refactor_items_variants
Create Date: 2025-12-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "021_make_catalog_article_nullable"
down_revision = "020_catalog_refactor_items_variants"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("catalog_items") as batch:
        batch.alter_column("article", existing_type=sa.String(), nullable=True)


def downgrade():
    with op.batch_alter_table("catalog_items") as batch:
        batch.alter_column("article", existing_type=sa.String(), nullable=False)
