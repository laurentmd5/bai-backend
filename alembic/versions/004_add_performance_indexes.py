"""Add performance indexes for critical queries.

Revision ID: 004
Revises: 003
Create Date: 2026-05-18 14:30:00.000000

This migration adds indexes to optimize frequently used queries:
- conversations: filtering by status, date range, session
- audit_logs: filtering by admin_id for audit trails
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for conversations and audit_logs tables."""
    
    # ============================================================================
    # CONVERSATIONS TABLE INDEXES
    # ============================================================================
    
    # Index for filtering conversations by status (for analytics dashboards)
    # Usage: SELECT * FROM conversations WHERE status = 'active'
    op.create_index(
        'idx_conversations_status',
        'conversations',
        ['status'],
    )
    
    # Index for range queries on created_at (for time-based analytics)
    # Usage: SELECT * FROM conversations WHERE created_at > '2026-05-01'
    op.create_index(
        'idx_conversations_created_at_range',
        'conversations',
        ['created_at'],
        postgresql_order_by=sa.text("DESC"),
    )
    
    # Composite index for combined queries (session + date range)
    # Usage: SELECT * FROM conversations WHERE session_id = ? AND created_at > ?
    op.create_index(
        'idx_conversations_session_created',
        'conversations',
        ['session_id', sa.text('created_at DESC')],
    )
    
    # Partial index for feedback analysis (only non-NULL feedback)
    # Usage: SELECT * FROM conversations WHERE feedback IS NOT NULL
    op.create_index(
        'idx_conversations_feedback_nonnull',
        'conversations',
        ['feedback'],
        postgresql_where=sa.text('feedback IS NOT NULL'),
    )
    
    # ============================================================================
    # AUDIT_LOGS TABLE INDEXES
    # ============================================================================
    
    # Index for filtering audit logs by admin_id (for per-user audit trail)
    # Usage: SELECT * FROM audit_logs WHERE admin_id = ?
    op.create_index(
        'idx_audit_logs_admin_id',
        'audit_logs',
        ['admin_id'],
    )
    
    # Composite index for admin + severity filtering (security alerts)
    # Usage: SELECT * FROM audit_logs WHERE admin_id = ? AND severity = 'CRITICAL'
    op.create_index(
        'idx_audit_logs_admin_severity',
        'audit_logs',
        ['admin_id', 'severity'],
    )
    
    # Index on created_at for time-based queries in audit logs
    # Usage: SELECT * FROM audit_logs WHERE created_at > ?
    op.create_index(
        'idx_audit_logs_created_at',
        'audit_logs',
        ['created_at'],
        postgresql_order_by=sa.text("DESC"),
    )


def downgrade() -> None:
    """Remove all performance indexes."""
    
    # Drop indexes in reverse order
    op.drop_index('idx_conversations_status')
    op.drop_index('idx_conversations_created_at_range')
    op.drop_index('idx_conversations_session_created')
    op.drop_index('idx_conversations_feedback_nonnull')
    op.drop_index('idx_audit_logs_admin_id')
    op.drop_index('idx_audit_logs_admin_severity')
    op.drop_index('idx_audit_logs_created_at')
