"""Create commercial_leads table for sales and quote requests pipeline.

Revision ID: 006
Revises: 005
Create Date: 2026-09-30 12:45:00.000000

This migration creates the commercial_leads table to persist
qualified commercial leads, quote requests, and client contacts.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create commercial_leads table and indexes."""
    op.create_table(
        'commercial_leads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('channel', sa.String(50), nullable=False, server_default='web'),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('service_category', sa.String(100), nullable=True),
        sa.Column('requirements_summary', sa.Text(), nullable=False),
        sa.Column('qualification_answers', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='new'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )

    op.create_index('idx_lead_session_id', 'commercial_leads', ['session_id'])
    op.create_index('idx_lead_channel', 'commercial_leads', ['channel'])
    op.create_index('idx_lead_full_name', 'commercial_leads', ['full_name'])
    op.create_index('idx_lead_email', 'commercial_leads', ['email'])
    op.create_index('idx_lead_phone', 'commercial_leads', ['phone_number'])
    op.create_index('idx_lead_status', 'commercial_leads', ['status'])
    op.create_index('idx_lead_category', 'commercial_leads', ['service_category'])
    op.create_index('idx_lead_status_created', 'commercial_leads', ['status', 'created_at'])
    op.create_index('idx_lead_created_at', 'commercial_leads', ['created_at'])


def downgrade() -> None:
    """Drop commercial_leads table and indexes."""
    op.drop_index('idx_lead_created_at', table_name='commercial_leads')
    op.drop_index('idx_lead_status_created', table_name='commercial_leads')
    op.drop_index('idx_lead_category', table_name='commercial_leads')
    op.drop_index('idx_lead_status', table_name='commercial_leads')
    op.drop_index('idx_lead_phone', table_name='commercial_leads')
    op.drop_index('idx_lead_email', table_name='commercial_leads')
    op.drop_index('idx_lead_full_name', table_name='commercial_leads')
    op.drop_index('idx_lead_channel', table_name='commercial_leads')
    op.drop_index('idx_lead_session_id', table_name='commercial_leads')
    op.drop_table('commercial_leads')
