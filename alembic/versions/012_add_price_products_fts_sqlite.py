"""Add FTS table for price_products (SQLite)

Revision ID: 012_add_price_products_fts_sqlite
Revises: 011_add_price_search_permission
Create Date: 2025-12-02 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_add_price_products_fts_sqlite'
down_revision = '011_add_price_search_permission'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return

    conn.execute(sa.text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS price_products_fts USING fts5(
            brand,
            product_name,
            raw_name,
            external_article,
            content='price_products',
            content_rowid='id'
        );
    """))

    # Первичное наполнение
    conn.execute(sa.text("""
        INSERT INTO price_products_fts(rowid, brand, product_name, raw_name, external_article)
        SELECT id, coalesce(brand,''), coalesce(product_name,''), coalesce(raw_name,''), coalesce(external_article,'')
        FROM price_products;
    """))

    # Триггеры синхронизации
    conn.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS price_products_ai AFTER INSERT ON price_products BEGIN
            INSERT INTO price_products_fts(rowid, brand, product_name, raw_name, external_article)
            VALUES (new.id, coalesce(new.brand,''), coalesce(new.product_name,''), coalesce(new.raw_name,''), coalesce(new.external_article,''));
        END;
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS price_products_ad AFTER DELETE ON price_products BEGIN
            INSERT INTO price_products_fts(price_products_fts, rowid, brand, product_name, raw_name, external_article)
            VALUES('delete', old.id, old.brand, old.product_name, old.raw_name, old.external_article);
        END;
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS price_products_au AFTER UPDATE ON price_products BEGIN
            INSERT INTO price_products_fts(price_products_fts, rowid, brand, product_name, raw_name, external_article)
            VALUES('delete', old.id, old.brand, old.product_name, old.raw_name, old.external_article);
            INSERT INTO price_products_fts(rowid, brand, product_name, raw_name, external_article)
            VALUES (new.id, coalesce(new.brand,''), coalesce(new.product_name,''), coalesce(new.raw_name,''), coalesce(new.external_article,''));
        END;
    """))


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    conn.execute(sa.text("DROP TABLE IF EXISTS price_products_fts"))
