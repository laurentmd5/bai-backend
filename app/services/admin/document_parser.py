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

logger = logging.getLogger(__name__)


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
    
    filename = filename or "document"
    
    # Detect format from content_type or filename
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return await _parse_pdf(content)
    
    elif content_type in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword"
    ] or filename.lower().endswith(".docx"):
        return await _parse_docx(content)
    
    elif content_type == "text/plain" or filename.lower().endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    
    elif content_type == "text/markdown" or filename.lower().endswith(".md"):
        return content.decode("utf-8", errors="ignore")
    
    else:
        raise DocumentParsingError(f"Unsupported format: {content_type}")


async def _parse_pdf(content: bytes) -> str:
    """Extract text from PDF using LlamaParse (if available) or pypdf (fallback)."""
    if HAS_LLAMAPARSE and settings.LLAMA_CLOUD_API_KEY:
        try:
            return await _parse_with_llama(content, suffix=".pdf")
        except Exception as e:
            logger.warning(f"LlamaParse failed, falling back to pypdf: {str(e)}")
            # Fallback to pypdf

    if not HAS_PDF:
        raise DocumentParsingError(
            "PDF support requires pypdf. Install with: pip install pypdf"
        )
    
    try:
        pdf_file = io.BytesIO(content)
        reader = pypdf.PdfReader(pdf_file)
        
        text_parts = []
        for page_num, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract page {page_num}: {str(e)}")
        
        if not text_parts:
            raise DocumentParsingError("No text extracted from PDF (possibly scanned image)")
        
        return "\n".join(text_parts)
    
    except DocumentParsingError:
        raise
    except Exception as e:
        raise DocumentParsingError(f"PDF parsing failed: {str(e)}")


async def _parse_with_llama(content: bytes, suffix: str) -> str:
    """Extract text from file using LlamaCloud."""
    api_key = settings.LLAMA_CLOUD_API_KEY.get_secret_value()
    client = AsyncLlamaCloud(api_key=api_key)
    
    # LlamaCloud requires a file path, so we write the bytes to a temp file
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        
        # 1. Upload the file
        file_info = await client.files.create(
            file=Path(temp_path), 
            purpose="parse"
        )
        
        # 2. Parse the document
        result = await client.parsing.parse(
            file_id=file_info.id,
            version="latest",
            expand=["markdown"]
        )
        
        if not result or not result.markdown or not result.markdown.pages:
            raise DocumentParsingError(f"No text extracted from {suffix} via LlamaCloud")
            
        text_parts = [page.markdown for page in result.markdown.pages if hasattr(page, 'markdown') and page.markdown]
        if not text_parts:
            raise DocumentParsingError(f"No markdown content found via LlamaCloud")
            
        return "\n\n".join(text_parts)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


async def _parse_docx(content: bytes) -> str:
    """Extract text from DOCX using LlamaParse (if available) or python-docx (fallback)."""
    if HAS_LLAMAPARSE and settings.LLAMA_CLOUD_API_KEY:
        try:
            return await _parse_with_llama(content, suffix=".docx")
        except Exception as e:
            logger.warning(f"LlamaParse failed for DOCX, falling back to python-docx: {str(e)}")
            # Fallback to python-docx

    if not HAS_DOCX:
        raise DocumentParsingError(
            "DOCX support requires python-docx. Install with: pip install python-docx"
        )
    
    try:
        docx_file = io.BytesIO(content)
        doc = DocxDocument(docx_file)
        
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        if not text_parts:
            raise DocumentParsingError("No text extracted from DOCX")
        
        return "\n".join(text_parts)
    
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
    Split text into overlapping chunks (token-based estimation).
    
    Args:
        text: Full text content
        chunk_size: Target chunk size (tokens, estimated as ~4 chars per token)
        overlap: Overlap between chunks (tokens)
    
    Returns:
        List of {'content': str, 'index': int} dicts
    """
    
    # Estimate: 1 token ≈ 4 characters (conservative)
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    
    chunks = []
    sentences = text.split(". ")
    
    current_chunk = ""
    chunk_index = 0
    
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Add sentence + period
        sentence_with_punct = sentence + (". " if i < len(sentences) - 1 else "")
        
        if len(current_chunk) + len(sentence_with_punct) > char_size:
            # Save current chunk
            if current_chunk.strip():
                chunks.append({
                    "content": current_chunk.strip(),
                    "index": chunk_index,
                })
                chunk_index += 1
            
            # Start new chunk with overlap
            overlap_text = current_chunk[-char_overlap:] if len(current_chunk) > char_overlap else current_chunk
            current_chunk = overlap_text + sentence_with_punct
        else:
            current_chunk += sentence_with_punct
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "index": chunk_index,
        })
    
    return chunks if chunks else [{"content": text, "index": 0}]
