"""Round delta fields to 2 decimals.

Revision ID: c2d3e4f5a6b7
Revises: b0c1a2d3e4f5
Create Date: 2025-12-15
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b0c1a2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE price_products SET round_delta = ROUND(round_delta, 2) WHERE round_delta IS NOT NULL;")
    op.execute("UPDATE price_history SET new_round_delta = ROUND(new_round_delta, 2) WHERE new_round_delta IS NOT NULL;")


def downgrade() -> None:
    pass

