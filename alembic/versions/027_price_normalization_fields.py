"""Add price normalization fields and brand tables

Revision ID: 027_price_normalization_fields
Revises: simple_margin_percent
Create Date: 2025-01-XX XX:XX:XX.XXXXXX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = '027_price_normalization_fields'
down_revision = 'simple_margin_percent'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # Проверяем существующие колонки в price_products
    pp_cols = {c["name"] for c in inspector.get_columns("price_products")}
    
    # Добавляем поля нормализации в price_products
    if "norm_brand" not in pp_cols:
        op.add_column("price_products", sa.Column("norm_brand", sa.String(), nullable=True))
    if "brand_confidence" not in pp_cols:
        op.add_column("price_products", sa.Column("brand_confidence", sa.Numeric(3, 2), nullable=True))
    if "model_name" not in pp_cols:
        op.add_column("price_products", sa.Column("model_name", sa.String(), nullable=True))
    if "series" not in pp_cols:
        op.add_column("price_products", sa.Column("series", sa.String(), nullable=True))
    if "category_path_json" not in pp_cols:
        # Для SQLite используем TEXT, для других БД - JSON
        if bind.dialect.name == "sqlite":
            op.add_column("price_products", sa.Column("category_path_json", sa.Text(), nullable=True))
        else:
            op.add_column("price_products", sa.Column("category_path_json", sa.JSON(), nullable=True))
    if "attrs_json" not in pp_cols:
        if bind.dialect.name == "sqlite":
            op.add_column("price_products", sa.Column("attrs_json", sa.Text(), nullable=True))
        else:
            op.add_column("price_products", sa.Column("attrs_json", sa.JSON(), nullable=True))
    if "variant_key" not in pp_cols:
        op.add_column("price_products", sa.Column("variant_key", sa.String(), nullable=True))
    if "search_text" not in pp_cols:
        op.add_column("price_products", sa.Column("search_text", sa.Text(), nullable=True))
    if "normalization_notes" not in pp_cols:
        op.add_column("price_products", sa.Column("normalization_notes", sa.Text(), nullable=True))
    
    # Обновляем ai_status: pending -> ok/review/error
    # (поле уже существует, просто обновляем значения по умолчанию)
    
    # Создаём индексы
    if "ix_price_products_group_key" not in [idx["name"] for idx in inspector.get_indexes("price_products")]:
        op.create_index("ix_price_products_group_key", "price_products", ["ai_group_key"], unique=False)
    if "ix_price_products_variant_key" not in [idx["name"] for idx in inspector.get_indexes("price_products")]:
        op.create_index("ix_price_products_variant_key", "price_products", ["variant_key"], unique=False)
    if "ix_price_products_norm_brand" not in [idx["name"] for idx in inspector.get_indexes("price_products")]:
        op.create_index("ix_price_products_norm_brand", "price_products", ["norm_brand"], unique=False)
    
    # Создаём таблицу brands
    if "brands" not in inspector.get_table_names():
        op.create_table(
            "brands",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name_canonical", sa.String(), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name_canonical", name="uq_brands_name_canonical"),
        )
        op.create_index("ix_brands_name_canonical", "brands", ["name_canonical"], unique=True)
    
    # Создаём таблицу brand_aliases
    if "brand_aliases" not in inspector.get_table_names():
        op.create_table(
            "brand_aliases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("brand_id", sa.Integer(), nullable=False),
            sa.Column("alias_upper", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("alias_upper", name="uq_brand_aliases_alias_upper"),
        )
        op.create_index("ix_brand_aliases_brand_id", "brand_aliases", ["brand_id"], unique=False)
        op.create_index("ix_brand_aliases_alias_upper", "brand_aliases", ["alias_upper"], unique=True)
        
        # Foreign key для brand_aliases
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_brand_aliases_brand_id",
                "brand_aliases",
                "brands",
                ["brand_id"],
                ["id"],
                ondelete="CASCADE",
            )
    
    # Обновляем CatalogItem: добавляем group_key если его нет
    ci_cols = {c["name"] for c in inspector.get_columns("catalog_items")}
    if "group_key" not in ci_cols:
        if bind.dialect.name == "sqlite":
            # SQLite не поддерживает unique=True при добавлении колонки, добавляем отдельно
            with op.batch_alter_table("catalog_items", schema=None) as batch_op:
                batch_op.add_column(sa.Column("group_key", sa.String(), nullable=True))
            op.create_index("ix_catalog_items_group_key", "catalog_items", ["group_key"], unique=True)
        else:
            op.add_column("catalog_items", sa.Column("group_key", sa.String(), nullable=True, unique=True))
            op.create_index("ix_catalog_items_group_key", "catalog_items", ["group_key"], unique=True)
    
    # Обновляем CatalogVariant: добавляем variant_key и новые поля
    cv_cols = {c["name"] for c in inspector.get_columns("catalog_variants")}
    if "variant_key" not in cv_cols:
        if bind.dialect.name == "sqlite":
            # SQLite не поддерживает unique=True при добавлении колонки, добавляем отдельно
            with op.batch_alter_table("catalog_variants", schema=None) as batch_op:
                batch_op.add_column(sa.Column("variant_key", sa.String(), nullable=True))
            op.create_index("ix_catalog_variants_variant_key", "catalog_variants", ["variant_key"], unique=True)
        else:
            op.add_column("catalog_variants", sa.Column("variant_key", sa.String(), nullable=True, unique=True))
            op.create_index("ix_catalog_variants_variant_key", "catalog_variants", ["variant_key"], unique=True)
    if "format" not in cv_cols:
        op.add_column("catalog_variants", sa.Column("format", sa.String(), nullable=True))  # full/tester/decant/sample/mini
    if "color" not in cv_cols:
        op.add_column("catalog_variants", sa.Column("color", sa.String(), nullable=True))
    if "size_cm" not in cv_cols:
        if bind.dialect.name == "sqlite":
            op.add_column("catalog_variants", sa.Column("size_cm", sa.Text(), nullable=True))  # JSON: {w:int, h:int}
        else:
            op.add_column("catalog_variants", sa.Column("size_cm", sa.JSON(), nullable=True))
    if "pack" not in cv_cols:
        if bind.dialect.name == "sqlite":
            op.add_column("catalog_variants", sa.Column("pack", sa.Text(), nullable=True))  # JSON: {qty:int, unit:string}
        else:
            op.add_column("catalog_variants", sa.Column("pack", sa.JSON(), nullable=True))
    if "density_raw" not in cv_cols:
        op.add_column("catalog_variants", sa.Column("density_raw", sa.String(), nullable=True))
    if "features" not in cv_cols:
        if bind.dialect.name == "sqlite":
            op.add_column("catalog_variants", sa.Column("features", sa.Text(), nullable=True))  # JSON: list<string>
        else:
            op.add_column("catalog_variants", sa.Column("features", sa.JSON(), nullable=True))
    if "volumes_ml" not in cv_cols:
        if bind.dialect.name == "sqlite":
            op.add_column("catalog_variants", sa.Column("volumes_ml", sa.Text(), nullable=True))  # JSON: list<int>
        else:
            op.add_column("catalog_variants", sa.Column("volumes_ml", sa.JSON(), nullable=True))
    if "total_ml" not in cv_cols:
        op.add_column("catalog_variants", sa.Column("total_ml", sa.Integer(), nullable=True))


def downgrade():
    # Удаляем индексы
    op.drop_index("ix_price_products_norm_brand", table_name="price_products")
    op.drop_index("ix_price_products_variant_key", table_name="price_products")
    
    # Удаляем колонки из catalog_variants
    op.drop_column("catalog_variants", "total_ml")
    op.drop_column("catalog_variants", "volumes_ml")
    op.drop_column("catalog_variants", "features")
    op.drop_column("catalog_variants", "density_raw")
    op.drop_column("catalog_variants", "pack")
    op.drop_column("catalog_variants", "size_cm")
    op.drop_column("catalog_variants", "color")
    op.drop_column("catalog_variants", "format")
    op.drop_index("ix_catalog_variants_variant_key", table_name="catalog_variants")
    op.drop_column("catalog_variants", "variant_key")
    
    # Удаляем колонки из catalog_items
    op.drop_index("ix_catalog_items_group_key", table_name="catalog_items")
    op.drop_column("catalog_items", "group_key")
    
    # Удаляем таблицы
    op.drop_table("brand_aliases")
    op.drop_table("brands")
    
    # Удаляем колонки из price_products
    op.drop_column("price_products", "normalization_notes")
    op.drop_column("price_products", "search_text")
    op.drop_column("price_products", "variant_key")
    op.drop_column("price_products", "attrs_json")
    op.drop_column("price_products", "category_path_json")
    op.drop_column("price_products", "series")
    op.drop_column("price_products", "model_name")
    op.drop_column("price_products", "brand_confidence")
    op.drop_column("price_products", "norm_brand")

