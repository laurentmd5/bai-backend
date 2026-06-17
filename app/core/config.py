"""
Core configuration module for BARROW.AI backend.
Uses Pydantic Settings for robust environment variable management.
All sensitive values are loaded from environment variables only.
"""

from typing import List, Optional, Union
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum


class Environment(str, Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OLLAMA = "ollama"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """
    Central configuration settings for BARROW.AI.
    All values are loaded from environment variables with validation.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True
    )

    # =========================================================================
    # APPLICATION SETTINGS
    # =========================================================================
    APP_NAME: str = Field(
        default="BARROW.AI POC",
        description="Application name for logging and headers"
    )
    
    APP_VERSION: str = Field(
        default="4.0.0",
        description="Semantic version of the application"
    )
    
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Current runtime environment"
    )
    
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode (disable in production)"
    )
    
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="API version 1 URL prefix"
    )
    
    # =========================================================================
    # SERVER SETTINGS
    # =========================================================================
    HOST: str = Field(
        default="0.0.0.0",
        description="Server host binding"
    )
    
    PORT: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Server port binding"
    )
    
    WORKERS: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Number of Uvicorn worker processes"
    )
    
    # =========================================================================
    # CORS SETTINGS
    # =========================================================================
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "https://widget.barrow-ai.poc",
            "https://admin.barrow-ai.poc",
            "https://npp.gm",
            "http://localhost:5173",
            "http://localhost:3000",
        ],
        description="Allowed CORS origins"
    )
    
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    
    CORS_ALLOW_METHODS: List[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS"
    )
    
    CORS_ALLOW_HEADERS: List[str] = Field(
        default_factory=lambda: [
            "Content-Type",
            "Authorization",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        description="Allowed HTTP headers for CORS"
    )
    
    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from string or list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(',') if origin.strip()]
        return value
    
    @field_validator('ENCRYPTION_KEY', mode='after')
    @classmethod
    def validate_encryption_key(cls, value: SecretStr) -> SecretStr:
        """
        BUG #4 FIX: Validate that encryption key is exactly 32 bytes after base64 decoding.
        Fails at startup rather than mid-request.
        """
        import base64
        
        key_str = value.get_secret_value()
        
        try:
            key_bytes = base64.b64decode(key_str)
        except Exception as e:
            raise ValueError(f"ENCRYPTION_KEY must be valid base64: {e}")
        
        if len(key_bytes) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY must be 32 bytes when decoded, got {len(key_bytes)} bytes. "
                f"Generate with: openssl rand -base64 32"
            )
        
        return value
    
    # =========================================================================
    # DATABASE SETTINGS
    # =========================================================================
    POSTGRES_USER: str = Field(
        default="barrowai",
        description="PostgreSQL username"
    )
    
    POSTGRES_PASSWORD: SecretStr = Field(
        ...,
        description="PostgreSQL password"
    )
    
    POSTGRES_HOST: str = Field(
        default="postgres",
        description="PostgreSQL host"
    )
    
    POSTGRES_PORT: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL port"
    )
    
    POSTGRES_DB: str = Field(
        default="barrowai_poc",
        description="PostgreSQL database name"
    )
    
    DATABASE_POOL_SIZE: int = Field(
        default=20,
        ge=5,
        le=100,
        description="SQLAlchemy connection pool size"
    )
    
    DATABASE_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
        le=50,
        description="SQLAlchemy max overflow connections"
    )
    
    DATABASE_ECHO: bool = Field(
        default=False,
        description="Echo SQL queries (debug only)"
    )
    
    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        password = self.POSTGRES_PASSWORD.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def sync_database_url(self) -> str:
        """Construct sync PostgreSQL connection URL for Alembic."""
        password = self.POSTGRES_PASSWORD.get_secret_value()
        return (
            f"postgresql://{self.POSTGRES_USER}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # =========================================================================
    # REDIS SETTINGS
    # =========================================================================
    REDIS_HOST: str = Field(
        default="redis",
        description="Redis host"
    )
    
    REDIS_PORT: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Redis port"
    )
    
    REDIS_PASSWORD: SecretStr = Field(
        ...,
        description="Redis password"
    )
    
    REDIS_DB: int = Field(
        default=0,
        ge=0,
        le=15,
        description="Redis database number"
    )
    
    REDIS_MAX_CONNECTIONS: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Redis connection pool size"
    )
    
    REDIS_SOCKET_TIMEOUT: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Redis socket timeout in seconds"
    )
    
    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        password = self.REDIS_PASSWORD.get_secret_value()
        return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # =========================================================================
    # RABBITMQ SETTINGS
    # =========================================================================
    RABBITMQ_HOST: str = Field(
        default="rabbitmq",
        description="RabbitMQ host"
    )
    
    RABBITMQ_PORT: int = Field(
        default=5672,
        ge=1,
        le=65535,
        description="RabbitMQ port"
    )
    
    RABBITMQ_USER: str = Field(
        default="barrowai",
        description="RabbitMQ username"
    )
    
    RABBITMQ_PASSWORD: SecretStr = Field(
        ...,
        description="RabbitMQ password"
    )
    
    RABBITMQ_WEBHOOK_QUEUE: str = Field(
        default="whatsapp_webhooks",
        description="Queue name for WhatsApp webhooks"
    )

    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ connection URL."""
        password = self.RABBITMQ_PASSWORD.get_secret_value()
        return f"amqp://{self.RABBITMQ_USER}:{password}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
    
    # =========================================================================
    # QDRANT SETTINGS
    # =========================================================================
    QDRANT_HOST: str = Field(
        default="qdrant",
        description="Qdrant host"
    )
    
    QDRANT_PORT: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Qdrant port"
    )
    
    QDRANT_COLLECTION: str = Field(
        default="npp_documents_poc_v2",
        description="Qdrant collection name"
    )
    
    QDRANT_VECTOR_SIZE: int = Field(
        default=1024,
        description="Embedding vector dimension"
    )
    
    QDRANT_SIMILARITY_THRESHOLD: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for RAG retrieval"
    )
    
    QDRANT_TOP_K: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Number of chunks to retrieve per query"
    )
    
    @property
    def qdrant_url(self) -> str:
        """Construct Qdrant connection URL."""
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"
    
    # =========================================================================
    # LLM SETTINGS
    # =========================================================================
    LLM_PROVIDER: LLMProvider = Field(
        default=LLMProvider.GEMINI,
        description="LLM provider to use"
    )
    
    GEMINI_API_KEY: SecretStr = Field(
        ...,
        description="Google Gemini API key"
    )
    
    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash-lite",
    )
    
    GEMINI_EMBED_MODEL: str = Field(
        default="models/text-embedding-004",
        description="Gemini embedding model"
    )
    
    GEMINI_TEMPERATURE: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature (lower = more deterministic)"
    )
    
    GEMINI_MAX_TOKENS: int = Field(
        default=512,
        ge=50,
        le=8192,
        description="Maximum output tokens"
    )
    
    GEMINI_TIMEOUT: int = Field(
        default=15,
        ge=5,
        le=60,
        description="API timeout in seconds"
    )
    
    GEMINI_MAX_RETRIES: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Maximum retry attempts for API calls"
    )
    
    # Ollama settings (for Phase 2)
    OLLAMA_HOST: str = Field(
        default="ollama",
        description="Ollama host"
    )
    
    OLLAMA_PORT: int = Field(
        default=11434,
        ge=1,
        le=65535,
        description="Ollama port"
    )
    
    OLLAMA_MODEL: str = Field(
        default="llama3.2:3b",
        description="Ollama model name"
    )
    
    @property
    def ollama_url(self) -> str:
        """Construct Ollama connection URL."""
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    
    # =========================================================================
    # HUGGING FACE & OOLEL SETTINGS
    # =========================================================================
    HF_TOKEN: Optional[SecretStr] = Field(
        default=None,
        description="Hugging Face Inference API key"
    )
    
    GROQ_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Groq API Key for Llama 3.3 fallback"
    )
    
    LLAMA_CLOUD_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="LlamaParse Cloud API Key"
    )
    
    WHISPER_MODEL_SIZE: str = Field(
        default="large-v3-turbo",
        description="Faster-Whisper model size for local STT"
    )
    
    OOLEL_TTS_SPACE_ID: str = Field(
        default="SoynadeResearch/oolel-voices",
        description="Gradio Space ID for Oolel TTS (Deprecated)"
    )
    
    OOLEL_API_URL: str = Field(
        default="http://100.110.197.46:8080",
        description="Local Oolel TTS VM API URL"
    )
    
    OOLEL_CORRECTOR_ENDPOINT: str = Field(
        default="https://router.huggingface.co/hf-inference/models/soynade-research/oolel-corrector-1.5b",
        description="Endpoint for Oolel Wolof Orthography Corrector"
    )
    
    OOLEL_TTS_TIMEOUT: int = Field(
        default=90,
        description="Timeout for Oolel TTS API in seconds"
    )
    
    # =========================================================================
    # SECURITY SETTINGS
    # =========================================================================
    JWT_SECRET: SecretStr = Field(
        ...,
        description="JWT signing secret (access tokens)"
    )
    
    JWT_REFRESH_SECRET: SecretStr = Field(
        ...,
        description="JWT signing secret (refresh tokens)"
    )
    
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=5,
        le=60,
        description="Access token expiration in minutes"
    )
    
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Refresh token expiration in days"
    )
    
    ENCRYPTION_KEY: SecretStr = Field(
        ...,
        description="AES-256 encryption key (32 bytes base64 encoded)"
    )
    
    CSRF_SECRET: SecretStr = Field(
        ...,
        description="CSRF token secret"
    )
    
    BCRYPT_ROUNDS: int = Field(
        default=12,
        ge=10,
        le=14,
        description="Bcrypt hashing rounds"
    )
    
    # =========================================================================
    # RATE LIMITING SETTINGS
    # =========================================================================
    RATE_LIMIT_CHAT_PER_MINUTE: int = Field(
        default=30,
        ge=10,
        le=100,
        description="Chat endpoint rate limit per minute"
    )
    
    RATE_LIMIT_ADMIN_PER_MINUTE: int = Field(
        default=60,
        ge=20,
        le=200,
        description="Admin endpoint rate limit per minute"
    )
    
    RATE_LIMIT_WHATSAPP_PER_MINUTE: int = Field(
        default=10,
        ge=5,
        le=30,
        description="WhatsApp endpoint rate limit per minute"
    )
    
    RATE_LIMIT_BURST_MULTIPLIER: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Burst multiplier for rate limiting"
    )
    
    # =========================================================================
    # WHATSAPP SETTINGS
    # =========================================================================
    WHATSAPP_VERIFY_TOKEN: SecretStr = Field(
        ...,
        description="WhatsApp webhook verify token"
    )
    
    WHATSAPP_ACCESS_TOKEN: SecretStr = Field(
        ...,
        description="WhatsApp Cloud API access token"
    )
    
    WHATSAPP_PHONE_NUMBER_ID: str = Field(
        ...,
        description="WhatsApp phone number ID"
    )
    
    WHATSAPP_API_VERSION: str = Field(
        default="v20.0",
        description="WhatsApp API version"
    )
    
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = Field(
        default="",
        description="WhatsApp business account ID"
    )
    
    WHATSAPP_APP_SECRET: SecretStr = Field(
        ...,
        description="WhatsApp App Secret (from Meta Developer Console, NOT the verify token)"
    )
    
    # =========================================================================
    # RAG CHUNKING SETTINGS
    # =========================================================================
    RAG_CHUNK_SIZE: int = Field(
        default=400,
        ge=100,
        le=1000,
        description="Chunk size in tokens for text splitting"
    )
    
    RAG_CHUNK_OVERLAP: int = Field(
        default=80,
        ge=0,
        le=200,
        description="Chunk overlap in tokens"
    )
    
    # =========================================================================
    # LOGGING SETTINGS
    # =========================================================================
    LOG_LEVEL: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level"
    )
    
    LOG_FORMAT: str = Field(
        default="json",
        pattern="^(json|text)$",
        description="Log format (json or text)"
    )
    
    LOG_FILE: str = Field(
        default="/app/logs/app.log",
        description="Log file path"
    )
    
    # =========================================================================
    # ADMIN SETTINGS
    # =========================================================================
    ADMIN_IP_WHITELIST: List[str] = Field(
        default_factory=lambda: [
            "127.0.0.1",
            "::1",
            # SECURITY FIX #3: Restrictive whitelist instead of entire Docker network
            # Only allow specific admin dashboard container IP or VPN addresses
            # Add your PACE office VPN IPs here: "203.xxx.xxx.xxx"
        ],
        description="IP addresses allowed to access admin endpoints (RESTRICTED for security)"
    )
    
    ADMIN_MAX_FAILED_ATTEMPTS: int = Field(
        default=5,
        ge=3,
        le=10,
        description="Max failed login attempts before lockout"
    )
    
    ADMIN_LOCKOUT_MINUTES: int = Field(
        default=30,
        ge=15,
        le=120,
        description="Account lockout duration in minutes"
    )
    
    # =========================================================================
    # CACHE SETTINGS
    # =========================================================================
    CACHE_RAG_TTL_SECONDS: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="RAG cache TTL in seconds"
    )
    
    CACHE_EMBEDDING_TTL_SECONDS: int = Field(
        default=14400,
        ge=3600,
        le=86400,
        description="Embedding cache TTL in seconds"
    )
    
    CACHE_SESSION_TTL_SECONDS: int = Field(
        default=86400,
        ge=3600,
        le=604800,
        description="Session cache TTL in seconds"
    )
    
    # =========================================================================
    # MONITORING SETTINGS
    # =========================================================================
    SENTRY_DSN: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error tracking"
    )
    
    PROMETHEUS_ENABLED: bool = Field(
        default=True,
        description="Enable Prometheus metrics endpoint"
    )
    
    HEALTH_CHECK_INTERVAL: int = Field(
        default=30,
        ge=10,
        le=300,
        description="Health check interval in seconds"
    )
    
    # =========================================================================
    # AUDIO SETTINGS (voice messages)
    # =========================================================================
    WHISPER_MODEL_SIZE: str = Field(
        default="base",
        description="Whisper model size: tiny, base, small, medium"
    )
    
    MAX_AUDIO_DURATION_SECONDS: int = Field(
        default=180,
        ge=10,
        le=300,
        description="Maximum allowed audio duration in seconds"
    )
    
    AUDIO_CACHE_TTL_SECONDS: int = Field(
        default=86400,
        ge=3600,
        le=604800,
        description="Cache TTL for transcribed audio in seconds"
    )
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    @property
    def jwt_secret_key(self) -> str:
        """Get JWT secret as string."""
        return self.JWT_SECRET.get_secret_value()
    
    @property
    def jwt_refresh_secret_key(self) -> str:
        """Get JWT refresh secret as string."""
        return self.JWT_REFRESH_SECRET.get_secret_value()
    
    @property
    def encryption_key_bytes(self) -> bytes:
        """Get encryption key as bytes (32 bytes for AES-256)."""
        import base64
        key_str = self.ENCRYPTION_KEY.get_secret_value()
        return base64.b64decode(key_str)
    
    @property
    def gemini_api_key_str(self) -> str:
        """Get Gemini API key as string."""
        return self.GEMINI_API_KEY.get_secret_value()


# Global settings instance
settings = Settings()