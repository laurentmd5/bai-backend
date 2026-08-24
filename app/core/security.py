"""
Security module for Company Bot backend.
Provides JWT handling, password hashing, AES encryption, 2FA, CSRF protection,
and input validation utilities.
"""

import hashlib
import hmac
import secrets
import base64
import re
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta, timezone

from jose import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationException,
    ValidationException,
    HostileContentException,
    PromptInjectionException,
)


# =============================================================================
# PASSWORD HASHING (Argon2id)
# =============================================================================

# Argon2id configuration for maximum security
# Parameters chosen for server environment with 2-4 vCPU
_ph = PasswordHasher(
    time_cost=3,        # Number of iterations
    memory_cost=65536,  # 64 MB memory usage
    parallelism=2,      # 2 threads
    hash_len=32,        # 32 byte output
    salt_len=16,        # 16 byte salt
)


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id algorithm.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Argon2id password hash
    """
    if not password or len(password) < 8:
        raise ValidationException("Password must be at least 8 characters")
    
    return _ph.hash(password)


def verify_password(hash_value: str, password: str) -> bool:
    """
    Verify a password against its Argon2id hash.
    
    Args:
        hash_value: Stored password hash
        password: Plain text password to verify
        
    Returns:
        bool: True if password matches, False otherwise
    """
    if not hash_value or not password:
        return False
    
    try:
        return _ph.verify(hash_value, password)
    except (VerificationError, InvalidHashError):
        return False


def check_password_needs_rehash(hash_value: str) -> bool:
    """
    Check if a password hash needs to be rehashed with current parameters.
    
    Args:
        hash_value: Stored password hash
        
    Returns:
        bool: True if rehash is recommended
    """
    try:
        return _ph.check_needs_rehash(hash_value)
    except InvalidHashError:
        return True


# Legacy bcrypt support for smooth migration
_bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password_legacy(hash_value: str, password: str) -> bool:
    """Verify password with bcrypt (for migration period)."""
    try:
        return _bcrypt_context.verify(password, hash_value)
    except Exception:
        return False


# =============================================================================
# JWT TOKEN HANDLING
# =============================================================================


def create_jwt_token(
    data: Dict[str, Any],
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT token with proper claims.
    
    Args:
        data: Payload data to encode
        token_type: "access" or "refresh"
        expires_delta: Custom expiration delta
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    # Set expiration
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        if token_type == "access":
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )
    
    # Add standard claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "type": token_type,
        "jti": secrets.token_hex(16),  # Unique token ID for revocation
        "iss": settings.APP_NAME,
    })
    
    # Select appropriate secret
    secret = (
        settings.jwt_secret_key
        if token_type == "access"
        else settings.jwt_refresh_secret_key
    )
    
    return jwt.encode(
        to_encode,
        secret,
        algorithm=settings.JWT_ALGORITHM
    )


def decode_jwt_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Dict[str, Any]: Decoded payload
        
    Raises:
        AuthenticationException: If token is invalid, expired, or wrong type
    """
    secret = (
        settings.jwt_secret_key
        if token_type == "access"
        else settings.jwt_refresh_secret_key
    )
    
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["exp", "iat", "type", "jti"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
            }
        )
        
        # Verify token type
        if payload.get("type") != token_type:
            raise AuthenticationException(
                f"Invalid token type: expected {token_type}"
            )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationException("Token has expired")
    except jwt.JWTError as e:
        raise AuthenticationException(f"Invalid token: {str(e)}")


def create_token_pair(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create both access and refresh token pair.
    
    Args:
        user_data: User information to include in tokens
        
    Returns:
        Dict containing access_token, refresh_token, and metadata
    """
    # Create access token
    access_token = create_jwt_token(user_data, "access")
    
    # Create refresh token
    refresh_token = create_jwt_token(user_data, "refresh")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """
    Create a new access token using a valid refresh token.
    
    Args:
        refresh_token: Valid refresh token
        
    Returns:
        Dict containing new access token
    """
    payload = decode_jwt_token(refresh_token, "refresh")
    
    # Extract user data (remove JWT-specific claims)
    user_data = {
        k: v for k, v in payload.items()
        if k not in ["exp", "iat", "nbf", "type", "jti", "iss"]
    }
    
    # Create new access token
    access_token = create_jwt_token(user_data, "access")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# =============================================================================
# TWO-FACTOR AUTHENTICATION (TOTP)
# =============================================================================


def generate_totp_secret() -> str:
    """
    Generate a cryptographically secure TOTP secret.
    
    Returns:
        str: Base32 encoded TOTP secret
    """
    return pyotp.random_base32()


def generate_totp_uri(secret: str, email: str) -> str:
    """
    Generate a provisioning URI for Google Authenticator / Authy.
    
    Args:
        secret: Base32 TOTP secret
        email: User's email address
        
    Returns:
        str: otpauth:// URI for QR code generation
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name="Company Bot Admin"
    )


