"""Unit tests for OutputValidator deduplication logic."""

import pytest
from app.services.validation.output_validator import OutputValidator


@pytest.fixture
def validator():
    return OutputValidator()


def test_deduplicate_repeated_cycle_blocks_whatsapp_bug(validator):
    """
    Reproduces the exact WhatsApp bug observed at 14:50:
    A 2-paragraph block repeated twice consecutively.
    """
    raw_response = (
        "Pourriez-vous s'il vous plaît me fournir plus de détails sur les caméras Imou que vous recherchez, par exemple :\n"
        "- Le nombre exact de caméras ?\n"
        "- S'agit-il d'une installation intérieure ou extérieure ?\n\n"
        "Ces informations me permettront de vous proposer un devis gratuit et précis sous 48h.\n\n"
        "Pourriez-vous s'il vous plaît me fournir plus de détails sur les caméras Imou que vous recherchez, par exemple :\n"
        "- Le nombre exact de caméras ?\n"
        "- S'agit-il d'une installation intérieure ou extérieure ?\n\n"
        "Ces informations me permettront de vous proposer un devis gratuit et précis sous 48h."
    )

    is_valid, final_resp, metadata = validator.validate_response(
        response=raw_response,
        sources=[],
        channel="whatsapp",
        strict_mode=False
    )

    assert is_valid
    assert "deduplicated_repeated_blocks" in metadata["fixes_applied"]
    # The duplicate block should be removed
    assert final_resp.count("Pourriez-vous s'il vous plaît") == 1
    assert final_resp.count("sous 48h.") == 1


def test_deduplicate_identical_consecutive_paragraphs(validator):
    """Test that consecutive identical paragraphs are removed."""
    raw = (
        "Nos solutions de vidéosurveillance intelligente incluent des caméras IP 4K avec IA.\n\n"
        "Nos solutions de vidéosurveillance intelligente incluent des caméras IP 4K avec IA.\n\n"
        "Souhaitez-vous un devis gratuit sous 48h ?"
    )

    is_valid, final_resp, metadata = validator.validate_response(
        response=raw,
        sources=[],
        channel="web",
        strict_mode=False
    )

    assert is_valid
    assert "deduplicated_repeated_blocks" in metadata["fixes_applied"]
    assert final_resp.count("Nos solutions de vidéosurveillance intelligente") == 1
    assert "Souhaitez-vous un devis gratuit" in final_resp


def test_deduplicate_consecutive_identical_sentences(validator):
    """Test that consecutive identical sentences inside a paragraph are deduplicated."""
    raw = (
        "Bonjour Monsieur Laurent. "
        "Nous vous remercions pour votre intérêt pour nos caméras. "
        "Nous vous remercions pour votre intérêt pour nos caméras. "
        "Un conseiller va vous contacter."
    )

    is_valid, final_resp, metadata = validator.validate_response(
        response=raw,
        sources=[],
        channel="web",
        strict_mode=False
    )

    assert is_valid
    assert "deduplicated_repeated_blocks" in metadata["fixes_applied"]
    assert final_resp.count("Nous vous remercions pour votre intérêt pour nos caméras.") == 1


def test_preserve_normal_distinct_paragraphs(validator):
    """Test that normal, distinct paragraphs are preserved without changes."""
    raw = (
        "Voici le détail de notre offre pour les caméras de surveillance IP.\n\n"
        "1. Caméra Dahua 4MP avec vision nocturne et IA embarquée.\n\n"
        "2. Enregistreur NVR 8 canaux avec disque dur 2 To inclus.\n\n"
        "Afin de finaliser votre devis, merci de nous transmettre votre email."
    )

    is_valid, final_resp, metadata = validator.validate_response(
        response=raw,
        sources=[],
        channel="whatsapp",
        strict_mode=False
    )

    assert is_valid
    assert "deduplicated_repeated_blocks" not in metadata["fixes_applied"]
    assert final_resp == raw
