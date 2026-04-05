"""add poll_interval_seconds to app_config

Revision ID: d5e2b8a4c1f9
Revises: c4e1f9b2a3d7
Create Date: 2026-04-05 00:00:00.000000

Adds configurable poll interval to the app_config singleton row.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e2b8a4c1f9"
down_revision: Union[str, Sequence[str], None] = "c4e1f9b2a3d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column(
            "poll_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_config", "poll_interval_seconds")
