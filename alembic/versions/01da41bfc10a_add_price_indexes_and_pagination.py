"""add_price_indexes_and_pagination

Revision ID: 01da41bfc10a
Revises: 669e791786f9
Create Date: 2026-01-06 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01da41bfc10a'
down_revision: Union[str, Sequence[str], None] = '669e791786f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем индексы для ускорения поиска и фильтрации
    # Проверяем, существуют ли уже индексы (могут быть созданы в других миграциях)
    
    # Индекс для price_list_id (если есть такое поле)
    # op.create_index('idx_price_products_price_list_id', 'price_products', ['price_list_id'], unique=False)
    
    # Индекс для search_text (для полнотекстового поиска)
    try:
        op.create_index('idx_price_products_search_text', 'price_products', ['search_text'], unique=False)
    except Exception:
        pass  # Индекс может уже существовать
    
    # Индекс для updated_at (для сортировки)
    try:
        op.create_index('idx_price_products_updated_at', 'price_products', ['updated_at'], unique=False)
    except Exception:
        pass
    
    # Индекс для is_active и is_in_current_pricelist (для фильтрации)
    try:
        op.create_index('idx_price_products_active_pricelist', 'price_products', ['is_active', 'is_in_current_pricelist'], unique=False)
    except Exception:
        pass
    
    # Индекс для ai_status (для фильтрации по статусу нормализации)
    try:
        op.create_index('idx_price_products_ai_status', 'price_products', ['ai_status'], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    """Downgrade schema."""
    try:
        op.drop_index('idx_price_products_ai_status', table_name='price_products')
    except Exception:
        pass
    try:
        op.drop_index('idx_price_products_active_pricelist', table_name='price_products')
    except Exception:
        pass
    try:
        op.drop_index('idx_price_products_updated_at', table_name='price_products')
    except Exception:
        pass
    try:
        op.drop_index('idx_price_products_search_text', table_name='price_products')
    except Exception:
        pass
