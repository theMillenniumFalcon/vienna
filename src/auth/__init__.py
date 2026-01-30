"""Authentication module for Vienna AI Agent Orchestration System."""

from .credential_store import (
    CredentialStore,
    get_credential_store,
    encrypt_token,
    decrypt_token,
)

from .oauth_manager import (
    GmailOAuthManager,
    GitHubOAuthManager,
    LazyAuthManager,
)

__all__ = [
    # Credential Store
    "CredentialStore",
    "get_credential_store",
    "encrypt_token",
    "decrypt_token",
    # OAuth Managers
    "GmailOAuthManager",
    "GitHubOAuthManager",
    "LazyAuthManager",
]