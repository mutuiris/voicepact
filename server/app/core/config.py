"""
VoicePact Application Configuration

Production-ready configuration management using pydantic-settings v2.0+
with environment-specific settings, validation, and security best practices.
"""

import secrets
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with environment variable support, validation, and security.
    
    All settings are loaded from environment variables with type validation.
    Sensitive values use SecretStr to prevent accidental exposure.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid"
    )

    # Application Settings
    
    app_name: str = Field(
        default="VoicePact",
        description="Application name for logging and API documentation"
    )
    
    app_version: str = Field(
        default="1.0.0",
        description="Application version"
    )
    
    environment: str = Field(
        default="development",
        description="Application environment: development, testing, production"
    )
    
    debug: bool = Field(
        default=True,
        description="Enable debug mode"
    )
    
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="API v1 route prefix"
    )

    # Security Configuration

    secret_key: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        description="Secret key for JWT tokens and general encryption"
    )
    
    access_token_expire_minutes: int = Field(
        default=60 * 24 * 7,
        description="JWT access token expiration time in minutes"
    )
    
    signature_private_key: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(64)),
        description="Private key for cryptographic contract signatures"
    )
    
    password_salt: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        description="Salt for password hashing"
    )

    # Africa's Talking API Configuration

    at_username: str = Field(
        default="sandbox",
        description="Africa's Talking username"
    )
    
    at_api_key: SecretStr = Field(
        description="Africa's Talking API key"
    )
    
    at_voice_number: str = Field(
        default="+254XXXXXXXXX",
        description="Africa's Talking voice number for outbound calls"
    )
    
    at_payment_product_name: str = Field(
        default="VoicePact",
        description="Product name"
    )
    
    at_ussd_service_code: str = Field(
        default="*483#",
        description="USSD service code for VoicePact"
    )

    # Database Configuration
    
    database_url: str = Field(
        default="sqlite:///./voicepact.db",
        description="SQLite database URL with WAL mode for concurrent access"
    )
    
    database_echo: bool = Field(
        default=False,
        description="Enable SQLAlchemy query logging"
    )
    
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for caching and session management"
    )
    
    redis_max_connections: int = Field(
        default=20,
        description="Maximum Redis connection pool size"
    )
    
    redis_socket_timeout: int = Field(
        default=30,
        description="Redis socket timeout in seconds"
    )

    # Voice Processing Configuration

    whisper_model_size: str = Field(
        default="small",
        description="OpenAI Whisper model size: tiny, base, small, medium, large"
    )
    
    max_audio_duration: int = Field(
        default=1200,
        description="Maximum audio file duration in seconds"
    )
    
    max_audio_file_size: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum audio file size in bytes"
    )
    
    supported_audio_formats: List[str] = Field(
        default=["wav", "mp3", "m4a", "ogg", "flac"],
        description="Supported audio file formats"
    )

    # API Client Configuration

    http_timeout: int = Field(
        default=30,
        description="HTTP client timeout in seconds"
    )
    
    http_max_connections: int = Field(
        default=100,
        description="Maximum HTTP connection pool size"
    )
    
    http_max_keepalive: int = Field(
        default=20,
        description="Maximum HTTP keep-alive connections"
    )

    # Webhook Configuration

    webhook_base_url: Optional[str] = Field(
        default=None,
        description="Base URL for webhooks"
    )
    
    webhook_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        description="Secret for webhook signature validation"
    )

    # Performance Configuration

    cache_ttl: int = Field(
        default=3600,
        description="Default cache TTL in seconds"
    )
    
    max_workers: int = Field(
        default=4,
        description="Maximum number of background workers"
    )
    
    request_timeout: int = Field(
        default=30,
        description="Request timeout in seconds"
    )

    # CORS Configuration
    
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins"
    )
    
    cors_credentials: bool = Field(
        default=True,
        description="Allow CORS credentials"
    )
    
    cors_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed CORS methods"
    )
    
    cors_headers: List[str] = Field(
        default=["*"],
        description="Allowed CORS headers"
    )

    # Logging Configuration
    
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format"
    )
    
    log_file: Optional[str] = Field(
        default=None,
        description="Log file path (None for console only)"
    )

    # Contract Configuration

    contract_hash_algorithm: str = Field(
        default="blake2b",
        description="Hashing algorithm for contract integrity: blake2b, sha256"
    )
    
    contract_signature_algorithm: str = Field(
        default="ed25519",
        description="Digital signature algorithm: ed25519, rsa"
    )
    
    max_contract_duration: int = Field(
        default=365 * 24 * 60 * 60,
        description="Maximum contract duration in seconds"
    )
    
    contract_confirmation_timeout: int = Field(
        default=24 * 60 * 60,
        description="Contract confirmation timeout in seconds"
    )

    # Payment Configuration

    escrow_timeout: int = Field(
        default=7 * 24 * 60 * 60,
        description="Escrow timeout in seconds"
    )
    
    payment_retry_attempts: int = Field(
        default=3,
        description="Maximum payment retry attempts"
    )
    
    payment_retry_delay: int = Field(
        default=300,
        description="Payment retry delay in seconds"
    )
    
    min_payment_amount: int = Field(
        default=100,
        description="Minimum payment amount in cents"
    )
    
    max_payment_amount: int = Field(
        default=1000000,
        description="Maximum payment amount in cents"
    )

    # Validation Methods
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
    
    @field_validator("supported_audio_formats", mode="before")
    @classmethod
    def parse_audio_formats(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse supported audio formats from comma-separated string or list."""
        if isinstance(value, str):
            return [fmt.strip().lower() for fmt in value.split(",") if fmt.strip()]
        return [fmt.lower() for fmt in value]
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Validate environment is one of the allowed values."""
        allowed_environments = ["development", "testing", "production"]
        if value.lower() not in allowed_environments:
            raise ValueError(f"Environment must be one of: {allowed_environments}")
        return value.lower()
    
    @field_validator("whisper_model_size")
    @classmethod
    def validate_whisper_model(cls, value: str) -> str:
        """Validate Whisper model size."""
        allowed_models = ["tiny", "base", "small", "medium", "large"]
        if value.lower() not in allowed_models:
            raise ValueError(f"Whisper model must be one of: {allowed_models}")
        return value.lower()
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validate log level."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if value.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {allowed_levels}")
        return value.upper()
    
    @model_validator(mode="after")
    def validate_payment_amounts(self) -> "Settings":
        """Validate payment amount constraints."""
        if self.min_payment_amount >= self.max_payment_amount:
            raise ValueError("min_payment_amount must be less than max_payment_amount")
        return self
    
    @model_validator(mode="after")
    def validate_timeouts(self) -> "Settings":
        """Validate timeout configurations."""
        if self.http_timeout <= 0:
            raise ValueError("http_timeout must be positive")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        if self.cache_ttl <= 0:
            raise ValueError("cache_ttl must be positive")
        return self

    # Computed Properties

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    @property
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == "testing"
    
    @property
    def database_url_with_wal(self) -> str:
        """Get SQLite database URL with WAL mode for concurrent access."""
        if self.database_url.startswith("sqlite:"):
            # Add WAL mode and other optimizations for SQLite
            return f"{self.database_url}?mode=rwc&cache=shared&_journal_mode=WAL&_synchronous=NORMAL&_temp_store=MEMORY"
        return self.database_url
    
    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        """Get FastAPI application kwargs based on environment."""
        kwargs = {
            "title": self.app_name,
            "version": self.app_version,
            "debug": self.debug,
        }
        if self.is_production:
            kwargs.update({
                "docs_url": None,
                "redoc_url": None,
                "openapi_url": None,
            })
        
        return kwargs
    
    def get_webhook_url(self, endpoint: str) -> Optional[str]:
        """Generate full webhook URL for given endpoint."""
        if not self.webhook_base_url:
            return None
        base_url = self.webhook_base_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base_url}/{endpoint}"
    
    def get_secret_value(self, secret_field: str) -> str:
        """Safely get secret value by field name."""
        field_value = getattr(self, secret_field)
        if hasattr(field_value, "get_secret_value"):
            return field_value.get_secret_value()
        return str(field_value)


@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache application settings.
    
    Using @lru_cache ensures settings are loaded once and reused,
    improving performance by avoiding repeated environment variable reads.
    
    Returns:
        Settings: Cached application settings instance
    """
    return Settings()


settings = get_settings()