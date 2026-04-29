#!/usr/bin/env python3
"""
Initialize Qdrant collection with all NPP documents from the data directory.
Run once during first deployment.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag_service import RAGService
from app.core.logging import get_logger

logger = get_logger(__name__)


def read_docx(filepath: Path) -> str:
    """Extract text from DOCX file."""
    try:
        import docx
        doc = docx.Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except ImportError:
        logger.error("python-docx not installed")
        return ""
    except Exception as e:
        logger.error("docx_read_error", file=str(filepath), error=str(e))
        return ""


def read_pdf(filepath: Path) -> str:
    """Extract text from PDF file."""
    try:
        import pypdf
        reader = pypdf.PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except ImportError:
        logger.error("pypdf not installed")
        return ""
    except Exception as e:
        logger.error("pdf_read_error", file=str(filepath), error=str(e))
        return ""


def read_txt(filepath: Path) -> str:
    """Read text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error("txt_read_error", file=str(filepath), error=str(e))
        return ""


async def index_all_documents():
    """Index all documents in the /app/data directory."""
    logger.info("Starting Qdrant initialization...")
    
    rag = RAGService()
    await rag.initialize()
    
    # Delete existing collection to start fresh
    try:
        await rag._vector_store.delete_collection()
        logger.info("deleted_existing_collection")
    except Exception:
        pass
    
    await rag._vector_store.create_collection()
    logger.info("created_new_collection")
    
    data_dir = Path("/app/data")
    if not data_dir.exists():
        logger.error("data_directory_not_found", path=str(data_dir))
        return
    
    # Find all document files
    extensions = [".docx", ".pdf", ".txt", ".md"]
    documents = []
    for ext in extensions:
        documents.extend(data_dir.glob(f"*{ext}"))
    
    if not documents:
        logger.warning("no_documents_found", directory=str(data_dir))
        return
    
    logger.info("indexing_start", count=len(documents), directory=str(data_dir))
    
    total_chunks = 0
    
    for doc_path in documents:
        try:
            logger.info("reading_document", name=doc_path.name)
            
            # Extract text based on extension
            if doc_path.suffix.lower() == '.docx':
                content = read_docx(doc_path)
            elif doc_path.suffix.lower() == '.pdf':
                content = read_pdf(doc_path)
            elif doc_path.suffix.lower() in ['.txt', '.md']:
                content = read_txt(doc_path)
            else:
                logger.warning("unsupported_format", name=doc_path.name)
                continue
            
            if not content or len(content) < 100:
                logger.warning("empty_or_too_short", name=doc_path.name, length=len(content))
                continue
            
            # Split into chunks by paragraphs
            chunks = [c.strip() for c in content.split("\n\n") if c.strip() and len(c.strip()) > 50]
            
            if not chunks:
                # Fallback: split by sentences
                chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
            
            logger.info("indexing_document", name=doc_path.name, chunks=len(chunks))
            
            indexed = await rag.index_document_chunks(
                chunks=chunks,
                document_name=doc_path.name,
                section=doc_path.stem,
                language="en",
            )
            total_chunks += indexed
            logger.info("document_indexed", name=doc_path.name, chunks=indexed)
            
        except Exception as e:
            logger.error("document_index_failed", name=doc_path.name, error=str(e))
    
    # Show collection stats
    stats = await rag.get_collection_stats()
    logger.info("indexing_complete", total_chunks=total_chunks, collection_stats=stats)


if __name__ == "__main__":
    asyncio.run(index_all_documents())