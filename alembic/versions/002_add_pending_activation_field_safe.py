"""Add pending_activation field to users table safely

Revision ID: 002_add_pending_activation_field_safe
Revises: 0ab2969563f5
Create Date: 2025-11-30 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers
revision = '002_add_pending_activation_field_safe'
down_revision = '0ab2969563f5'
branch_labels = None
depends_on = None


def upgrade():
    # Проверяем, существует ли колонка pending_activation
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns('users')
    column_names = [column['name'] for column in columns]
    
    if 'pending_activation' not in column_names:
        # Добавляем поле pending_activation к таблице users
        op.add_column('users', sa.Column('pending_activation', sa.Boolean(), nullable=False, server_default='false'))
    else:
        print("Колонка pending_activation уже существует")


def downgrade():
    # Удаляем поле pending_activation из таблицы users
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns('users')
    column_names = [column['name'] for column in columns]
    
    if 'pending_activation' in column_names:
        op.drop_column('users', 'pending_activation')
    else:
        print("Колонка pending_activation не существует для удаления")