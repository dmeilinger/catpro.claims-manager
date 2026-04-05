"""add app_config table

Revision ID: b3f0e8a9c2d1
Revises: a742875c23f7
Create Date: 2026-04-01 00:00:00.000000

Singleton configuration table managed via the Settings UI.
Seeds with defaults matching the original .env values.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f0e8a9c2d1"
down_revision: Union[str, Sequence[str], None] = "a742875c23f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("test_mode", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("test_adjuster_id", sa.String(), nullable=False, server_default="342436"),
        sa.Column("test_branch_id", sa.String(), nullable=False, server_default="2529"),
        sa.Column("updated_at", sa.String(), nullable=True),
    )
    # Seed singleton row — inherits DRY_RUN=true and TEST_MODE=true from original .env
    op.execute(
        "INSERT INTO app_config (id, dry_run, test_mode, test_adjuster_id, test_branch_id) "
        "VALUES (1, 1, 1, '342436', '2529')"
    )


def downgrade() -> None:
    op.drop_table("app_config")
