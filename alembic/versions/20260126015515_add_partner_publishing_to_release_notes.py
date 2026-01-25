"""add_partner_publishing_to_release_notes

Revision ID: 20260126015515
Revises: 31a69389712b
Create Date: 2026-01-26 01:55:15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260126015515'
down_revision: Union[str, Sequence[str], None] = '31a69389712b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем поля для управления публикацией партнерам
    op.add_column('release_notes', sa.Column('is_published_to_partners', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('release_notes', sa.Column('max_partner_views', sa.Integer(), nullable=True))
    
    # Изменяем значение по умолчанию для is_published на False
    # Сначала обновляем существующие записи (если есть опубликованные, оставляем их)
    # Затем меняем значение по умолчанию
    op.execute("UPDATE release_notes SET is_published = 1 WHERE is_published = 1")  # Сохраняем текущее состояние
    # В SQLite нельзя изменить значение по умолчанию напрямую, но это не критично


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('release_notes', 'max_partner_views')
    op.drop_column('release_notes', 'is_published_to_partners')