def verify_totp(secret: str, token: str) -> bool:
    """
    Verify a TOTP token.
    
    Args:
        secret: Base32 TOTP secret
        token: 6-digit token from authenticator app
        
    Returns:
        bool: True if token is valid
    """
    if not secret or not token:
        return False
    
    try:
        totp = pyotp.TOTP(secret)
        # valid_window=1 allows ±30 seconds of clock drift
        return totp.verify(token, valid_window=1)
    except Exception:
        return False


def generate_backup_codes(count: int = 8) -> List[str]:
    """
    Generate backup recovery codes for 2FA.
    
    Args:
        count: Number of backup codes to generate
        
    Returns:
        List[str]: List of backup codes (plain text, show once)
    """
    return [secrets.token_hex(4).upper() for _ in range(count)]


def hash_backup_code(code: str) -> str:
    """
    Hash a backup code for secure storage.
    
    Args:
        code: Plain text backup code
        
    Returns:
        str: SHA-256 hash of the code
    """
    return hashlib.sha256(code.encode()).hexdigest()


def verify_backup_code(stored_hashes: List[str], provided_code: str) -> Tuple[bool, Optional[str]]:
    """
    Verify a backup code against stored hashes.
    
    Args:
        stored_hashes: List of hashed backup codes
        provided_code: Plain text code to verify
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, matched_hash)
    """
    provided_hash = hash_backup_code(provided_code)
    
    for stored_hash in stored_hashes:
        if hmac.compare_digest(provided_hash, stored_hash):
            return True, stored_hash
    
    return False, None


# =============================================================================
# AES-256-GCM ENCRYPTION
# =============================================================================


class AESGCMEncryption:
    """
    AES-256-GCM encryption for sensitive data.
    Provides authenticated encryption with 96-bit nonces.
    """
    
    def __init__(self, key: bytes):
        """
        Initialize with 32-byte encryption key.
        
        Args:
            key: 32-byte key for AES-256
        """
        if len(key) != 32:
            raise ValueError("AES-256 requires a 32-byte key")
        self.key = key
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext using AES-256-GCM.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            str: Base64 encoded ciphertext (nonce + tag + ciphertext)
        """
        # Generate 96-bit random nonce
        nonce = secrets.token_bytes(12)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Encrypt
        ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
        
        # Get authentication tag (16 bytes)
        tag = encryptor.tag
        
        # Combine: nonce (12) + tag (16) + ciphertext
        combined = nonce + tag + ciphertext
        
        return base64.b64encode(combined).decode('utf-8')
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt ciphertext using AES-256-GCM.
        
        Args:
            encrypted_data: Base64 encoded ciphertext
            
        Returns:
            str: Decrypted plaintext
            
        Raises:
            ValueError: If decryption fails (invalid data or tampered)
        """
        try:
            combined = base64.b64decode(encrypted_data)
            
            # Extract components
            nonce = combined[:12]
            tag = combined[12:28]
            ciphertext = combined[28:]
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext.decode('utf-8')
            
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")


# Global encryption instance
_aes_gcm = AESGCMEncryption(settings.encryption_key_bytes)


def encrypt_field(value: str) -> str:
    """Encrypt a sensitive field for database storage."""
    if not value:
        return value
    return _aes_gcm.encrypt(value)


def decrypt_field(encrypted_value: str) -> str:
    """Decrypt a sensitive field from database storage."""
    if not encrypted_value:
        return encrypted_value
    try:
        return _aes_gcm.decrypt(encrypted_value)
    except ValueError:
        # Handle legacy unencrypted data
        return encrypted_value


