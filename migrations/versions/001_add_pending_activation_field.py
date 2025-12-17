"""Add pending_activation field to users table

Revision ID: 001_add_pending_activation_field
Revises: d5b34f323ca5
Create Date: 2023-11-30 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001_add_pending_activation_field'
down_revision = 'd5b34f323ca5'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле pending_activation к таблице users
    op.add_column('users', sa.Column('pending_activation', sa.Boolean(), nullable=True))
    
    # Устанавливаем значение по умолчанию для существующих записей
    op.execute("UPDATE users SET pending_activation = FALSE WHERE pending_activation IS NULL")
    
    # Делаем поле NOT NULL с значением по умолчанию
    op.alter_column('users', 'pending_activation',
               existing_type=sa.Boolean(),
               nullable=False,
               server_default='false')


def downgrade():
    # Удаляем поле pending_activation из таблицы users
    op.drop_column('users', 'pending_activation')