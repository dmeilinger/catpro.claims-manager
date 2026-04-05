"""initial schema

Revision ID: a742875c23f7
Revises:
Create Date: 2026-04-02 17:22:01.139847

Adds dry_run column, indexes, and UNIQUE constraint on claim_data.email_id.
For existing databases: stamp the base, then upgrade to apply these changes.
For fresh databases: tables are created by SQLAlchemy create_all or alembic upgrade.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a742875c23f7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add dry_run column to processed_emails
    with op.batch_alter_table("processed_emails", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_index("ix_processed_emails_processed_at", ["processed_at"])
        batch_op.create_index("ix_processed_emails_status", ["status"])

    # Backfill dry_run from existing claim_id = 'DRY_RUN' rows
    op.execute(
        "UPDATE processed_emails SET dry_run = 1 WHERE claim_id = 'DRY_RUN'"
    )

    # Add UNIQUE constraint and index on claim_data.email_id
    with op.batch_alter_table("claim_data", schema=None) as batch_op:
        batch_op.create_index("ix_claim_data_email_id", ["email_id"])
        batch_op.create_unique_constraint("uq_claim_data_email_id", ["email_id"])


def downgrade() -> None:
    with op.batch_alter_table("claim_data", schema=None) as batch_op:
        batch_op.drop_constraint("uq_claim_data_email_id", type_="unique")
        batch_op.drop_index("ix_claim_data_email_id")

    with op.batch_alter_table("processed_emails", schema=None) as batch_op:
        batch_op.drop_index("ix_processed_emails_status")
        batch_op.drop_index("ix_processed_emails_processed_at")
        batch_op.drop_column("dry_run")
