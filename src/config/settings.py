"""
Configuration settings for Vienna AI Agent Orchestration System.
Loads environment variables and provides validated settings throughout the application.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # MongoDB Atlas Configuration
    mongodb_uri: str = Field(..., description="MongoDB Atlas connection string")
    database_name: str = Field(default="vienna", description="MongoDB database name")
    
    # Anthropic API Configuration
    anthropic_api_key: str = Field(..., description="Anthropic Claude API key")
    
    # Gmail OAuth Configuration
    gmail_client_id: str = Field(..., description="Google OAuth client ID")
    gmail_client_secret: str = Field(..., description="Google OAuth client secret")
    gmail_redirect_uri: str = Field(
        default="http://localhost:8080/oauth2callback",
        description="Gmail OAuth redirect URI"
    )
    
    # GitHub OAuth Configuration
    github_client_id: str = Field(..., description="GitHub OAuth client ID")
    github_client_secret: str = Field(..., description="GitHub OAuth client secret")
    github_redirect_uri: str = Field(
        default="http://localhost:8080/github/callback",
        description="GitHub OAuth redirect URI"
    )
    
    # Security Configuration
    encryption_key: str = Field(..., description="Fernet encryption key for tokens")
    token_salt: str = Field(..., description="Salt for token encryption")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str = Field(default="vienna.log", description="Log file path")
    
    # Application Configuration
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)
    
    @field_validator("mongodb_uri")
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        """Validate MongoDB URI format."""
        if not v.startswith("mongodb"):
            raise ValueError("MongoDB URI must start with 'mongodb://' or 'mongodb+srv://'")
        return v
    
    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Validate Anthropic API key format."""
        if not v.startswith("sk-ant-"):
            raise ValueError("Anthropic API key must start with 'sk-ant-'")
        return v
    
    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Validate that encryption key is a valid Fernet key."""
        try:
            Fernet(v.encode())
        except Exception as e:
            raise ValueError(f"Invalid Fernet encryption key: {e}")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v_upper
    
    @property
    def config_dir(self) -> Path:
        """Get the configuration directory path."""
        return self.project_root / "src" / "config"
    
    @property
    def agent_registry_path(self) -> Path:
        """Get the agent registry YAML file path."""
        return self.config_dir / "agent_registry.yaml"
    
    def get_gmail_scopes(self) -> list[str]:
        """Get Gmail OAuth scopes."""
        return [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send"
        ]
    
    def get_github_scopes(self) -> list[str]:
        """Get GitHub OAuth scopes."""
        return ["repo", "read:user"]


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the singleton Settings instance.
    
    Returns:
        Settings: The application settings instance
        
    Raises:
        ValueError: If settings cannot be loaded
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Returns:
        str: Base64-encoded Fernet key
    """
    return Fernet.generate_key().decode()