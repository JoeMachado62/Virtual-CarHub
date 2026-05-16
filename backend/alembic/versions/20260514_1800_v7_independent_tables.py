"""v7 independent tables: agent_service_tokens, dealer_groups, fleet_state,
openclaw_dispatch_log, agent_versions, worker_health

Revision ID: 20260514_1800
Revises: 20260502_1200
Create Date: 2026-05-14 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


revision = "20260514_1800"
down_revision = "20260502_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- agent_service_tokens ---
    op.create_table(
        "agent_service_tokens",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("rotated_from", UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rotated_from"], ["agent_service_tokens.id"]),
        sa.UniqueConstraint("token_hash"),
    )

    # --- dealer_groups ---
    op.create_table(
        "dealer_groups",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- fleet_state ---
    op.create_table(
        "fleet_state",
        sa.Column("vps_hostname", sa.Text(), nullable=False),
        sa.Column("wg_ip", INET(), nullable=False),
        sa.Column("reported_by_agent", sa.Text(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("runtime_status", sa.Text(), nullable=False),
        sa.Column("openclaw_node_uptime_seconds", sa.BigInteger(), nullable=True),
        sa.Column("active_workflows", sa.Integer(), nullable=True),
        sa.Column("queue_depth", sa.Integer(), nullable=True),
        sa.Column("pending_approvals", sa.Integer(), nullable=True),
        sa.Column("drift_alerts", JSONB(), nullable=True),
        sa.Column("free_disk_gb", sa.Numeric(8, 2), nullable=True),
        sa.Column("free_memory_gb", sa.Numeric(6, 2), nullable=True),
        sa.Column("recent_errors", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("vps_hostname"),
    )

    # --- openclaw_dispatch_log ---
    op.create_table(
        "openclaw_dispatch_log",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("admin_agent_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_vps", sa.Text(), nullable=True),
        sa.Column("target_resource", sa.Text(), nullable=True),
        sa.Column("payload_redacted", JSONB(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("outcome_detail", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_openclaw_dispatch_log_admin", "openclaw_dispatch_log", ["admin_agent_id"])
    op.create_index("idx_openclaw_dispatch_log_at", "openclaw_dispatch_log", [sa.text("occurred_at DESC")])

    # --- agent_versions ---
    op.create_table(
        "agent_versions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("persona_sha", sa.Text(), nullable=False),
        sa.Column("skill_catalog_sha", sa.Text(), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("deployed_by", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_versions_agent", "agent_versions", [sa.text("agent_id, deployed_at DESC")])

    # --- worker_health ---
    op.create_table(
        "worker_health",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("vps_hostname", sa.Text(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("openclaw_healthy", sa.Boolean(), nullable=False),
        sa.Column("queue_depth", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_worker_health_vps_at", "worker_health", [sa.text("vps_hostname, reported_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_worker_health_vps_at", table_name="worker_health")
    op.drop_table("worker_health")

    op.drop_index("idx_agent_versions_agent", table_name="agent_versions")
    op.drop_table("agent_versions")

    op.drop_index("idx_openclaw_dispatch_log_at", table_name="openclaw_dispatch_log")
    op.drop_index("idx_openclaw_dispatch_log_admin", table_name="openclaw_dispatch_log")
    op.drop_table("openclaw_dispatch_log")

    op.drop_table("fleet_state")
    op.drop_table("dealer_groups")
    op.drop_table("agent_service_tokens")
