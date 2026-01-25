"""add_brand_key_and_alias_key

Revision ID: 08054e09e2b8
Revises: db5cca638d76
Create Date: 2026-01-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08054e09e2b8'
down_revision: Union[str, Sequence[str], None] = 'db5cca638d76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def normalize_key(text: str) -> str:
    """Нормализует текст для создания устойчивого ключа поиска"""
    import re
    if not text or not text.strip():
        return ""
    
    key = text.lower().strip()
    key = re.sub(r'\s*&\s*', 'and', key)  # & → and
    key = re.sub(r'[-_]', ' ', key)  # дефисы → пробелы
    key = re.sub(r'[.,;:!?()\[\]{}"\']', '', key)  # убираем знаки препинания
    key = re.sub(r'\s+', ' ', key)  # нормализуем пробелы
    key = key.strip()
    key = key.replace(' ', '')  # убираем все пробелы
    
    return key if key else ""


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем колонки
    op.add_column('brands', sa.Column('key', sa.String(), nullable=True))
    op.add_column('brand_aliases', sa.Column('alias_key', sa.String(), nullable=True))
    
    # Создаем временную функцию нормализации в SQLite
    # SQLite не поддерживает функции напрямую, поэтому используем Python для заполнения
    
    # Создаем индексы (пока nullable, потом сделаем unique после заполнения)
    op.create_index(op.f('ix_brands_key'), 'brands', ['key'], unique=False)
    op.create_index(op.f('ix_brand_aliases_alias_key'), 'brand_aliases', ['alias_key'], unique=False)
    
    # Заполняем существующие записи через connection.execute
    connection = op.get_bind()
    
    # Заполняем brands.key
    brands = connection.execute(sa.text("SELECT id, name_canonical FROM brands")).fetchall()
    for brand_id, name_canonical in brands:
        key = normalize_key(name_canonical)
        if key:
            connection.execute(
                sa.text("UPDATE brands SET key = :key WHERE id = :id"),
                {"key": key, "id": brand_id}
            )
    
    # Заполняем brand_aliases.alias_key
    aliases = connection.execute(sa.text("SELECT id, alias_upper FROM brand_aliases")).fetchall()
    for alias_id, alias_upper in aliases:
        key = normalize_key(alias_upper)
        if key:
            connection.execute(
                sa.text("UPDATE brand_aliases SET alias_key = :key WHERE id = :id"),
                {"key": key, "id": alias_id}
            )
    
    # Теперь делаем колонки NOT NULL и добавляем unique constraints
    # Сначала обновляем NULL значения пустой строкой (если есть)
    connection.execute(sa.text("UPDATE brands SET key = '' WHERE key IS NULL"))
    connection.execute(sa.text("UPDATE brand_aliases SET alias_key = '' WHERE alias_key IS NULL"))
    
    # Делаем NOT NULL (SQLite не поддерживает alter_column с nullable напрямую, используем raw SQL)
    # Для SQLite нужно пересоздать таблицу или использовать более простой подход
    # В данном случае просто убедимся, что все значения заполнены и создадим unique constraint
    
    # Добавляем unique constraints (SQLite создаст индекс автоматически)
    try:
        op.create_unique_constraint('uq_brands_key', 'brands', ['key'])
    except Exception:
        # Если constraint уже существует, пропускаем
        pass
    
    try:
        op.create_unique_constraint('uq_brand_aliases_alias_key', 'brand_aliases', ['alias_key'])
    except Exception:
        # Если constraint уже существует, пропускаем
        pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_brand_aliases_alias_key', 'brand_aliases', type_='unique')
    op.drop_constraint('uq_brands_key', 'brands', type_='unique')
    op.drop_index(op.f('ix_brand_aliases_alias_key'), table_name='brand_aliases')
    op.drop_index(op.f('ix_brands_key'), table_name='brands')
    op.drop_column('brand_aliases', 'alias_key')
    op.drop_column('brands', 'key')
