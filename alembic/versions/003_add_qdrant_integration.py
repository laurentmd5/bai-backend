"""Add Qdrant integration support.

Revision ID: 003
Revises: 002
Create Date: 2026-05-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add knowledge chunks table and Qdrant integration columns."""
    
    # Create knowledge_chunks table
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),  # Store embedding as JSON array
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_doc_chunk_index'),
    )
    
    # Create index on document_id for faster queries
    op.create_index(
        'ix_knowledge_chunks_document_id',
        'knowledge_chunks',
        ['document_id'],
    )
    
    # Create index on created_at for time-based queries
    op.create_index(
        'ix_knowledge_chunks_created_at',
        'knowledge_chunks',
        ['created_at'],
    )
    
    # Add columns to knowledge_documents table for Qdrant tracking
    op.add_column(
        'knowledge_documents',
        sa.Column('qdrant_indexed_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    op.add_column(
        'knowledge_documents',
        sa.Column('qdrant_collection_id', sa.String(100), nullable=True),
    )
    
    op.add_column(
        'knowledge_documents',
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    
    # Create index on qdrant_indexed_at to track indexing status
    op.create_index(
        'ix_knowledge_documents_qdrant_indexed_at',
        'knowledge_documents',
        ['qdrant_indexed_at'],
    )


def downgrade() -> None:
    """Revert Qdrant integration support."""
    
    # Drop indexes
    op.drop_index('ix_knowledge_documents_qdrant_indexed_at')
    op.drop_index('ix_knowledge_chunks_created_at')
    op.drop_index('ix_knowledge_chunks_document_id')
    
    # Drop columns from knowledge_documents
    op.drop_column('knowledge_documents', 'error_message')
    op.drop_column('knowledge_documents', 'qdrant_collection_id')
    op.drop_column('knowledge_documents', 'qdrant_indexed_at')
    
    # Drop knowledge_chunks table
    op.drop_table('knowledge_chunks')
