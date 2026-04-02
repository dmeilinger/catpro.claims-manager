"""SQLAlchemy ORM models matching the existing SQLite schema."""

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str]
    internet_message_id: Mapped[str] = mapped_column(unique=True)
    subject: Mapped[str | None]
    sender: Mapped[str | None]
    received_at: Mapped[str | None]
    processed_at: Mapped[str]
    claim_id: Mapped[str | None]
    status: Mapped[str] = mapped_column(String, default="pending")
    error_message: Mapped[str | None]
    dry_run: Mapped[bool] = mapped_column(default=False)

    claim_data: Mapped["ClaimData | None"] = relationship(
        back_populates="email", uselist=False
    )

    __table_args__ = (
        Index("ix_processed_emails_status", "status"),
        Index("ix_processed_emails_processed_at", "processed_at"),
    )

    def __repr__(self) -> str:
        return f"<ProcessedEmail id={self.id} status={self.status!r} claim_id={self.claim_id!r}>"


class ClaimData(Base):
    __tablename__ = "claim_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("processed_emails.id"))

    # Insured
    insured_first_name: Mapped[str | None]
    insured_last_name: Mapped[str | None]
    insured_email: Mapped[str | None]
    insured_phone: Mapped[str | None]
    insured_cell: Mapped[str | None]
    insured_address1: Mapped[str | None]
    insured_city: Mapped[str | None]
    insured_state: Mapped[str | None]
    insured_zip: Mapped[str | None]

    # Secondary insured
    secondary_insured_first: Mapped[str | None]
    secondary_insured_last: Mapped[str | None]

    # Policy
    policy_number: Mapped[str | None]
    policy_effective: Mapped[str | None]
    policy_expiration: Mapped[str | None]

    # Loss
    loss_date: Mapped[str | None]
    loss_type: Mapped[str | None]
    loss_description: Mapped[str | None] = mapped_column(Text)
    loss_address1: Mapped[str | None]
    loss_city: Mapped[str | None]
    loss_state: Mapped[str | None]
    loss_zip: Mapped[str | None]

    # Client / insurer
    client_company_name: Mapped[str | None]
    client_claim_number: Mapped[str | None]

    # Agent
    agent_company: Mapped[str | None]
    agent_phone: Mapped[str | None]
    agent_email: Mapped[str | None]
    agent_address1: Mapped[str | None]
    agent_city: Mapped[str | None]
    agent_state: Mapped[str | None]
    agent_zip: Mapped[str | None]

    # Assignment
    assigned_adjuster_name: Mapped[str | None]

    # Resolved FileTrac IDs
    filetrac_company_id: Mapped[str | None]
    filetrac_contact_id: Mapped[str | None]
    filetrac_branch_id: Mapped[str | None]
    filetrac_adjuster_id: Mapped[str | None]
    filetrac_manager_id: Mapped[str | None]
    filetrac_csrf_token: Mapped[str | None]

    # Submission
    submission_payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str]

    email: Mapped["ProcessedEmail"] = relationship(back_populates="claim_data")

    __table_args__ = (
        UniqueConstraint("email_id", name="uq_claim_data_email_id"),
        Index("ix_claim_data_email_id", "email_id"),
    )

    def __repr__(self) -> str:
        return f"<ClaimData id={self.id} email_id={self.email_id}>"
