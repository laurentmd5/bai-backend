"""
Tests unitaires des utilitaires.
"""

from app.core.security import validate_email, validate_phone_number, validate_uuid


class TestUtils:
    """Tests des fonctions utilitaires."""
    
    def test_validate_email_standard(self):
        assert validate_email("admin@pace.gm") is True
    
    def test_validate_email_no_at(self):
        assert validate_email("adminpace.gm") is False
    
    def test_validate_email_empty(self):
        assert validate_email("") is False
    
    def test_validate_phone_gambia(self):
        assert validate_phone_number("+2201234567") is True
    
    def test_validate_uuid_v4(self):
        assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True
    
    def test_validate_uuid_random_string(self):
        assert validate_uuid("hello-world") is False
