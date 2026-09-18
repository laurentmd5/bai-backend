"""
Document parser for knowledge base uploads.
Supports: TXT, PDF, DOCX, MD

This module handles extracting text content from various document formats
for indexing in the vector database and knowledge base.
"""

import io
import logging
from typing import Optional
import tempfile
import os
from pathlib import Path
from app.core.config import settings

try:
    import pypdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from llama_cloud import AsyncLlamaCloud
    HAS_LLAMAPARSE = True
except ImportError:
    HAS_LLAMAPARSE = False

from app.services.processing.document_processor import DocumentProcessor

from app.core.logging import get_logger

logger = get_logger(__name__)

# Resource caps to prevent denial of service / memory exhaustion
MAX_PDF_PAGES: int = 100
MAX_DOCX_PARAGRAPHS: int = 2000
MAX_DOCX_TABLES: int = 100
MAX_EXTRACTED_TEXT_LENGTH: int = 1_000_000  # 1 million characters (~1MB text)
MAX_CHUNKS_PER_DOCUMENT: int = 500


class DocumentParsingError(Exception):
    """Raised when document parsing fails."""
    pass


async def parse_document_content(
    content: bytes,
    content_type: str,
    filename: Optional[str] = None
) -> str:
    """
    Parse document content to plain text.
    
    Args:
        content: Raw file bytes
        content_type: MIME type
        filename: Original filename (used as fallback)
    
    Returns:
        Extracted text content
    
    Raises:
        DocumentParsingError: If parsing fails
    """
    if not content:
        raise DocumentParsingError("Document is empty (0 bytes)")
        
    filename = filename or "document"
    fn_lower = filename.lower()
    
    # Detect format from content_type or filename
    if content_type == "application/pdf" or fn_lower.endswith(".pdf"):
        return await _parse_pdf(content)
    
    elif (
        content_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ]
        or fn_lower.endswith((".docx", ".doc"))
    ):
        return await _parse_docx(content)
    
    elif (
        content_type in ["text/plain", "text/markdown"]
        or fn_lower.endswith((".txt", ".md"))
    ):
        decoded = None
        for enc in ("utf-8", "utf-8-sig"):
            try:
                dec = content.decode(enc)
                if dec.strip():
                    decoded = dec
                    break
            except UnicodeDecodeError:
                continue
        if not decoded:
            dec = content.decode("utf-8", errors="ignore")
            if dec.strip():
                decoded = dec
        if decoded:
            if len(decoded) > MAX_EXTRACTED_TEXT_LENGTH:
                logger.warning(
                    "text_document_capped",
                    original_length=len(decoded),
                    capped_length=MAX_EXTRACTED_TEXT_LENGTH,
                )
                decoded = decoded[:MAX_EXTRACTED_TEXT_LENGTH]
            return decoded
        raise DocumentParsingError("Unable to decode text document")
    
    else:
        raise DocumentParsingError(f"Unsupported document format: {content_type} ({filename})")



async def _parse_with_llama(content: bytes, suffix: str) -> str:
    """Extract text from file using LlamaCloud."""
    if not settings.LLAMA_CLOUD_API_KEY:
        raise DocumentParsingError("LlamaCloud API key not configured")
        
    api_key_str = (
        settings.LLAMA_CLOUD_API_KEY.get_secret_value()
        if hasattr(settings.LLAMA_CLOUD_API_KEY, "get_secret_value")
        else str(settings.LLAMA_CLOUD_API_KEY)
    )
    if not api_key_str or not api_key_str.strip():
        raise DocumentParsingError("LlamaCloud API key is empty")
        
    client = AsyncLlamaCloud(api_key=api_key_str)
    
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        
        file_info = await client.files.create(
            file=Path(temp_path), 
            purpose="parse"
        )
        
        result = await client.parsing.parse(
            file_id=file_info.id,
            version="latest",
            expand=["markdown"]
        )
        
        if not result or not result.markdown or not result.markdown.pages:
            raise DocumentParsingError(f"No text extracted from {suffix} via LlamaCloud")
            
        text_parts = [page.markdown for page in result.markdown.pages if hasattr(page, 'markdown') and page.markdown]
        if not text_parts:
            raise DocumentParsingError("No markdown content found via LlamaCloud")
            
        return "\n\n".join(text_parts)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


