"""Initial database schema for BARROW.AI POC.

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-17 10:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and indexes."""
    
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    
    # =========================================================================
    # Table: admin_users
    # =========================================================================
    op.create_table(
        'admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='viewer'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('two_factor_secret', sa.String(255), nullable=True),
        sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('backup_codes', postgresql.JSONB, nullable=True),
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_ip', postgresql.INET, nullable=True),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_reset_token', sa.String(255), nullable=True),
        sa.Column('password_reset_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('preferences', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    op.create_index('idx_admin_users_email', 'admin_users', ['email'], unique=True)
    op.create_index('idx_admin_users_email_active', 'admin_users', ['email', 'is_active'])
    op.create_index('idx_admin_users_role', 'admin_users', ['role'])
    op.create_index('idx_admin_users_is_active', 'admin_users', ['is_active'])
    op.create_index('idx_admin_users_locked', 'admin_users', ['locked_until'], postgresql_where=sa.text('locked_until IS NOT NULL'))
    
    # =========================================================================
    # Table: sessions
    # =========================================================================
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('language', sa.String(20), nullable=False, server_default='en'),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('opted_out', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_active', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    op.create_index('idx_sessions_external_id', 'sessions', ['external_id'], postgresql_where=sa.text('external_id IS NOT NULL'))
    op.create_index('idx_sessions_channel_active', 'sessions', ['channel', 'is_active'])
    op.create_index('idx_sessions_last_active', 'sessions', ['last_active'], postgresql_where=sa.text('is_active = true'))
    
    # =========================================================================
    # Table: conversations
    # =========================================================================
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('bot_response', sa.Text(), nullable=False),
        sa.Column('sources', postgresql.JSONB, nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('feedback', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('llm_tokens_used', sa.Integer(), nullable=True),
        sa.Column('fallback_triggered', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('validation_failed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    op.create_index('idx_conversations_session_id', 'conversations', ['session_id'])
    op.create_index('idx_conversations_created_at', 'conversations', ['created_at'])
    op.create_index('idx_conversations_channel_created', 'conversations', ['channel', 'created_at'])
    op.create_index('idx_conversations_session_created', 'conversations', ['session_id', 'created_at'])
    op.create_index('idx_conversations_feedback', 'conversations', ['feedback'], postgresql_where=sa.text('feedback IS NOT NULL'))
    op.create_index('idx_conversations_cache_hit', 'conversations', ['cache_hit'], postgresql_where=sa.text('cache_hit = true'))
    op.create_index('idx_conversations_recent', 'conversations', ['created_at'], postgresql_where=sa.text("created_at > NOW() - INTERVAL '30 days'"))
    
    # =========================================================================
    # Table: knowledge_docs
    # =========================================================================
    op.create_table(
        'knowledge_docs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False, server_default='upload'),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('chunks_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('previous_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('times_retrieved', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_relevance_score', sa.Float(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('admin_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    op.create_index('idx_knowledge_docs_content_hash', 'knowledge_docs', ['content_hash'], unique=True)
    op.create_index('idx_knowledge_docs_status', 'knowledge_docs', ['status'])
    op.create_index('idx_knowledge_docs_uploaded_at', 'knowledge_docs', ['uploaded_at'])
    op.create_index('idx_knowledge_docs_public_active', 'knowledge_docs', ['is_public', 'status'], postgresql_where=sa.text("is_public = true AND status = 'active'"))
    
    # =========================================================================
    # Table: audit_logs
    # =========================================================================
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('admin_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('admin_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB, nullable=True),
        sa.Column('severity', sa.String(10), nullable=False, server_default='INFO'),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    op.create_index('idx_audit_logs_admin_id', 'audit_logs', ['admin_id'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_action_created', 'audit_logs', ['action', 'created_at'])
    op.create_index('idx_audit_logs_severity', 'audit_logs', ['severity'], postgresql_where=sa.text("severity IN ('WARN', 'CRITICAL')"))
    
    # =========================================================================
    # Table: whatsapp_optouts
    # =========================================================================
    op.create_table(
        'whatsapp_optouts',
        sa.Column('phone_number', sa.String(20), primary_key=True),
        sa.Column('opted_out_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('source', sa.String(20), nullable=False, server_default='whatsapp'),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
    )
    
    # =========================================================================
    # Table: jwt_blacklist
    # =========================================================================
    op.create_table(
        'jwt_blacklist',
        sa.Column('jti', sa.String(64), primary_key=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('revoked_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('admin_users.id', ondelete='SET NULL'), nullable=True),
    )
    
    op.create_index('idx_jwt_blacklist_expires_at', 'jwt_blacklist', ['expires_at'])
    
    # =========================================================================
    # Create updated_at trigger function
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trg_admin_users_updated_at
        BEFORE UPDATE ON admin_users
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # =========================================================================
    # Create analytics views
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE VIEW v_daily_stats AS
        SELECT
            DATE_TRUNC('day', created_at) AS day,
            channel,
            COUNT(*) AS total_conversations,
            AVG(confidence) AS avg_confidence,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
            COUNT(*) FILTER (WHERE feedback = 1) AS positive_feedback,
            COUNT(*) FILTER (WHERE feedback = -1) AS negative_feedback,
            COUNT(*) FILTER (WHERE cache_hit = true) AS cache_hits,
            COUNT(*) FILTER (WHERE fallback_triggered = true) AS fallbacks
        FROM conversations
        GROUP BY DATE_TRUNC('day', created_at), channel
        ORDER BY day DESC;
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW v_top_questions AS
        SELECT
            LEFT(user_message, 100) AS question_preview,
            COUNT(*) AS frequency,
            AVG(confidence) AS avg_confidence,
            COUNT(*) FILTER (WHERE feedback = 1) AS positive_feedback,
            COUNT(*) FILTER (WHERE feedback = -1) AS negative_feedback
        FROM conversations
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY LEFT(user_message, 100)
        ORDER BY frequency DESC
        LIMIT 20;
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW v_hourly_activity AS
        SELECT
            DATE_TRUNC('hour', created_at) AS hour,
            channel,
            COUNT(*) AS message_count,
            COUNT(DISTINCT session_id) AS active_sessions
        FROM conversations
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY DATE_TRUNC('hour', created_at), channel
        ORDER BY hour DESC;
    """)


def downgrade() -> None:
    """Drop all tables and views."""
    
    # Drop views first
    op.execute("DROP VIEW IF EXISTS v_hourly_activity")
    op.execute("DROP VIEW IF EXISTS v_top_questions")
    op.execute("DROP VIEW IF EXISTS v_daily_stats")
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_admin_users_updated_at ON admin_users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables in reverse order
    op.drop_table('jwt_blacklist')
    op.drop_table('whatsapp_optouts')
    op.drop_table('audit_logs')
    op.drop_table('knowledge_docs')
    op.drop_table('conversations')
    op.drop_table('sessions')
    op.drop_table('admin_users')
    
    # Drop extensions (optional, may be used by other applications)
    # op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    # op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')