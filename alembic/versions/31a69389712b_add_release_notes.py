"""add_release_notes

Revision ID: 31a69389712b
Revises: 285dc33c6319
Create Date: 2026-01-20 01:51:50.781016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31a69389712b'
down_revision: Union[str, Sequence[str], None] = '285dc33c6319'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "release_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("release_type", sa.String(), nullable=False, server_default="minor"),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("changes", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(op.f("ix_release_notes_id"), "release_notes", ["id"])
    op.create_index(op.f("ix_release_notes_version"), "release_notes", ["version"], unique=True)
    op.create_index(op.f("ix_release_notes_release_date"), "release_notes", ["release_date"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_release_notes_release_date"), table_name="release_notes")
    op.drop_index(op.f("ix_release_notes_version"), table_name="release_notes")
    op.drop_index(op.f("ix_release_notes_id"), table_name="release_notes")
    op.drop_table("release_notes")