# =============================================================================
# CSRF PROTECTION
# =============================================================================


def generate_csrf_token(session_id: str) -> str:
    """
    Generate a CSRF token bound to a session.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        str: HMAC-based CSRF token
    """
    message = f"{session_id}{settings.CSRF_SECRET.get_secret_value()}"
    return hmac.new(
        settings.CSRF_SECRET.get_secret_value().encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_csrf_token(token: str, session_id: str) -> bool:
    """
    Verify a CSRF token using constant-time comparison.
    
    Args:
        token: CSRF token from request header
        session_id: Session identifier
        
    Returns:
        bool: True if token is valid
    """
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(token, expected)


# =============================================================================
# INPUT VALIDATION AND SANITIZATION
# =============================================================================


# Compiled regex patterns for performance
_SQL_INJECTION_PATTERN = re.compile(
    r"(\bUNION\b.*\bSELECT\b)|(\bDROP\b.*\bTABLE\b)|(\bINSERT\b.*\bINTO\b)|"
    r"(\bDELETE\b.*\bFROM\b)|(\bUPDATE\b.*\bSET\b)|(--)|(;)|"
    r"(\bOR\b.*=.*\bOR\b)|('\s*OR\s*')|(\bEXEC\b)|(\bEXECUTE\b)",
    re.IGNORECASE
)

_XSS_PATTERN = re.compile(
    r"<script|javascript:|on\w+\s*=|<\s*img[^>]+src|<\s*iframe|<\s*embed|<\s*object|"
    r"<\s*meta|<\s*link|<\s*style|expression\s*\(",
    re.IGNORECASE
)

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)(ignore|forget|disregard)\s+(previous|above|all)\s+(instructions?|prompts?)"),
    re.compile(r"(?i)(you are now|act as|pretend you are|roleplay as)"),
    re.compile(r"(?i)(system\s*prompt|developer\s*mode|jailbreak)"),
    re.compile(r"(?i)(bypass|override|ignore)\s+(restrictions?|rules?|guidelines?)"),
    re.compile(r"(?i)(new\s+instructions?|updated\s+prompt)"),
]

_HOSTILE_KEYWORDS = [
    "corrupt", "incompetent", "failure", "liar", "dictator",
    "steal", "rigged", "fake", "useless", "worst", "terrible",
    "awful", "disaster", "shame", "embarrassment"
]

_HOSTILE_PATTERNS = [
    re.compile(r"(?i)(barrow|president|npp)\s+is\s+({})".format("|".join(_HOSTILE_KEYWORDS))),
    re.compile(r"(?i)(why is barrow|why does barrow)\s+(so bad|a failure|corrupt)"),
    re.compile(r"(?i)(opposition|udp|pdois|gdc)\s+(is better|will win|should win)"),
]


def sanitize_input(text: str) -> str:
    """
    Sanitize user input for safe processing.
    
    Args:
        text: Raw user input
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Trim whitespace
    text = text.strip()
    
    # Remove control characters (except newline and tab)
    text = ''.join(
        char for char in text
        if ord(char) >= 32 or char in ('\n', '\t')
    )
    
    return text


def html_escape(text: str) -> str:
    """
    Escape HTML special characters.
    
    Args:
        text: Text to escape
        
    Returns:
        str: HTML-escaped text
    """
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
            .replace("/", "&#x2F;")
    )


def detect_sql_injection(text: str) -> bool:
    """
    Detect SQL injection patterns in user input.
    
    Args:
        text: User input to check
        
    Returns:
        bool: True if SQL injection patterns detected
    """
    return bool(_SQL_INJECTION_PATTERN.search(text))


def detect_xss(text: str) -> bool:
    """
    Detect XSS patterns in user input.
    
    Args:
        text: User input to check
        
    Returns:
        bool: True if XSS patterns detected
    """
    return bool(_XSS_PATTERN.search(text))


def detect_prompt_injection(text: str) -> bool:
    """
    Detect prompt injection attempts.
    
    Args:
        text: User input to check
        
    Returns:
        bool: True if prompt injection patterns detected
    """
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def detect_hostile_content(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect hostile or inappropriate content.
    
    Args:
        text: User input to check
        
    Returns:
        Tuple[bool, Optional[str]]: (is_hostile, matched_pattern)
    """
    text_lower = text.lower()
    
    # Check for hostile patterns
    for pattern in _HOSTILE_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group()
    
    # Check for isolated hostile keywords near Barrow/NPP references
        if has_barrow_ref:
        for keyword in _HOSTILE_KEYWORDS:
            if keyword in text_lower:
                return True, keyword
    
    return False, None


