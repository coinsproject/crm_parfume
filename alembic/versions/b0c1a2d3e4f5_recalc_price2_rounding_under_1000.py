"""Recalc price_2 rounding for items under 1000.

Revision ID: b0c1a2d3e4f5
Revises: a6114f01cf64
Create Date: 2025-12-15
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b0c1a2d3e4f5"
down_revision = "a6114f01cf64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # price_products: recompute price_2 and round_delta from price_1
    op.execute(
        """
        WITH calc AS (
            SELECT
                id,
                price_1 AS p1,
                CASE WHEN price_1 < 1000 THEN 5000 ELSE 50000 END AS step_cents,
                CAST(ROUND(price_1 * 100) AS INTEGER) AS p1_cents
            FROM price_products
            WHERE price_1 IS NOT NULL
        )
        UPDATE price_products
        SET
            price_2 = (
                SELECT (CAST((c.p1_cents + c.step_cents - 1) / c.step_cents AS INTEGER) * c.step_cents) / 100.0
                FROM calc c
                WHERE c.id = price_products.id
            ),
            round_delta = (
                SELECT ((CAST((c.p1_cents + c.step_cents - 1) / c.step_cents AS INTEGER) * c.step_cents) / 100.0) - c.p1
                FROM calc c
                WHERE c.id = price_products.id
            )
        WHERE id IN (SELECT id FROM calc);
        """
    )

    # price_history: recompute new_price_2, new_round_delta and compatibility "price" from new_price_1
    op.execute(
        """
        WITH calc AS (
            SELECT
                id,
                new_price_1 AS p1,
                CASE WHEN new_price_1 < 1000 THEN 5000 ELSE 50000 END AS step_cents,
                CAST(ROUND(new_price_1 * 100) AS INTEGER) AS p1_cents
            FROM price_history
            WHERE new_price_1 IS NOT NULL
        )
        UPDATE price_history
        SET
            new_price_2 = (
                SELECT (CAST((c.p1_cents + c.step_cents - 1) / c.step_cents AS INTEGER) * c.step_cents) / 100.0
                FROM calc c
                WHERE c.id = price_history.id
            ),
            new_round_delta = (
                SELECT ((CAST((c.p1_cents + c.step_cents - 1) / c.step_cents AS INTEGER) * c.step_cents) / 100.0) - c.p1
                FROM calc c
                WHERE c.id = price_history.id
            ),
            price = (
                SELECT (CAST((c.p1_cents + c.step_cents - 1) / c.step_cents AS INTEGER) * c.step_cents) / 100.0
                FROM calc c
                WHERE c.id = price_history.id
            )
        WHERE id IN (SELECT id FROM calc);
        """
    )


def downgrade() -> None:
    # Data migration; no safe automatic downgrade.
    pass

