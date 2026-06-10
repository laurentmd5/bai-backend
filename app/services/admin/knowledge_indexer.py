import asyncio
from typing import List
from uuid import UUID

from app.core.logging import get_logger
from app.core.database import get_session_context
from app.models.domain.knowledge import DocumentStatus
from app.repositories.knowledge_repository import KnowledgeRepository

logger = get_logger(__name__)

async def index_document_background_task(
    doc_id: UUID,
    chunks: List[str],
    document_name: str,
    language: str,
    app
) -> None:
    """
    Background task to index a document's chunks into Qdrant.
    Updates the document status in PostgreSQL upon completion or failure.
    """
    logger.info("background_indexing_started", doc_id=str(doc_id), chunks=len(chunks))
    
    # Extract RAG service from app state
    rag_service = getattr(app.state, "rag_service", None)
    if not rag_service:
        logger.error("background_indexing_failed", doc_id=str(doc_id), error="RAGService not found in app state")
        await _update_status(doc_id, DocumentStatus.ERROR, error_message="Internal Error: RAGService unavailable")
        return
        
    try:
        # Index into Qdrant
        indexed_count = await rag_service.index_document_chunks(
            chunks=chunks,
            document_name=document_name,
            section=document_name[:50],
            language=language
        )
        
        logger.info("background_indexing_completed", doc_id=str(doc_id), indexed=indexed_count)
        
        # Update DB status
        await _update_status(
            doc_id, 
            DocumentStatus.ACTIVE, 
            chunks_count=indexed_count
        )
        
    except Exception as e:
        logger.error("background_indexing_failed", doc_id=str(doc_id), error=str(e))
        await _update_status(doc_id, DocumentStatus.ERROR, error_message=str(e))

async def _update_status(
    doc_id: UUID, 
    status: DocumentStatus, 
    chunks_count: int = 0, 
    error_message: str = None
) -> None:
    """Helper to update document status in a fresh DB session."""
    try:
        async with get_session_context() as session:
            repo = KnowledgeRepository(session)
            if status == DocumentStatus.ERROR:
                doc = await repo.get_by_id(doc_id)
                if doc:
                    doc.mark_indexing_failed(error_message)
                    await session.commit()
            else:
                await repo.update_indexing_status(
                    doc_id,
                    status,
                    chunks_count=chunks_count
                )
                await session.commit()
    except Exception as db_e:
        logger.error("background_status_update_failed", doc_id=str(doc_id), error=str(db_e))
