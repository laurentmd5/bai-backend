"""Add performance indexes for admin endpoints.

Revision ID: 002
Revises: 001_initial_schema
Create Date: 2026-05-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for optimized queries."""
    
    # Indexes on knowledge_documents table
    op.create_index('idx_knowledge_docs_status', 'knowledge_documents', ['status'])
    op.create_index('idx_knowledge_docs_created_at', 'knowledge_documents', ['created_at'])
    op.create_index('idx_knowledge_docs_uploaded_by', 'knowledge_documents', ['uploaded_by'])
    op.create_index('idx_knowledge_docs_language', 'knowledge_documents', ['language'])
    
    # Indexes on conversations table
    op.create_index('idx_conversations_channel', 'conversations', ['channel'])
    op.create_index('idx_conversations_created_at', 'conversations', ['created_at'])
    op.create_index('idx_conversations_session_id', 'conversations', ['session_id'])
    
    # Indexes on audit_logs table
    op.create_index('idx_audit_logs_admin_id', 'audit_logs', ['admin_id'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    """Drop performance indexes."""
    
    # Drop indexes in reverse order
    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('idx_audit_logs_action', table_name='audit_logs')
    op.drop_index('idx_audit_logs_admin_id', table_name='audit_logs')
    
    op.drop_index('idx_conversations_session_id', table_name='conversations')
    op.drop_index('idx_conversations_created_at', table_name='conversations')
    op.drop_index('idx_conversations_channel', table_name='conversations')
    
    op.drop_index('idx_knowledge_docs_language', table_name='knowledge_documents')
    op.drop_index('idx_knowledge_docs_uploaded_by', table_name='knowledge_documents')
    op.drop_index('idx_knowledge_docs_created_at', table_name='knowledge_documents')
    op.drop_index('idx_knowledge_docs_status', table_name='knowledge_documents')
