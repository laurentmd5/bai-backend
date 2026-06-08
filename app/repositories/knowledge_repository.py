"""
Knowledge document repository for BARROW.AI.
Handles knowledge document database operations.
"""

from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.knowledge import KnowledgeDocument, DocumentStatus
from app.repositories.base import BaseRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class KnowledgeRepository(BaseRepository[KnowledgeDocument, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for KnowledgeDocument model operations.
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(KnowledgeDocument, session)
    
    async def create_document(
        self,
        filename: str,
        title: str,
        content_hash: str,
        description: Optional[str] = None,
        source_type: str = "upload",
        language: str = "en",
        uploaded_by: Optional[UUID] = None,
        is_public: bool = True,
    ) -> KnowledgeDocument:
        """
        Create a new knowledge document record.
        
        Args:
            filename: Original filename
            title: Document title
            content_hash: SHA-256 content hash
            description: Optional description
            source_type: Source type
            language: Document language
            uploaded_by: Admin user ID
            is_public: Whether available for RAG
            
        Returns:
            Created KnowledgeDocument instance
        """
        doc = KnowledgeDocument(
            filename=filename,
            title=title,
            content_hash=content_hash,
            description=description,
            source_type=source_type,
            language=language,
            uploaded_by=uploaded_by,
            is_public=is_public,
            status=DocumentStatus.PENDING.value,
        )
        
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        
        logger.info(
            "knowledge_document_created",
            doc_id=str(doc.id),
            title=title,
            filename=filename
        )
        
        return doc
    
    async def get_by_hash(self, content_hash: str) -> Optional[KnowledgeDocument]:
        """
        Find document by content hash (for deduplication).
        
        Args:
            content_hash: SHA-256 hash
            
        Returns:
            KnowledgeDocument or None
        """
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.content_hash == content_hash
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_indexing_status(
        self,
        doc_id: UUID,
        status: DocumentStatus,
        chunks_count: Optional[int] = None,
        token_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update document indexing status.
        
        Args:
            doc_id: Document UUID
            status: New status
            chunks_count: Number of chunks (if completed)
            token_count: Token count (if completed)
            error_message: Error message (if failed)
            
        Returns:
            True if updated
        """
        values = {'status': status.value}
        
        if status == DocumentStatus.ACTIVE:
            values['indexed_at'] = datetime.utcnow()
            if chunks_count is not None:
                values['chunks_count'] = chunks_count
            if token_count is not None:
                values['token_count'] = token_count
        elif status == DocumentStatus.ERROR:
            values['error_message'] = error_message
        
        stmt = (
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == doc_id)
            .values(**values)
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.info(
                "document_status_updated",
                doc_id=str(doc_id),
                status=status.value
            )
        
        return updated
    
    async def get_active_documents(
        self,
        language: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[KnowledgeDocument], int]:
        """
        Get active (indexed) documents available for RAG.
        
        Args:
            language: Optional language filter
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            Tuple of (documents, total_count)
        """
        stmt = select(KnowledgeDocument).where(
            and_(
                KnowledgeDocument.status == DocumentStatus.ACTIVE.value,
                KnowledgeDocument.is_public == True
            )
        )
        
        if language:
            stmt = stmt.where(KnowledgeDocument.language == language)
        
        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Get documents
        stmt = stmt.order_by(KnowledgeDocument.uploaded_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        documents = list(result.scalars().all())
        
        return documents, total
    
    async def record_retrieval(
        self,
        doc_id: UUID,
        relevance_score: float
    ) -> None:
        """
        Record that a document was retrieved in RAG.
        
        Args:
            doc_id: Document UUID
            relevance_score: Relevance score of the retrieval
        """
        # Get current stats
        stmt = select(
            KnowledgeDocument.times_retrieved,
            KnowledgeDocument.avg_relevance_score
        ).where(KnowledgeDocument.id == doc_id)
        
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        
        if not row:
            return
        
        times_retrieved = (row.times_retrieved or 0) + 1
        
        # Exponential moving average for relevance
        if row.avg_relevance_score is None:
            new_avg = relevance_score
        else:
            alpha = 0.1
            new_avg = alpha * relevance_score + (1 - alpha) * row.avg_relevance_score
        
        stmt = (
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == doc_id)
            .values(
                times_retrieved=times_retrieved,
                avg_relevance_score=new_avg,
                last_retrieved_at=datetime.utcnow(),
            )
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
    
    async def deprecate_document(self, doc_id: UUID) -> bool:
        """
        Mark a document as deprecated.
        
        Args:
            doc_id: Document UUID
            
        Returns:
            True if updated
        """
        stmt = (
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == doc_id)
            .values(
                status=DocumentStatus.DEPRECATED.value,
                deprecated_at=datetime.utcnow(),
                is_public=False,
            )
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        return result.rowcount > 0
    
    async def get_documents_needing_reindex(
        self,
        limit: int = 10
    ) -> List[KnowledgeDocument]:
        """
        Get documents that need reindexing (error or pending).
        
        Args:
            limit: Maximum results
            
        Returns:
            List of documents
        """
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.status.in_([
                DocumentStatus.PENDING.value,
                DocumentStatus.ERROR.value,
            ])
        ).order_by(KnowledgeDocument.uploaded_at).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def list_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        language: Optional[str] = None,
        uploaded_by: Optional[str] = None,
    ) -> List[KnowledgeDocument]:
        """
        List knowledge base documents with optional filtering.
        
        Args:
            limit: Maximum documents to return
            offset: Pagination offset
            status: Filter by status (pending|indexing|active|error|deprecated|archived)
            language: Filter by language (en, fr, etc.)
            uploaded_by: Filter by uploader admin ID
            
        Returns:
            List of KnowledgeDocument instances
        """
        stmt = select(KnowledgeDocument)
        
        # Apply filters
        if status:
            stmt = stmt.where(KnowledgeDocument.status == status)
        if language:
            stmt = stmt.where(KnowledgeDocument.language == language)
        if uploaded_by:
            stmt = stmt.where(KnowledgeDocument.uploaded_by == uploaded_by)
        
        # Apply pagination
        stmt = stmt.order_by(
            KnowledgeDocument.uploaded_at.desc()
        ).offset(offset).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def count_documents(
        self,
        status: Optional[str] = None,
        language: Optional[str] = None,
        uploaded_by: Optional[str] = None,
    ) -> int:
        """
        Count knowledge base documents with optional filtering.
        
        Args:
            status: Filter by status
            language: Filter by language
            uploaded_by: Filter by uploader admin ID
            
        Returns:
            Total count
        """
        stmt = select(func.count()).select_from(KnowledgeDocument)
        
        # Apply filters
        if status:
            stmt = stmt.where(KnowledgeDocument.status == status)
        if language:
            stmt = stmt.where(KnowledgeDocument.language == language)
        if uploaded_by:
            stmt = stmt.where(KnowledgeDocument.uploaded_by == uploaded_by)
        
        result = await self.session.execute(stmt)
        return result.scalar() or 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get knowledge base statistics.
        
        Returns:
            Statistics dict
        """
        # Total documents by status
        status_stmt = select(
            KnowledgeDocument.status,
            func.count().label('count'),
            func.sum(KnowledgeDocument.chunks_count).label('total_chunks'),
        ).group_by(KnowledgeDocument.status)
        
        status_result = await self.session.execute(status_stmt)
        
        stats = {
            'by_status': {},
            'total_documents': 0,
            'total_chunks': 0,
            'total_tokens': 0,
            'active_documents': 0,
            'total_retrievals': 0,
        }
        
        for row in status_result:
            stats['by_status'][row.status] = {
                'count': row.count,
                'chunks': row.total_chunks or 0,
            }
            stats['total_documents'] += row.count
            stats['total_chunks'] += row.total_chunks or 0
            if row.status == DocumentStatus.ACTIVE.value:
                stats['active_documents'] = row.count
        
        # Total retrievals
        retrieval_stmt = select(
            func.sum(KnowledgeDocument.times_retrieved)
        ).select_from(KnowledgeDocument)
        
        retrieval_result = await self.session.execute(retrieval_stmt)
        stats['total_retrievals'] = retrieval_result.scalar() or 0
        
        return stats