async def _parse_pdf(content: bytes) -> str:
    """Extract text from PDF using LlamaCloud (if available) or pypdf (fallback)."""
    if HAS_LLAMAPARSE and settings.LLAMA_CLOUD_API_KEY:
        try:
            return await _parse_with_llama(content, suffix=".pdf")
        except Exception as e:
            logger.warning(f"LlamaParse failed, falling back to pypdf: {str(e)}")

    if not HAS_PDF:
        raise DocumentParsingError(
            "PDF support requires pypdf. Install with: pip install pypdf"
        )
    
    try:
        pdf_file = io.BytesIO(content)
        reader = pypdf.PdfReader(pdf_file)
        
        num_pages = len(reader.pages)
        if num_pages > MAX_PDF_PAGES:
            logger.warning(
                "pdf_pages_exceeded_cap",
                total_pages=num_pages,
                capped_pages=MAX_PDF_PAGES,
            )

        text_parts = []
        total_chars = 0
        for page_num, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                    total_chars += len(text)
                    if total_chars >= MAX_EXTRACTED_TEXT_LENGTH:
                        logger.warning(
                            "pdf_extracted_text_capped",
                            total_chars=total_chars,
                            max_allowed=MAX_EXTRACTED_TEXT_LENGTH,
                        )
                        break
            except Exception as e:
                logger.warning(f"Failed to extract page {page_num}: {str(e)}")
        
        if not text_parts:
            raise DocumentParsingError("No text extracted from PDF (possibly scanned image)")
        
        full_text = "\n\n".join(text_parts)
        return full_text[:MAX_EXTRACTED_TEXT_LENGTH]
    
    except DocumentParsingError:
        raise
    except Exception as e:
        raise DocumentParsingError(f"PDF parsing failed: {str(e)}")


async def _parse_docx(content: bytes) -> str:
    """Extract text from DOCX using LlamaCloud (if available) or python-docx (fallback)."""
    if HAS_LLAMAPARSE and settings.LLAMA_CLOUD_API_KEY:
        try:
            return await _parse_with_llama(content, suffix=".docx")
        except Exception as e:
            logger.warning(f"LlamaParse failed for DOCX, falling back to python-docx: {str(e)}")

    if not HAS_DOCX:
        raise DocumentParsingError(
            "DOCX support requires python-docx. Install with: pip install python-docx"
        )
    
    try:
        docx_file = io.BytesIO(content)
        doc = DocxDocument(docx_file)
        
        text_parts = []
        total_chars = 0
        for para in doc.paragraphs[:MAX_DOCX_PARAGRAPHS]:
            if para.text.strip():
                text_parts.append(para.text.strip())
                total_chars += len(para.text)
                if total_chars >= MAX_EXTRACTED_TEXT_LENGTH:
                    break
                
        # Also extract table text up to MAX_DOCX_TABLES
        if total_chars < MAX_EXTRACTED_TEXT_LENGTH:
            for table in doc.tables[:MAX_DOCX_TABLES]:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        text_parts.append(row_text)
                        total_chars += len(row_text)
                        if total_chars >= MAX_EXTRACTED_TEXT_LENGTH:
                            break
                if total_chars >= MAX_EXTRACTED_TEXT_LENGTH:
                    break
        
        if not text_parts:
            raise DocumentParsingError("No text extracted from DOCX")
        
        full_text = "\n\n".join(text_parts)
        return full_text[:MAX_EXTRACTED_TEXT_LENGTH]
    
    except DocumentParsingError:
        raise
    except Exception as e:
        raise DocumentParsingError(f"DOCX parsing failed: {str(e)}")



def split_text_into_chunks(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50
) -> list[dict]:
    """
    Split text into overlapping chunks using the DocumentProcessor
    so that web upload and init_qdrant.py behave identically.
    
    Args:
        text: Full text content
        chunk_size: Target chunk size (characters)
        overlap: Overlap between chunks (characters)
    
    Returns:
        List of {'content': str, 'index': int} dicts
    """
    # Truncate text before chunking to prevent memory explosion
    safe_text = text[:MAX_EXTRACTED_TEXT_LENGTH]
    
    # Convert token limits to character limits for DocumentProcessor
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    
    processor = DocumentProcessor(chunk_size=char_size, chunk_overlap=char_overlap)
    doc = processor._create_document(safe_text, "web_upload")
    processor_chunks = processor.chunk_document(doc)
    
    chunks = []
    for i, chunk in enumerate(processor_chunks):
        if chunk.page_content.strip():
            chunks.append({
                "content": chunk.page_content.strip(),
                "index": i,
            })
            if len(chunks) >= MAX_CHUNKS_PER_DOCUMENT:
                logger.warning(
                    "document_chunks_capped",
                    total_chunks=len(processor_chunks),
                    max_allowed=MAX_CHUNKS_PER_DOCUMENT,
                )
                break
            
    return chunks if chunks else [{"content": safe_text, "index": 0}]
