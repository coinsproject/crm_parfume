"""add partner price markup percent

Revision ID: f3c9b1a2d4e5
Revises: e49a30f6b35a
Create Date: 2026-01-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c9b1a2d4e5"
down_revision: Union[str, Sequence[str], None] = "3f4b2ada01c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("partners") as batch_op:
        batch_op.add_column(sa.Column("partner_price_markup_percent", sa.Numeric(5, 2), nullable=True))
    
    # Пересчитываем все существующие price_2 = price_1 (убираем округление)
    op.execute("""
        UPDATE price_products 
        SET price_2 = price_1, round_delta = 0 
        WHERE price_1 IS NOT NULL AND price_2 IS NOT NULL
    """)
    
    # Пересчитываем все записи в истории цен
    op.execute("""
        UPDATE price_history 
        SET new_price_2 = new_price_1, old_price_2 = old_price_1
        WHERE new_price_1 IS NOT NULL AND new_price_2 IS NOT NULL
    """)
    
    op.execute("""
        UPDATE price_history 
        SET price = new_price_1
        WHERE new_price_1 IS NOT NULL AND price IS NOT NULL AND new_price_2 IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Восстанавливаем округление (обратная операция не выполняется автоматически)
    # Можно оставить как есть или добавить логику восстановления округления
    with op.batch_alter_table("partners") as batch_op:
        batch_op.drop_column("partner_price_markup_percent")

