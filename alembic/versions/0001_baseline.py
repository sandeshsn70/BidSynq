"""Baseline: the schema BidSynq V1-V5 already created with Base.metadata.create_all().

SAFE FOR EXISTING DATABASES. Each table is created only if it does not exist yet, so on your
current Render database this migration changes nothing and simply records the version in the
``alembic_version`` table. On a brand-new empty database it creates the full schema.

Nothing in this file drops, truncates, renames or alters anything.

Revision ID: 0001_baseline
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def _create(name: str, *elements) -> bool:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(name):
        return False
    op.create_table(name, *elements)
    return True


def _index(name: str, table: str, column: str, unique: bool = False) -> None:
    op.create_index(name, table, [column], unique=unique)


def upgrade() -> None:
    if _create(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("company_name", sa.String(180), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    ):
        _index("ix_users_email", "users", "email", unique=True)

    if _create(
        "tenders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("tender_type", sa.String(30), nullable=False),
        sa.Column("deadline", TS, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("mandatory_requirements", sa.Text(), nullable=False),
        sa.Column("w_price", sa.Float(), nullable=False),
        sa.Column("w_delivery", sa.Float(), nullable=False),
        sa.Column("w_trust", sa.Float(), nullable=False),
        sa.Column("w_match", sa.Float(), nullable=False),
        sa.Column("anti_sniping", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    ):
        _index("ix_tenders_buyer_id", "tenders", "buyer_id")
        _index("ix_tenders_title", "tenders", "title")
        _index("ix_tenders_deadline", "tenders", "deadline")
        _index("ix_tenders_status", "tenders", "status")

    if _create(
        "bids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("requirement_match", sa.Float(), nullable=False),
        sa.Column("mandatory_met", sa.Boolean(), nullable=False),
        sa.Column("compliance_notes", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("tender_id", "supplier_id", name="uq_bid_supplier_tender"),
    ):
        _index("ix_bids_tender_id", "bids", "tender_id")
        _index("ix_bids_supplier_id", "bids", "supplier_id")

    if _create(
        "tender_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id"), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("stored_filename"),
    ):
        _index("ix_tender_documents_tender_id", "tender_documents", "tender_id")
        _index("ix_tender_documents_uploaded_by", "tender_documents", "uploaded_by")

    if _create(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(180), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    ):
        _index("ix_document_chunks_document_id", "document_chunks", "document_id")
        _index("ix_document_chunks_tender_id", "document_chunks", "tender_id")

    if _create(
        "supplier_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("on_time", sa.Boolean(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("tender_id", "supplier_id", name="uq_outcome_tender_supplier"),
    ):
        _index("ix_supplier_outcomes_tender_id", "supplier_outcomes", "tender_id")
        _index("ix_supplier_outcomes_supplier_id", "supplier_outcomes", "supplier_id")
        _index("ix_supplier_outcomes_recorded_by", "supplier_outcomes", "recorded_by")

    if _create(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    ):
        _index("ix_audit_logs_actor_id", "audit_logs", "actor_id")
        _index("ix_audit_logs_action", "audit_logs", "action")
        _index("ix_audit_logs_entity_type", "audit_logs", "entity_type")
        _index("ix_audit_logs_entity_id", "audit_logs", "entity_id")
        _index("ix_audit_logs_entry_hash", "audit_logs", "entry_hash", unique=True)
        _index("ix_audit_logs_created_at", "audit_logs", "created_at")

    if _create(
        "risk_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id"), nullable=False),
        sa.Column("bid_id", sa.Integer(), sa.ForeignKey("bids.id"), nullable=True),
        sa.Column("rule_key", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("reviewed_at", TS, nullable=True),
    ):
        _index("ix_risk_alerts_fingerprint", "risk_alerts", "fingerprint", unique=True)
        _index("ix_risk_alerts_tender_id", "risk_alerts", "tender_id")
        _index("ix_risk_alerts_bid_id", "risk_alerts", "bid_id")
        _index("ix_risk_alerts_rule_key", "risk_alerts", "rule_key")
        _index("ix_risk_alerts_status", "risk_alerts", "status")
        _index("ix_risk_alerts_created_at", "risk_alerts", "created_at")


def downgrade() -> None:
    # Intentionally empty: this project never drops production tables automatically.
    pass
