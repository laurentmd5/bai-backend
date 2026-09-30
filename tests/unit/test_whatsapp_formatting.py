"""
Unit tests for WhatsApp markdown formatting conversion.
Tests transformation of standard markdown bold/strikethrough into native WhatsApp formatting.
"""

import pytest
from app.services.whatsapp_service import format_for_whatsapp


class TestWhatsAppFormatting:
    """Tests for format_for_whatsapp converter."""

    def test_converts_double_asterisks_to_single(self):
        """Standard Markdown **bold** must be converted to WhatsApp *bold*."""
        input_text = "Chez **NETSYSTEME INFORMATIQUE**, nous cherchons un **Développeur**."
        expected = "Chez *NETSYSTEME INFORMATIQUE*, nous cherchons un *Développeur*."
        assert format_for_whatsapp(input_text) == expected

    def test_converts_strikethrough(self):
        """Standard Markdown ~~strikethrough~~ must be converted to ~strikethrough~."""
        input_text = "Ceci est ~~obsolète~~ corrigé."
        expected = "Ceci est ~obsolète~ corrigé."
        assert format_for_whatsapp(input_text) == expected

    def test_cleans_mismatched_asterisks(self):
        """Mismatched asterisks like **email* or *phone** must be cleaned to *email* and *phone*."""
        input_text = "Contactez-nous à **adiarraa@gmail.com* ou au *+221 33 827 28 45**."
        expected = "Contactez-nous à *adiarraa@gmail.com* ou au *+221 33 827 28 45*."
        assert format_for_whatsapp(input_text) == expected

    def test_handles_empty_or_none(self):
        """Empty or None input must return safely."""
        assert format_for_whatsapp("") == ""
        assert format_for_whatsapp(None) is None
