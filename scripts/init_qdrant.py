#!/usr/bin/env python3
"""
Initialize Qdrant collection with all NPP documents from the data directory.
Run once during first deployment.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag_service import RAGService
from app.services.processing.document_processor import DocumentProcessor
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
            page_text = page.extract_text()
            if page_text:
                text += page_text
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


import argparse

async def index_all_documents(force: bool = False, check_only: bool = False):
    """
    Index all documents in the /app/data directory using DocumentProcessor.
    Idempotent: skips already indexed documents unless force=True.
    """
    logger.info("Initializing RAG service and verifying Qdrant status...", force=force)
    
    rag = RAGService()
    await rag.initialize()
    
    # 1. Check existing collection stats
    try:
        stats = await rag.get_collection_stats()
        points_count = stats.get("points_count", 0)
        existing_docs = set(stats.get("documents", []))
    except Exception as e:
        logger.warning("could_not_fetch_stats", error=str(e))
        points_count = 0
        existing_docs = set()
    
    logger.info("qdrant_current_state", points_count=points_count, unique_documents=len(existing_docs))
    
    if check_only:
        print(f"Qdrant points: {points_count}, Documents: {len(existing_docs)}")
        return
        
    data_dir = Path("/app/data")
    if not data_dir.exists():
        # Fallback to local data dir if running outside docker container
        data_dir = Path(__file__).resolve().parent.parent / "data"
        
    if not data_dir.exists():
        logger.warning("data_directory_not_found", path=str(data_dir))
        return
    
    # Find all document files (including subdirectories like data/knowledge)
    extensions = [".docx", ".pdf", ".txt", ".md"]
    candidate_files = []
    for ext in extensions:
        candidate_files.extend(data_dir.glob(f"*{ext}"))
        candidate_files.extend(data_dir.glob(f"**/*{ext}"))
    
    # Deduplicate resolved paths
    documents = list({p.resolve(): p for p in candidate_files}.values())
    
    if not documents:
        logger.info("no_data_documents_found", directory=str(data_dir))
        return
    
    # 2. Check if all documents are already indexed
    if not force and points_count > 0:
        missing_docs = [doc for doc in documents if doc.name not in existing_docs]
        if not missing_docs:
            logger.info(
                "qdrant_already_initialized",
                points_count=points_count,
                documents_count=len(existing_docs),
                msg="All documents are already indexed in Qdrant. Initialization skipped (0s)."
            )
            return
        else:
            logger.info(
                "qdrant_incremental_indexing",
                total_files=len(documents),
                already_indexed=len(existing_docs),
                to_index=len(missing_docs),
                new_files=[d.name for d in missing_docs],
            )
            documents = missing_docs
            
    logger.info("indexing_start", count=len(documents), directory=str(data_dir))
    
    # Initialize document processor for intelligent chunking
    processor = DocumentProcessor(
        chunk_size=512,
        chunk_overlap=50,
        supported_extensions=[".docx", ".pdf", ".txt", ".md"]
    )
    
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
            
            # Create document and split into chunks using DocumentProcessor
            logger.info("processing_document", name=doc_path.name, content_length=len(content))
            
            doc = processor._create_document(content, str(doc_path))
            chunks = processor.chunk_document(doc)
            chunk_texts = [chunk.page_content for chunk in chunks]
            
            logger.info("indexing_document", name=doc_path.name, chunks=len(chunk_texts))
            
            indexed = await rag.index_document_chunks(
                chunks=chunk_texts,
                document_name=doc_path.name,
                section=doc_path.stem[:50],
                language="fr",
            )
            total_chunks += indexed
            logger.info("document_indexed", name=doc_path.name, chunks=indexed)
            
        except Exception as e:
            logger.error("document_index_failed", name=doc_path.name, error=str(e))
    
    # Show collection stats
    try:
        final_stats = await rag._vector_store.get_collection_info()
        logger.info("indexing_complete", total_chunks_added=total_chunks, points_count=final_stats.get("points_count", 0))
    except Exception as e:
        logger.info("indexing_complete", total_chunks_added=total_chunks)


def main():
    parser = argparse.ArgumentParser(description="Initialize or update Qdrant RAG vector store")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of all documents even if already indexed")
    parser.add_argument("--check-only", action="store_true", help="Only check and print current Qdrant index status")
    args = parser.parse_args()
    
    asyncio.run(index_all_documents(force=args.force, check_only=args.check_only))


if __name__ == "__main__":
    main()