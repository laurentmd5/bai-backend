"""
Tests unitaires pour le parseur de documents (document_parser.py).
Verifie l'extraction de texte (TXT, MD, PDF, DOCX) et le chunking RAG.
"""

import pytest
from app.services.admin.document_parser import (
    parse_document_content,
    split_text_into_chunks,
    DocumentParsingError,
)


class TestDocumentParser:
    """Tests d'extraction et de découpage de documents."""

    @pytest.mark.asyncio
    async def test_parse_plain_text_utf8(self):
        """Extraction de texte brut UTF-8."""
        raw = "NETSYSTEME INFORMATIQUE fournit des services IT de haute qualité.".encode("utf-8")
        text = await parse_document_content(raw, "text/plain", "service.txt")
        assert "NETSYSTEME" in text
        assert "haute qualité" in text

    @pytest.mark.asyncio
    async def test_parse_markdown(self):
        """Extraction de document Markdown."""
        raw = "# NETSYSTEME\n\n## 1. Réseaux\n- Wi-Fi 6\n- IP/MPLS".encode("utf-8")
        text = await parse_document_content(raw, "text/markdown", "reseaux.md")
        assert "NETSYSTEME" in text
        assert "Wi-Fi 6" in text

    @pytest.mark.asyncio
    async def test_parse_empty_document_raises(self):
        """Un document vide lève DocumentParsingError."""
        with pytest.raises(DocumentParsingError):
            await parse_document_content(b"", "text/plain", "empty.txt")

    @pytest.mark.asyncio
    async def test_parse_unsupported_format_raises(self):
        """Un format non reconnu lève DocumentParsingError."""
        with pytest.raises(DocumentParsingError):
            await parse_document_content(b"\x00\x01\x02\x03", "application/octet-stream", "binary.bin")

    def test_split_text_into_chunks(self):
        """Découpage du texte en chunks avec chevauchement."""
        sample_text = (
            "NETSYSTEME est une entreprise informatique basée à Dakar au Sénégal. "
            "Elle propose des services d'énergie solaire, vidéosurveillance, réseaux et téléphonie IP. "
            "Nos ingénieurs certifiés interviennent en moins de 30 minutes pour les incidents critiques. "
        ) * 5

        chunks = split_text_into_chunks(sample_text, chunk_size=50, overlap=10)
        assert len(chunks) >= 1
        assert "content" in chunks[0]
        assert "index" in chunks[0]
        assert len(chunks[0]["content"]) > 0

    def test_split_short_text_single_chunk(self):
        """Un texte court produit un chunk unique."""
        short_text = "Court texte de test."
        chunks = split_text_into_chunks(short_text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0]["content"] == short_text
