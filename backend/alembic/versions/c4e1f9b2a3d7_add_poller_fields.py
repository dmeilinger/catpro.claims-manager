"""add poller fields to app_config

Revision ID: c4e1f9b2a3d7
Revises: b3f0e8a9c2d1
Create Date: 2026-04-02 00:00:00.000000

Adds poller control and status fields to the app_config singleton row.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e1f9b2a3d7"
down_revision: Union[str, Sequence[str], None] = "b3f0e8a9c2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("poller_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("app_config", sa.Column("poller_status", sa.String(), nullable=True))
    op.add_column("app_config", sa.Column("last_heartbeat", sa.String(), nullable=True))
    op.add_column("app_config", sa.Column("last_run_at", sa.String(), nullable=True))
    op.add_column("app_config", sa.Column("last_error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_config", "last_error")
    op.drop_column("app_config", "last_run_at")
    op.drop_column("app_config", "last_heartbeat")
    op.drop_column("app_config", "poller_status")
    op.drop_column("app_config", "poller_enabled")
