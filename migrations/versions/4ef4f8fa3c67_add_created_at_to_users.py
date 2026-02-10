"""add created_at to users

Revision ID: 4ef4f8fa3c67
Revises: 
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision = "4ef4f8fa3c67"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add column with a default so existing rows don't break (SQLite batch mode)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )

    # Remove DB-level default after backfilling existing rows
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("created_at", server_default=None)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("created_at")
