"""Add price uploads table and price.upload permission

Revision ID: 010_add_price_uploads_and_permission
Revises: 009_add_price_products_and_history
Create Date: 2025-12-02 01:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# revision identifiers, used by Alembic.
revision = '010_add_price_uploads_and_permission'
down_revision = '009_add_price_products_and_history'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'price_uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('source_date', sa.Date(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.Column('total_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('new_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('up_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('down_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('removed_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unchanged_count', sa.Integer(), nullable=True, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_price_uploads_id'), 'price_uploads', ['id'], unique=False)

    # Добавляем колонку price_upload_id в price_history (без внешнего ключа для совместимости SQLite)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('price_history')]
    if 'price_upload_id' not in cols:
        op.add_column('price_history', sa.Column('price_upload_id', sa.Integer(), nullable=True))

    # Добавляем permission price.upload и выдаём ADMIN
    permission_table = table(
        "permissions",
        column("id", sa.Integer),
        column("key", sa.String),
        column("label", sa.String),
    )
    role_table = table(
        "roles",
        column("id", sa.Integer),
        column("name", sa.String),
    )
    role_permissions_table = table(
        "role_permissions",
        column("id", sa.Integer),
        column("role_id", sa.Integer),
        column("permission_id", sa.Integer),
    )

    existing_keys = {row.key for row in conn.execute(select(permission_table.c.key))}
    if "price.upload" not in existing_keys:
        conn.execute(permission_table.insert().values(key="price.upload", label="Загрузка прайса"))

    admin_role = conn.execute(
        select(role_table.c.id).where(role_table.c.name == "ADMIN")
    ).fetchone()
    if admin_role:
        perm = conn.execute(
            select(permission_table.c.id).where(permission_table.c.key == "price.upload")
        ).fetchone()
        if perm:
            exists = conn.execute(
                select(role_permissions_table.c.id).where(
                    role_permissions_table.c.role_id == admin_role.id,
                    role_permissions_table.c.permission_id == perm.id,
                )
            ).fetchone()
            if not exists:
                conn.execute(
                    role_permissions_table.insert().values(
                        role_id=admin_role.id, permission_id=perm.id
                    )
                )


def downgrade():
    # Удаляем permission price.upload
    conn = op.get_bind()
    permission_table = table(
        "permissions",
        column("id", sa.Integer),
        column("key", sa.String),
        column("label", sa.String),
    )
    role_permissions_table = table(
        "role_permissions",
        column("id", sa.Integer),
        column("role_id", sa.Integer),
        column("permission_id", sa.Integer),
    )

    perm_rows = conn.execute(
        select(permission_table.c.id).where(permission_table.c.key == "price.upload")
    ).fetchall()
    perm_ids = [row.id for row in perm_rows]
    if perm_ids:
        conn.execute(
            role_permissions_table.delete().where(
                role_permissions_table.c.permission_id.in_(perm_ids)
            )
        )
        conn.execute(permission_table.delete().where(permission_table.c.id.in_(perm_ids)))

    # Откатываем колонку price_upload_id
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('price_history')]
    if 'price_upload_id' in cols:
        op.drop_column('price_history', 'price_upload_id')

    op.drop_index(op.f('ix_price_uploads_id'), table_name='price_uploads')
    op.drop_table('price_uploads')
