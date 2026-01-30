"""
Credential store for secure token management.
Provides encryption/decryption for sensitive OAuth tokens.
"""

import logging
from typing import Optional
from cryptography.fernet import Fernet

from src.config import get_settings

logger = logging.getLogger(__name__)


class CredentialStore:
    """Handles encryption and decryption of sensitive credentials."""
    
    def __init__(self):
        """Initialize the credential store with encryption key."""
        settings = get_settings()
        self._cipher = Fernet(settings.encryption_key.encode())
        self._salt = settings.token_salt.encode()
    
    def encrypt_token(self, token: str) -> str:
        """
        Encrypt a token using Fernet encryption.
        
        Args:
            token: Plain text token to encrypt
            
        Returns:
            str: Encrypted token (base64 encoded)
            
        Raises:
            ValueError: If token is empty
        """
        if not token:
            raise ValueError("Token cannot be empty")
        
        try:
            # Add salt to token for additional security
            salted_token = self._salt + token.encode()
            
            # Encrypt the salted token
            encrypted = self._cipher.encrypt(salted_token)
            
            # Return as string (base64 encoded)
            return encrypted.decode()
            
        except Exception as e:
            logger.error(f"Error encrypting token: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt a token using Fernet decryption.
        
        Args:
            encrypted_token: Encrypted token (base64 encoded string)
            
        Returns:
            str: Decrypted plain text token
            
        Raises:
            ValueError: If encrypted_token is empty or invalid
        """
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")
        
        try:
            # Decrypt the token
            decrypted = self._cipher.decrypt(encrypted_token.encode())
            
            # Remove salt and decode
            token = decrypted[len(self._salt):].decode()
            
            return token
            
        except Exception as e:
            logger.error(f"Error decrypting token: {e}")
            raise ValueError(f"Failed to decrypt token: {e}")
    
    def encrypt_credentials(
        self,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> tuple[str, Optional[str]]:
        """
        Encrypt both access token and refresh token.
        
        Args:
            access_token: Plain text access token
            refresh_token: Plain text refresh token (optional)
            
        Returns:
            tuple: (encrypted_access_token, encrypted_refresh_token)
        """
        encrypted_access = self.encrypt_token(access_token)
        encrypted_refresh = None
        
        if refresh_token:
            encrypted_refresh = self.encrypt_token(refresh_token)
        
        logger.info("Credentials encrypted successfully")
        return encrypted_access, encrypted_refresh
    
    def decrypt_credentials(
        self,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str] = None
    ) -> tuple[str, Optional[str]]:
        """
        Decrypt both access token and refresh token.
        
        Args:
            encrypted_access_token: Encrypted access token
            encrypted_refresh_token: Encrypted refresh token (optional)
            
        Returns:
            tuple: (access_token, refresh_token)
        """
        access_token = self.decrypt_token(encrypted_access_token)
        refresh_token = None
        
        if encrypted_refresh_token:
            refresh_token = self.decrypt_token(encrypted_refresh_token)
        
        logger.info("Credentials decrypted successfully")
        return access_token, refresh_token


# Singleton instance
_credential_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """
    Get the singleton CredentialStore instance.
    
    Returns:
        CredentialStore: The credential store instance
    """
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store


def encrypt_token(token: str) -> str:
    """
    Encrypt a token.
    
    Args:
        token: Plain text token
        
    Returns:
        str: Encrypted token
    """
    return get_credential_store().encrypt_token(token)


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a token.
    
    Args:
        encrypted_token: Encrypted token
        
    Returns:
        str: Decrypted token
    """
    return get_credential_store().decrypt_token(encrypted_token)