"""
Admin knowledge base management endpoints for BARROW.AI.

Endpoints for managing knowledge documents used in the RAG pipeline.
Supports uploading, listing, updating, and deleting documents.
"""

import asyncio
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin, get_admin_service
from app.core.database import get_session
from app.core.logging import get_logger
from app.models.domain.admin import AuditAction
from app.models.response.knowledge import KnowledgeDocumentResponse
from app.models.domain.knowledge import DocumentStatus
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.admin_service import AdminService
from app.services.admin.document_parser import (
    parse_document_content,
    split_text_into_chunks,
    DocumentParsingError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Admin Knowledge Base Management"])

# Supported document formats
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("", response_model=Dict[str, Any])
async def list_knowledge_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(
        None,
        regex="^(pending|indexing|active|error|deprecated|archived)$"
    ),
    language: Optional[str] = Query(None),
    uploaded_by: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    List all knowledge base documents with optional filtering.
    
    Query Parameters:
    - limit: Max documents to return (max 100, default 50)
    - offset: Pagination offset (default 0)
    - status: Filter by status (pending|indexing|active|error|deprecated|archived)
    - language: Filter by language (en, fr, etc.)
    - uploaded_by: Filter by uploader admin ID
    """
    
    logger.info(
        "list_knowledge_documents_requested",
        admin_id=current_admin["id"],
        limit=limit,
        offset=offset,
    )
    
    # Check permission
    # NOTE: For Phase 1, assume all authenticated admins can read knowledge
    
    repo = KnowledgeRepository(session)
    
    # Build filters
    filters = {}
    if status:
        filters["status"] = status
    if language:
        filters["language"] = language
    if uploaded_by:
        filters["uploaded_by"] = uploaded_by
    
    # Get documents
    docs = await repo.list_documents(
        limit=limit,
        offset=offset,
        **filters
    )
    
    # Get total count
    total = await repo.count_documents(**filters)
    
    # Log audit
    try:
        await AdminService.log_audit_static(
            session=session,
            admin_id=current_admin["id"],
            action=AuditAction.VIEW_CONVERSATIONS.value,
            details={"limit": limit, "offset": offset, "filters": filters}
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
    
    return {
        "documents": [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "title": doc.title,
                "status": doc.status,
                "language": doc.language,
                "uploaded_by": str(doc.uploaded_by) if doc.uploaded_by else None,
                "created_at": doc.created_at.isoformat(),
                "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
                "chunks_count": doc.chunks_count or 0,
            }
            for doc in docs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def upload_knowledge_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    language: str = Form("en"),
    is_public: bool = Form(True),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Upload and index a new knowledge document.
    
    Supported formats: PDF, DOCX, TXT, MD
    Max file size: 10MB
    
    In Phase 1, documents are stored in PostgreSQL immediately with status=ACTIVE.
    Qdrant indexing is deferred to Phase 2 as an optional background task.
    """
    
    logger.info(
        "upload_knowledge_document_requested",
        filename=file.filename,
        admin_id=current_admin["id"],
    )
    
    # 🔴 SECURITY: Validate and sanitize filename (Path Traversal Prevention)
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    # Remove path components (prevents ../ attacks)
    original_filename = file.filename
    safe_filename = os.path.basename(original_filename)
    
    # Verify filename changed (indicates path traversal attempt)
    if safe_filename != original_filename:
        logger.warning(
            "upload_rejected_path_traversal_attempt",
            original_filename=original_filename,
            safe_filename=safe_filename,
            admin_id=current_admin["id"],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path components are not allowed"
        )
    
    # Validate file extension
    file_extension = Path(safe_filename).suffix.lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        logger.warning(
            "upload_rejected_invalid_extension",
            filename=safe_filename,
            extension=file_extension,
            allowed=list(ALLOWED_EXTENSIONS),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension: {file_extension}. "
                   f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Remove dangerous characters from filename (keep only alphanumeric, dash, underscore, dot)
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', safe_filename)
    
    # Prevent duplicate attacks: if file already exists, append UUID
    # This would be used if we ever store files on disk
    # For now, filename is mainly for display in DB
    if len(safe_filename) > 255:
        # Truncate to 200 chars + extension
        name_part = safe_filename[:200]
        ext_part = Path(safe_filename).suffix
        safe_filename = name_part + ext_part
    
    logger.info(
        "filename_validated_and_sanitized",
        original=original_filename,
        sanitized=safe_filename,
    )
    
    # Validate file content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(
            "upload_rejected_unsupported_format",
            content_type=file.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Supported: PDF, DOCX, TXT, MD"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        logger.warning(
            "upload_rejected_file_too_large",
            size=len(content),
            max_size=MAX_FILE_SIZE,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)"
        )
    
    # Calculate content hash to detect duplicates
    content_hash = hashlib.sha256(content).hexdigest()
    
    repo = KnowledgeRepository(session)
    
    # Check for duplicate content
    existing = await repo.get_by_hash(content_hash)
    if existing:
        logger.warning(
            "upload_rejected_duplicate",
            existing_doc_id=str(existing.id),
            content_hash=content_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document already indexed (ID: {existing.id})"
        )
    
    try:
        # Parse document content
        logger.info("parsing_document", filename=safe_filename)
        text_content = await parse_document_content(
            content,
            file.content_type,
            safe_filename
        )
        
        # Split into chunks for later indexing
        chunks = split_text_into_chunks(text_content, chunk_size=512)
        chunk_count = len(chunks)
        
        # Estimate token count (rough: 1 token ≈ 4 characters)
        token_count = len(text_content) // 4
        
        logger.info(
            "document_parsed",
            filename=file.filename,
            chunks=chunk_count,
            tokens=token_count,
        )
        
    except DocumentParsingError as e:
        logger.error(f"Failed to parse document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse document: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error parsing document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document"
        )
    
    # Create document record in PostgreSQL
    try:
        doc = await repo.create_document(
            filename=safe_filename,
            title=title or safe_filename,
            content_hash=content_hash,
            description=description,
            language=language,
            uploaded_by=current_admin["id"],
            is_public=is_public,
        )
        
        # Set status to ACTIVE immediately (no Qdrant blocking in Phase 1)
        await repo.update_indexing_status(
            doc.id, 
            DocumentStatus.ACTIVE,
            chunks_count=chunk_count,
            token_count=token_count
        )
        
        logger.info(
            "document_stored",
            doc_id=str(doc.id),
            filename=file.filename,
        )
        
    except Exception as e:
        logger.error(f"Failed to create document record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store document"
        )
    
    # Log audit
    try:
        await AdminService.log_audit_static(
            session=session,
            admin_id=current_admin["id"],
            action=AuditAction.KNOWLEDGE_UPLOAD.value,
            details={
                "doc_id": str(doc.id),
                "filename": safe_filename,
                "original_filename": original_filename,
                "size": len(content),
                "language": language
            }
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
    
    return {
        "document_id": str(doc.id),
        "filename": safe_filename,
        "title": doc.title,
        "status": "active",
        "chunks_count": chunk_count,
        "token_count": token_count,
        "created_at": datetime.utcnow().isoformat(),
        "message": "Document uploaded successfully"
    }


@router.get("/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_knowledge_document(
    document_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get details of a specific knowledge document.
    """
    
    logger.info(
        "get_knowledge_document_requested",
        document_id=document_id,
        admin_id=current_admin["id"],
    )
    
    repo = KnowledgeRepository(session)
    
    try:
        doc_id = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    doc = await repo.get_by_id(doc_id)
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Log audit
    try:
        await AdminService.log_audit_static(
            session=session,
            admin_id=current_admin["id"],
            action=AuditAction.VIEW_CONVERSATIONS.value,
            details={"doc_id": str(doc.id)}
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
    
    return KnowledgeDocumentResponse(
        id=str(doc.id),
        filename=doc.filename,
        title=doc.title,
        description=doc.description,
        content_hash=doc.content_hash,
        source_type=doc.source_type,
        language=doc.language,
        chunks_count=doc.chunks_count or 0,
        token_count=doc.token_count,
        status=doc.status,
        error_message=doc.error_message,
        version=doc.version,
        times_retrieved=doc.times_retrieved,
        avg_relevance_score=doc.avg_relevance_score,
        is_public=doc.is_public,
        uploaded_by=str(doc.uploaded_by) if doc.uploaded_by else None,
        uploaded_by_name=doc.uploaded_by_name,
        uploaded_at=doc.created_at,
        indexed_at=doc.indexed_at,
        last_retrieved_at=doc.last_retrieved_at,
    )


@router.put("/{document_id}", response_model=Dict[str, Any])
async def update_knowledge_document(
    document_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_public: Optional[bool] = Form(None),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Update a knowledge base document metadata.
    """
    
    logger.info(
        "update_knowledge_document_requested",
        document_id=document_id,
        admin_id=current_admin["id"],
    )
    
    repo = KnowledgeRepository(session)
    
    try:
        doc_id = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    doc = await repo.get_by_id(doc_id)
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Update fields
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    if is_public is not None:
        update_data["is_public"] = is_public
    
    if update_data:
        await repo.update_document(doc_id, **update_data)
    
    # Log audit
    try:
        await AdminService.log_audit_static(
            session=session,
            admin_id=current_admin["id"],
            action=AuditAction.CONFIG_CHANGE.value,
            details={"doc_id": str(doc.id), "updates": update_data}
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
    
    return {
        "document_id": str(doc.id),
        "message": "Document updated successfully",
        "updated_fields": list(update_data.keys())
    }


@router.delete("/{document_id}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def delete_knowledge_document(
    document_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a knowledge base document.
    
    This removes the document from PostgreSQL and marks it for cleanup from Qdrant.
    """
    
    logger.info(
        "delete_knowledge_document_requested",
        document_id=document_id,
        admin_id=current_admin["id"],
    )
    
    repo = KnowledgeRepository(session)
    
    try:
        doc_id = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    doc = await repo.get_by_id(doc_id)
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Soft delete or hard delete
    await repo.delete_document(doc_id)
    
    # Log audit
    try:
        await AdminService.log_audit_static(
            session=session,
            admin_id=current_admin["id"],
            action=AuditAction.KNOWLEDGE_DELETE.value,
            details={"doc_id": str(doc.id), "filename": doc.filename}
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
    
    return {
        "document_id": str(doc.id),
        "message": "Document deleted successfully"
    }
