"""
Tests unitaires de la configuration.
Vérifie la validation des variables d'environnement.
"""

import base64
import os
import pytest
from pydantic import ValidationError


class TestConfigValidation:
    """Tests de validation de la configuration."""
    
    def test_encryption_key_must_be_32_bytes(self):
        """La clé de chiffrement doit faire exactement 32 bytes décodés."""
        from app.core.config import Settings
        
        # Clé de 31 bytes (invalide)
        invalid_key = base64.b64encode(b"a" * 31).decode()
        os.environ["ENCRYPTION_KEY"] = invalid_key
        
        with pytest.raises((ValidationError, ValueError)):
            Settings()
    
    def test_encryption_key_must_be_valid_base64(self):
        """La clé de chiffrement doit être du base64 valide."""
        from app.core.config import Settings
        
        os.environ["ENCRYPTION_KEY"] = "not_valid_base64!!!"
        
        with pytest.raises((ValidationError, ValueError)):
            Settings()
    
    def test_port_must_be_in_range(self):
        """Le port doit être entre 1024 et 65535."""
        from app.core.config import Settings
        
        with pytest.raises(ValidationError):
            Settings(PORT=80)  # Trop bas
