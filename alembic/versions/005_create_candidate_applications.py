"""Create candidate_applications table for recruitment pipeline.

Revision ID: 005
Revises: 004
Create Date: 2026-09-14 10:00:00.000000

This migration creates the candidate_applications table to durably persist
candidate screening interviews, CV profiles, and prescreening answers.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create candidate_applications table and indexes."""
    op.create_table(
        'candidate_applications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('channel', sa.String(50), nullable=False, server_default='whatsapp'),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('cv_filename', sa.String(255), nullable=True),
        sa.Column('raw_cv_text', sa.Text(), nullable=True),
        sa.Column('parsed_profile', sa.JSON(), nullable=True),
        sa.Column('answers_json', sa.JSON(), nullable=True),
        sa.Column('match_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('target_domains', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='new'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )

    op.create_index('idx_candidate_session_id', 'candidate_applications', ['session_id'])
    op.create_index('idx_candidate_channel', 'candidate_applications', ['channel'])
    op.create_index('idx_candidate_full_name', 'candidate_applications', ['full_name'])
    op.create_index('idx_candidate_email', 'candidate_applications', ['email'])
    op.create_index('idx_candidate_phone', 'candidate_applications', ['phone_number'])
    op.create_index('idx_candidate_status', 'candidate_applications', ['status'])
    op.create_index('idx_candidate_status_score', 'candidate_applications', ['status', 'match_score'])
    op.create_index('idx_candidate_created_at', 'candidate_applications', ['created_at'])


def downgrade() -> None:
    """Drop candidate_applications table and indexes."""
    op.drop_index('idx_candidate_created_at', table_name='candidate_applications')
    op.drop_index('idx_candidate_status_score', table_name='candidate_applications')
    op.drop_index('idx_candidate_status', table_name='candidate_applications')
    op.drop_index('idx_candidate_phone', table_name='candidate_applications')
    op.drop_index('idx_candidate_email', table_name='candidate_applications')
    op.drop_index('idx_candidate_full_name', table_name='candidate_applications')
    op.drop_index('idx_candidate_channel', table_name='candidate_applications')
    op.drop_index('idx_candidate_session_id', table_name='candidate_applications')
    op.drop_table('candidate_applications')
