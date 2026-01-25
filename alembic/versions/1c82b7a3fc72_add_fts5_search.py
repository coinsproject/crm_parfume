"""add_fts5_search

Revision ID: 1c82b7a3fc72
Revises: 027_price_normalization_fields
Create Date: 2026-01-04 04:09:51.887741

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c82b7a3fc72'
down_revision: Union[str, Sequence[str], None] = '027_price_normalization_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаём виртуальную таблицу FTS5 для полнотекстового поиска
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS price_products_fts5 USING fts5(
            id UNINDEXED,
            raw_name,
            norm_brand,
            model_name,
            series,
            search_text,
            external_article,
            content='price_products',
            content_rowid='id'
        );
    """)
    
    # Создаём триггеры для автоматического обновления FTS5
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS price_products_fts5_insert AFTER INSERT ON price_products BEGIN
            INSERT INTO price_products_fts5(rowid, raw_name, norm_brand, model_name, series, search_text, external_article)
            VALUES (new.id, new.raw_name, new.norm_brand, new.model_name, new.series, new.search_text, new.external_article);
        END;
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS price_products_fts5_delete AFTER DELETE ON price_products BEGIN
            DELETE FROM price_products_fts5 WHERE rowid = old.id;
        END;
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS price_products_fts5_update AFTER UPDATE ON price_products BEGIN
            DELETE FROM price_products_fts5 WHERE rowid = old.id;
            INSERT INTO price_products_fts5(rowid, raw_name, norm_brand, model_name, series, search_text, external_article)
            VALUES (new.id, new.raw_name, new.norm_brand, new.model_name, new.series, new.search_text, new.external_article);
        END;
    """)
    
    # Заполняем FTS5 существующими данными
    op.execute("""
        INSERT INTO price_products_fts5(rowid, raw_name, norm_brand, model_name, series, search_text, external_article)
        SELECT id, raw_name, norm_brand, model_name, series, search_text, external_article
        FROM price_products
        WHERE is_active = 1;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS price_products_fts5_update;")
    op.execute("DROP TRIGGER IF EXISTS price_products_fts5_delete;")
    op.execute("DROP TRIGGER IF EXISTS price_products_fts5_insert;")
    op.execute("DROP TABLE IF EXISTS price_products_fts5;")
