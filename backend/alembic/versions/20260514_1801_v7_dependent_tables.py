"""v7 dependent tables: audit_log, dealers, dealer_contacts, dealer_group_members,
intent_threads, strategy_reports, dealer_threads, outbound_log, hitl_tasks,
pending_approvals

Revision ID: 20260514_1801
Revises: 20260514_1800
Create Date: 2026-05-14 18:01:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260514_1801"
down_revision = "20260514_1800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- audit_log (v7 agent-action audit; existing audit_events stays for deal lifecycle) ---
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("payload_redacted", JSONB(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("outcome_detail", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_log_agent_id", "audit_log", ["agent_id"])
    op.create_index("idx_audit_log_trace_id", "audit_log", ["trace_id"])
    op.create_index("idx_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")])
    op.create_index("idx_audit_log_target", "audit_log", ["target_type", "target_id"])

    # --- dealers (v7 wholesale prospect/target; existing dealer_partners stays for formal partnerships) ---
    op.create_table(
        "dealers",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("location_city", sa.Text(), nullable=True),
        sa.Column("location_state", sa.Text(), nullable=True),
        sa.Column("location_zip", sa.Text(), nullable=True),
        sa.Column("primary_brand", sa.Text(), nullable=True),
        sa.Column("secondary_brands", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("chat_widget_url", sa.Text(), nullable=True),
        sa.Column("main_phone", sa.Text(), nullable=True),
        sa.Column("reputation_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dealers_state", "dealers", ["location_state"])
    op.create_index("idx_dealers_primary_brand", "dealers", ["primary_brand"])

    # --- dealer_contacts (FK → dealers) ---
    op.create_table(
        "dealer_contacts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dealer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("decision_maker_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dealer_id"], ["dealers.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_dealer_contacts_dealer", "dealer_contacts", ["dealer_id"])

    # --- dealer_group_members (FK → dealers, dealer_groups) ---
    op.create_table(
        "dealer_group_members",
        sa.Column("dealer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dealer_group_id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("dealer_id", "dealer_group_id"),
        sa.ForeignKeyConstraint(["dealer_id"], ["dealers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dealer_group_id"], ["dealer_groups.id"], ondelete="CASCADE"),
    )

    # --- intent_threads (deal_id FK → existing deals.id as nullable TEXT) ---
    op.create_table(
        "intent_threads",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column("intent_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("context_payload", JSONB(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("deal_id", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_intent_threads_contact", "intent_threads", ["contact_id"])
    op.create_index("idx_intent_threads_status", "intent_threads", ["status"])

    # --- strategy_reports (deal_id FK → existing deals.id as nullable) ---
    op.create_table(
        "strategy_reports",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column("vehicle_target", JSONB(), nullable=False),
        sa.Column("report_content", sa.Text(), nullable=False),
        sa.Column("key_data_points", JSONB(), nullable=True),
        sa.Column("outreach_targets", JSONB(), nullable=True),
        sa.Column("pricing_envelope", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("deal_id", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_strategy_reports_contact", "strategy_reports", ["contact_id"])
    op.create_index("idx_strategy_reports_status", "strategy_reports", ["status"])

    # --- dealer_threads (FK → strategy_reports, dealers, dealer_contacts) ---
    op.create_table(
        "dealer_threads",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_report_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dealer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dealer_contact_id", UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_quote_otd", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("deal_id", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["strategy_report_id"], ["strategy_reports.id"]),
        sa.ForeignKeyConstraint(["dealer_id"], ["dealers.id"]),
        sa.ForeignKeyConstraint(["dealer_contact_id"], ["dealer_contacts.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_dealer_threads_strategy", "dealer_threads", ["strategy_report_id"])
    op.create_index("idx_dealer_threads_dealer", "dealer_threads", ["dealer_id"])
    op.create_index("idx_dealer_threads_status", "dealer_threads", ["status"])

    # --- outbound_log (FK → dealer_threads; deal_id FK → existing deals) ---
    op.create_table(
        "outbound_log",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=True),
        sa.Column("dealer_thread_id", UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("body_redacted", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("rate_limit_check_passed", sa.Boolean(), nullable=False),
        sa.Column("deal_id", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dealer_thread_id"], ["dealer_threads.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_outbound_log_contact", "outbound_log", ["contact_id"])
    op.create_index("idx_outbound_log_dealer_thread", "outbound_log", ["dealer_thread_id"])
    op.create_index("idx_outbound_log_sent_at", "outbound_log", [sa.text("sent_at DESC")])

    # --- hitl_tasks (FK → intent_threads; deal_id FK → existing deals) ---
    op.create_table(
        "hitl_tasks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("trigger_code", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("context_payload", JSONB(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_action", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_id", sa.Text(), nullable=True),
        sa.Column("deal_id", sa.String(36), nullable=True),
        sa.Column("intent_thread_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["intent_thread_id"], ["intent_threads.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_hitl_tasks_status", "hitl_tasks", ["status"])
    op.create_index("idx_hitl_tasks_urgency", "hitl_tasks", ["urgency"])
    op.create_index("idx_hitl_tasks_created_at", "hitl_tasks", [sa.text("created_at DESC")])

    # --- pending_approvals ---
    op.create_table(
        "pending_approvals",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("resume_token", sa.Text(), nullable=False),
        sa.Column("proposing_agent", sa.Text(), nullable=False),
        sa.Column("workflow_name", sa.Text(), nullable=False),
        sa.Column("preview", JSONB(), nullable=False),
        sa.Column("notified_channels", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resume_token"),
    )
    op.create_index("idx_pending_approvals_status", "pending_approvals", [sa.text("(resolved_at IS NULL)")])


def downgrade() -> None:
    op.drop_index("idx_pending_approvals_status", table_name="pending_approvals")
    op.drop_table("pending_approvals")

    op.drop_index("idx_hitl_tasks_created_at", table_name="hitl_tasks")
    op.drop_index("idx_hitl_tasks_urgency", table_name="hitl_tasks")
    op.drop_index("idx_hitl_tasks_status", table_name="hitl_tasks")
    op.drop_table("hitl_tasks")

    op.drop_index("idx_outbound_log_sent_at", table_name="outbound_log")
    op.drop_index("idx_outbound_log_dealer_thread", table_name="outbound_log")
    op.drop_index("idx_outbound_log_contact", table_name="outbound_log")
    op.drop_table("outbound_log")

    op.drop_index("idx_dealer_threads_status", table_name="dealer_threads")
    op.drop_index("idx_dealer_threads_dealer", table_name="dealer_threads")
    op.drop_index("idx_dealer_threads_strategy", table_name="dealer_threads")
    op.drop_table("dealer_threads")

    op.drop_index("idx_strategy_reports_status", table_name="strategy_reports")
    op.drop_index("idx_strategy_reports_contact", table_name="strategy_reports")
    op.drop_table("strategy_reports")

    op.drop_index("idx_intent_threads_status", table_name="intent_threads")
    op.drop_index("idx_intent_threads_contact", table_name="intent_threads")
    op.drop_table("intent_threads")

    op.drop_table("dealer_group_members")

    op.drop_index("idx_dealer_contacts_dealer", table_name="dealer_contacts")
    op.drop_table("dealer_contacts")

    op.drop_index("idx_dealers_primary_brand", table_name="dealers")
    op.drop_index("idx_dealers_state", table_name="dealers")
    op.drop_table("dealers")

    op.drop_index("idx_audit_log_target", table_name="audit_log")
    op.drop_index("idx_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("idx_audit_log_trace_id", table_name="audit_log")
    op.drop_index("idx_audit_log_agent_id", table_name="audit_log")
    op.drop_table("audit_log")
