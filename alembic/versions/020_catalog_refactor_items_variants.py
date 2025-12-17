"""refactor catalog items and add variants

Revision ID: 020_catalog_refactor_items_variants
Revises: 019_add_partner_contact_fields
Create Date: 2025-12-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "020_catalog_refactor_items_variants"
down_revision = "019_add_partner_contact_fields"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- catalog_items adjustments ---
    with op.batch_alter_table("catalog_items") as batch:
        # drop old unique constraint if exists
        for uc in insp.get_unique_constraints("catalog_items"):
            if uc.get("name") == "uq_catalog_item_price_product":
                batch.drop_constraint("uq_catalog_item_price_product", type_="unique")
        # make price_product_id nullable (legacy, теперь опционально)
        batch.alter_column("price_product_id", existing_type=sa.Integer(), nullable=True)
        # add new fields if missing
        if "display_name" not in [c["name"] for c in insp.get_columns("catalog_items")]:
            batch.add_column(sa.Column("display_name", sa.String(), nullable=True))
        if "visible" not in [c["name"] for c in insp.get_columns("catalog_items")]:
            batch.add_column(sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.text("0")))
            batch.alter_column("visible", server_default=None)
        if "in_stock" not in [c["name"] for c in insp.get_columns("catalog_items")]:
            batch.add_column(sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("0")))
            batch.alter_column("in_stock", server_default=None)

    # заполнить display_name и избежать конфликтов для уникального индекса brand+name
    # приводим brand/name к строкам, дубликаты переименовываем с добавлением id
    rows = list(bind.execute(sa.text("SELECT id, brand, name FROM catalog_items")))
    seen = set()
    for row in rows:
        brand = (row.brand or "").strip()
        name = (row.name or f"Товар {row.id}").strip()
        display_name = f"{brand} {name}".strip() if brand else name
        # резолв конфликтов
        key = (brand.lower(), name.lower())
        if key in seen:
            name = f"{name} ({row.id})"
            display_name = f"{brand} {name}".strip() if brand else name
            key = (brand.lower(), name.lower())
        seen.add(key)
        bind.execute(
            sa.text("UPDATE catalog_items SET brand=:brand, name=:name, display_name=:display WHERE id=:id"),
            {"brand": brand or None, "name": name, "display": display_name, "id": row.id},
        )

    # новый уникальный индекс по brand+name
    existing_indexes = {ix["name"] for ix in insp.get_indexes("catalog_items")}
    if "uq_catalog_item_brand_name" not in existing_indexes:
        with op.batch_alter_table("catalog_items") as batch:
            batch.create_unique_constraint("uq_catalog_item_brand_name", ["brand", "name"])

    # --- новая таблица catalog_variants ---
    if "catalog_variants" not in insp.get_table_names():
        op.create_table(
            "catalog_variants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("price_product_id", sa.Integer(), sa.ForeignKey("price_products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("volume_value", sa.Numeric(10, 2), nullable=True),
            sa.Column("volume_unit", sa.String(), nullable=True),
            sa.Column("is_tester", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("gender", sa.String(), nullable=True),
            sa.Column("kind", sa.String(), nullable=True),
            sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("request_payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("price_product_id", name="uq_catalog_variant_price_product"),
        )


def downgrade():
    op.drop_table("catalog_variants")
    with op.batch_alter_table("catalog_items") as batch:
        batch.drop_constraint("uq_catalog_item_brand_name", type_="unique")
        # оставляем новые колонки (display_name/visible/in_stock) ради совместимости, не удаляем
        batch.alter_column("price_product_id", nullable=False)
