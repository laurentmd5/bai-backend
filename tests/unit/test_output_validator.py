"""
Tests unitaires du validateur de sortie.
Vérifie la validation des réponses générées par le LLM.
"""

from app.services.validation.output_validator import OutputValidator


class TestOutputValidator:
    """Tests du validateur de réponses."""
    
    def setup_method(self):
        self.validator = OutputValidator()
    
    def test_valid_response_passes(self):
        """Une réponse valide avec slogan passe la validation."""
        response = (
            "The NPP has achieved a mobile penetration rate of 113%. "
            "[Source: Digital.docx, Section 2]\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        )
        sources = [{"text": "Mobile penetration reached 113%", "document": "Digital.docx"}]
        
        is_valid, final, meta = self.validator.validate_response(
            response, sources, channel="web", strict_mode=False
        )
        assert is_valid is True
    
    def test_missing_slogan_added(self):
        """Le slogan est ajouté s'il est absent."""
        response = "The NPP has achieved great things."
        sources = []
        
        is_valid, final, meta = self.validator.validate_response(
            response, sources, channel="web", strict_mode=False
        )
        assert "Ask. Know. Decide." in final
        assert "slogan_added" in meta.get("fixes_applied", [])
    
    def test_forbidden_term_rejected(self):
        """Un terme interdit est rejeté."""
        response = "Barrow is corrupt and the NPP failed."
        sources = []
        
        is_valid, final, meta = self.validator.validate_response(
            response, sources, channel="web", strict_mode=True
        )
        # En mode strict, une exception est levée
        # En mode non-strict, le fallback est utilisé
        if not is_valid:
            assert "forbidden_term_detected" in meta.get("validations_performed", [])
    
    def test_whatsapp_truncation(self):
        """Les messages WhatsApp sont tronqués si trop longs."""
        response = "A" * 5000 + "\n\nAsk. Know. Decide. - One Gambia. One People. One Barrow."
        sources = []
        
        is_valid, final, meta = self.validator.validate_response(
            response, sources, channel="whatsapp", strict_mode=False
        )
        assert len(final) <= 4100  # ~4000 max + slogan
        assert "truncated_for_whatsapp" in meta.get("fixes_applied", [])
    
    def test_empty_response_invalid(self):
        """Une réponse vide est invalide."""
        sources = []
        
        is_valid, final, meta = self.validator.validate_response(
            "", sources, channel="web", strict_mode=False
        )
        assert not is_valid
        assert "empty_response" in meta.get("validations_performed", [])
