"""Add triage lifecycle and email_actions audit table.

Adds triage_status (NOT NULL DEFAULT 'unreviewed') and body_text to
processed_emails. Adds agent output columns to the DB for future use
(no Python model references yet — added when agent ships).

Creates email_actions audit table. FK is intentionally NO CASCADE:
deleting a processed_emails row while actions exist raises IntegrityError
at runtime (PRAGMA foreign_keys=ON). This is deliberate — the audit trail
must be explicitly managed before an email record can be removed.

triage_status SQLite backfill: ALTER TABLE ADD COLUMN with a DEFAULT
backfills the value to all existing rows automatically. No UPDATE needed.

Revision ID: e6f3a7b5d2c8
Revises: d5e2b8a4c1f9
Create Date: 2026-04-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f3a7b5d2c8"
down_revision: Union[str, Sequence[str], None] = "d5e2b8a4c1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- processed_emails: triage + body storage + agent output columns ---
    # CRITICAL: use server_default (not default=) so SQLite emits DEFAULT
    # in the ALTER TABLE DDL and backfills existing rows.
    op.add_column(
        "processed_emails",
        sa.Column("triage_status", sa.Text(), nullable=False, server_default="unreviewed"),
    )
    op.add_column(
        "processed_emails",
        sa.Column("body_text", sa.Text(), nullable=True),
    )
    # Agent output columns — in DB now for future migration safety.
    # Do NOT reference in models.py or schemas.py until agent ships.
    op.add_column(
        "processed_emails",
        sa.Column("agent_classification", sa.Text(), nullable=True),
    )
    op.add_column(
        "processed_emails",
        sa.Column("agent_confidence", sa.REAL(), nullable=True),
    )
    op.add_column(
        "processed_emails",
        sa.Column("agent_reasoning", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_processed_emails_triage_status", "processed_emails", ["triage_status"]
    )

    # --- email_actions audit table ---
    op.create_table(
        "email_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "email_id",
            sa.Integer(),
            sa.ForeignKey("processed_emails.id"),
            nullable=False,
        ),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),  # JSON string
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_email_actions_email_id", "email_actions", ["email_id"])
    op.create_index("ix_email_actions_created_at", "email_actions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_actions_created_at", table_name="email_actions")
    op.drop_index("ix_email_actions_email_id", table_name="email_actions")
    op.drop_table("email_actions")

    # batch_alter_table required for column drops on SQLite
    with op.batch_alter_table("processed_emails") as batch_op:
        batch_op.drop_index("ix_processed_emails_triage_status")
        batch_op.drop_column("agent_reasoning")
        batch_op.drop_column("agent_confidence")
        batch_op.drop_column("agent_classification")
        batch_op.drop_column("body_text")
        batch_op.drop_column("triage_status")