def validate_chat_message(message: str) -> Tuple[bool, Optional[str], str]:
    """
    Comprehensive validation of chat messages.
    
    Args:
        message: Raw user message
        
    Returns:
        Tuple[bool, Optional[str], str]: (is_valid, error_code, sanitized_message)
        
    Raises:
        ValidationException: For validation errors
        HostileContentException: For hostile content
        PromptInjectionException: For injection attempts
    """
    # Check if empty
    if not message or not message.strip():
        raise ValidationException("Message cannot be empty")
    
    # Check length
    if len(message) > 2000:
        raise ValidationException(
            f"Message too long: {len(message)} characters (max 2000)"
        )
    
    # Sanitize input
    sanitized = sanitize_input(message)
    sanitized = html_escape(sanitized)
    
    # Check for XSS (critical - reject)
    if detect_xss(message):
        raise ValidationException("Invalid message content")
    
    # Check for prompt injection (critical - reject)
    if detect_prompt_injection(message):
        raise PromptInjectionException()
    
    # Check for hostile content (critical - reject)
    is_hostile, matched = detect_hostile_content(message)
    if is_hostile:
        raise HostileContentException()
    
    # Check for SQL injection (warning only - might be legitimate question)
    if detect_sql_injection(message):
        import structlog
        logger = structlog.get_logger()
        logger.warning(
            "potential_sql_injection_detected",
            message_preview=message[:100]
        )
    
    return True, None, sanitized


def validate_email(email: str) -> bool:
    """
    Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        bool: True if valid email format
    """
    pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    return bool(pattern.match(email))


def validate_phone_number(phone: str) -> bool:
    """
    Validate phone number in E.164 format.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        bool: True if valid E.164 format
    """
    pattern = re.compile(r"^\+[1-9]\d{1,14}$")
    return bool(pattern.match(phone))


def validate_uuid(uuid_string: str) -> bool:
    """
    Validate UUID v4 format.
    
    Args:
        uuid_string: String to validate
        
    Returns:
        bool: True if valid UUID v4
    """
    pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE
    )
    return bool(pattern.match(uuid_string))


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.
    
    Args:
        length: Token length in bytes (output will be 2x length in hex)
        
    Returns:
        str: Hex-encoded secure random token
    """
    return secrets.token_hex(length)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks.
    
    Args:
        a: First string
        b: Second string
        
    Returns:
        bool: True if strings are equal
    """
    return hmac.compare_digest(a.encode(), b.encode())


def validate_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password strength against security requirements.
    
    Requirements:
    - At least 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Not a common password
    - No excessive repeated characters
    - No sequential character patterns
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    
    if len(password) < 12:
        issues.append("Password must be at least 12 characters long")
    
    if not re.search(r"[A-Z]", password):
        issues.append("Password must contain at least one uppercase letter")
    
    if not re.search(r"[a-z]", password):
        issues.append("Password must contain at least one lowercase letter")
    
    if not re.search(r"\d", password):
        issues.append("Password must contain at least one digit")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        issues.append("Password must contain at least one special character")
    
    # Check common passwords
    common_passwords = [
        "password", "password123", "admin123", , ,
        "12345678", "qwerty123", , 
    ]
    
    if password.lower() in common_passwords:
        issues.append("Password is too common or easily guessable")
    
    # Check for repeated characters
    if re.search(r"(.)\1{3,}", password):
        issues.append("Password contains too many repeated characters")
    
    # Check for sequential characters
    sequential_patterns = [
        "abcdefgh", "12345678", "qwertyui", "asdfghjk"
    ]
    for pattern in sequential_patterns:
        if pattern in password.lower():
            issues.append("Password contains sequential characters")
            break
    
    return len(issues) == 0, issues


