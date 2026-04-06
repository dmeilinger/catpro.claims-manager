"""Add error_traceback and error_phase to processed_emails.

error_traceback stores the full Python traceback (format_exc()) so errors
can be diagnosed without log access.
error_phase identifies which pipeline stage failed:
  'extraction' | 'auth' | 'submission'

Both are nullable TEXT — existing rows keep NULL, which the UI renders
as absent (no traceback panel shown).

Revision ID: f7a4c2e8b9d3
Revises: e6f3a7b5d2c8
Create Date: 2026-04-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a4c2e8b9d3"
down_revision: Union[str, Sequence[str], None] = "e6f3a7b5d2c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processed_emails", sa.Column("error_traceback", sa.Text(), nullable=True))
    op.add_column("processed_emails", sa.Column("error_phase", sa.String(), nullable=True))


def downgrade() -> None:
    # SQLite does not support DROP COLUMN before 3.35 — recreate table approach not needed
    # for dev; just leave columns in place if rolling back.
    pass
