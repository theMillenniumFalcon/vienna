"""
OAuth manager for handling authentication flows.
Implements OAuth 2.0 flows for Gmail and GitHub services.
"""

import logging
import webbrowser
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import httpx

from src.config import get_settings
from src.database import store_credentials, get_credentials
from .credential_store import get_credential_store

logger = logging.getLogger(__name__)


# OAuth callback handler
class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callbacks."""
    
    authorization_code: Optional[str] = None
    oauth_error: Optional[str] = None
    
    def do_GET(self):
        """Handle GET request from OAuth callback."""
        # Parse the query parameters
        parsed_path = urlparse(self.path)
        params = parse_qs(parsed_path.query)
        
        # Check for authorization code
        if 'code' in params:
            OAuthCallbackHandler.authorization_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                    <script>window.close();</script>
                </body>
                </html>
            """)
        elif 'error' in params:
            OAuthCallbackHandler.oauth_error = params['error'][0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {params['error'][0]}</p>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """.encode())
        
        # Suppress log messages
        def log_message(self, format, *args):
            pass
        
        OAuthCallbackHandler.log_message = log_message


class GmailOAuthManager:
    """Manages Gmail OAuth 2.0 authentication flow."""
    
    @staticmethod
    def initiate_gmail_oauth() -> Dict[str, Any]:
        """
        Initiate Gmail OAuth flow.
        
        Returns:
            dict: Contains 'access_token' and 'refresh_token'
            
        Raises:
            Exception: If OAuth flow fails
        """
        settings = get_settings()
        
        logger.info("Initiating Gmail OAuth flow...")
        print("\n🔐 Gmail authentication required. Opening browser...")
        
        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.gmail_redirect_uri]
                }
            },
            scopes=settings.get_gmail_scopes()
        )
        
        flow.redirect_uri = settings.gmail_redirect_uri
        
        # Generate authorization URL
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Reset callback handler
        OAuthCallbackHandler.authorization_code = None
        OAuthCallbackHandler.oauth_error = None
        
        # Start local server
        server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()
        
        # Open browser
        print(f"📱 Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}\n")
        webbrowser.open(auth_url)
        
        # Wait for callback
        print("⏳ Waiting for authorization...")
        server_thread.join(timeout=300)  # 5 minute timeout
        
        if OAuthCallbackHandler.oauth_error:
            raise Exception(f"OAuth error: {OAuthCallbackHandler.oauth_error}")
        
        if not OAuthCallbackHandler.authorization_code:
            raise Exception("Authorization code not received. OAuth flow timed out.")
        
        # Exchange code for tokens
        print("✓ Authorization received. Exchanging for tokens...")
        flow.fetch_token(code=OAuthCallbackHandler.authorization_code)
        
        credentials = flow.credentials
        
        logger.info("Gmail OAuth completed successfully")
        print("✓ Gmail authentication successful!\n")
        
        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_expiry': credentials.expiry
        }
    
    @staticmethod
    def refresh_gmail_token(refresh_token: str) -> Dict[str, Any]:
        """
        Refresh Gmail access token using refresh token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            dict: Contains new 'access_token' and 'token_expiry'
            
        Raises:
            Exception: If token refresh fails
        """
        settings = get_settings()
        
        logger.info("Refreshing Gmail access token...")
        
        try:
            # Create credentials object
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret
            )
            
            # Refresh the token
            credentials.refresh(Request())
            
            logger.info("Gmail token refreshed successfully")
            
            return {
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token or refresh_token,
                'token_expiry': credentials.expiry
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh Gmail token: {e}")
            raise Exception(f"Token refresh failed: {e}")
    
    @staticmethod
    def check_gmail_auth(user_id: str) -> Dict[str, Any]:
        """
        Check Gmail authentication status for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            dict: {'authenticated': bool, 'needs_refresh': bool, 'credentials': dict or None}
        """
        try:
            # Get credentials from database
            creds = get_credentials(user_id, "gmail")
            
            if not creds:
                return {
                    'authenticated': False,
                    'needs_refresh': False,
                    'credentials': None
                }
            
            # Check if token is expired
            token_expiry = creds.get('token_expiry')
            needs_refresh = False
            
            if token_expiry:
                # Add 5 minute buffer
                if datetime.utcnow() + timedelta(minutes=5) >= token_expiry:
                    needs_refresh = True
            
            return {
                'authenticated': True,
                'needs_refresh': needs_refresh,
                'credentials': creds
            }
            
        except Exception as e:
            logger.error(f"Error checking Gmail auth: {e}")
            return {
                'authenticated': False,
                'needs_refresh': False,
                'credentials': None
            }


class GitHubOAuthManager:
    """Manages GitHub OAuth 2.0 authentication flow."""
    
    @staticmethod
    def initiate_github_oauth() -> Dict[str, str]:
        """
        Initiate GitHub OAuth flow.
        
        Returns:
            dict: Contains 'access_token'
            
        Raises:
            Exception: If OAuth flow fails
        """
        settings = get_settings()
        
        logger.info("Initiating GitHub OAuth flow...")
        print("\n🔐 GitHub authentication required. Opening browser...")
        
        # Build authorization URL
        scopes = settings.get_github_scopes()
        scope_string = " ".join(scopes)
        
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.github_client_id}"
            f"&redirect_uri={settings.github_redirect_uri}"
            f"&scope={scope_string}"
        )
        
        # Reset callback handler
        OAuthCallbackHandler.authorization_code = None
        OAuthCallbackHandler.oauth_error = None
        
        # Start local server
        server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()
        
        # Open browser
        print(f"📱 Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}\n")
        webbrowser.open(auth_url)
        
        # Wait for callback
        print("⏳ Waiting for authorization...")
        server_thread.join(timeout=300)  # 5 minute timeout
        
        if OAuthCallbackHandler.oauth_error:
            raise Exception(f"OAuth error: {OAuthCallbackHandler.oauth_error}")
        
        if not OAuthCallbackHandler.authorization_code:
            raise Exception("Authorization code not received. OAuth flow timed out.")
        
        # Exchange code for access token
        print("✓ Authorization received. Exchanging for token...")
        
        token_url = "https://github.com/login/oauth/access_token"
        
        response = httpx.post(
            token_url,
            data={
                'client_id': settings.github_client_id,
                'client_secret': settings.github_client_secret,
                'code': OAuthCallbackHandler.authorization_code,
                'redirect_uri': settings.github_redirect_uri
            },
            headers={'Accept': 'application/json'}
        )
        
        response.raise_for_status()
        token_data = response.json()
        
        if 'error' in token_data:
            raise Exception(f"Token exchange error: {token_data['error_description']}")
        
        access_token = token_data['access_token']
        
        logger.info("GitHub OAuth completed successfully")
        print("✓ GitHub authentication successful!\n")
        
        return {'access_token': access_token}
    
    @staticmethod
    def validate_github_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Validate GitHub token and get user info.
        
        Args:
            token: GitHub access token
            
        Returns:
            dict: User info if valid, None otherwise
        """
        try:
            response = httpx.get(
                'https://api.github.com/user',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"GitHub token validation failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error validating GitHub token: {e}")
            return None
    
    @staticmethod
    def check_github_auth(user_id: str) -> Dict[str, Any]:
        """
        Check GitHub authentication status for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            dict: {'authenticated': bool, 'valid': bool, 'credentials': dict or None}
        """
        try:
            # Get credentials from database
            creds = get_credentials(user_id, "github")
            
            if not creds:
                return {
                    'authenticated': False,
                    'valid': False,
                    'credentials': None
                }
            
            # Optionally validate token
            credential_store = get_credential_store()
            access_token = credential_store.decrypt_token(creds['encrypted_token'])
            
            user_info = GitHubOAuthManager.validate_github_token(access_token)
            
            return {
                'authenticated': True,
                'valid': user_info is not None,
                'credentials': creds,
                'user_info': user_info
            }
            
        except Exception as e:
            logger.error(f"Error checking GitHub auth: {e}")
            return {
                'authenticated': False,
                'valid': False,
                'credentials': None
            }


class LazyAuthManager:
    """Manages lazy authentication - only authenticate when needed."""
    
    @staticmethod
    def ensure_gmail_auth(user_id: str) -> str:
        """
        Ensure Gmail authentication, triggering OAuth if needed.
        
        Args:
            user_id: User identifier
            
        Returns:
            str: Valid access token
            
        Raises:
            Exception: If authentication fails
        """
        credential_store = get_credential_store()
        
        # Check current auth status
        auth_status = GmailOAuthManager.check_gmail_auth(user_id)
        
        if auth_status['authenticated']:
            creds = auth_status['credentials']
            
            # Check if refresh needed
            if auth_status['needs_refresh']:
                logger.info("Gmail token expired, refreshing...")
                print("🔄 Refreshing Gmail token...")
                
                # Decrypt refresh token
                refresh_token = credential_store.decrypt_token(
                    creds['encrypted_refresh_token']
                )
                
                # Refresh tokens
                new_tokens = GmailOAuthManager.refresh_gmail_token(refresh_token)
                
                # Encrypt and store new tokens
                encrypted_access, encrypted_refresh = credential_store.encrypt_credentials(
                    new_tokens['access_token'],
                    new_tokens['refresh_token']
                )
                
                store_credentials(
                    user_id=user_id,
                    service="gmail",
                    encrypted_token=encrypted_access,
                    encrypted_refresh_token=encrypted_refresh,
                    token_expiry=new_tokens['token_expiry']
                )
                
                print("✓ Gmail token refreshed\n")
                return new_tokens['access_token']
            
            else:
                # Decrypt and return existing token
                access_token = credential_store.decrypt_token(creds['encrypted_token'])
                return access_token
        
        else:
            # Need to authenticate
            logger.info("No Gmail credentials found, initiating OAuth...")
            
            # Trigger OAuth flow
            tokens = GmailOAuthManager.initiate_gmail_oauth()
            
            # Encrypt and store tokens
            encrypted_access, encrypted_refresh = credential_store.encrypt_credentials(
                tokens['access_token'],
                tokens['refresh_token']
            )
            
            store_credentials(
                user_id=user_id,
                service="gmail",
                encrypted_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                token_expiry=tokens['token_expiry']
            )
            
            return tokens['access_token']
    
    @staticmethod
    def ensure_github_auth(user_id: str) -> str:
        """
        Ensure GitHub authentication, triggering OAuth if needed.
        
        Args:
            user_id: User identifier
            
        Returns:
            str: Valid access token
            
        Raises:
            Exception: If authentication fails
        """
        credential_store = get_credential_store()
        
        # Check current auth status
        auth_status = GitHubOAuthManager.check_github_auth(user_id)
        
        if auth_status['authenticated'] and auth_status['valid']:
            # Decrypt and return existing token
            creds = auth_status['credentials']
            access_token = credential_store.decrypt_token(creds['encrypted_token'])
            return access_token
        
        else:
            # Need to authenticate
            logger.info("No valid GitHub credentials found, initiating OAuth...")
            
            # Trigger OAuth flow
            tokens = GitHubOAuthManager.initiate_github_oauth()
            
            # Encrypt and store token
            encrypted_token = credential_store.encrypt_token(tokens['access_token'])
            
            store_credentials(
                user_id=user_id,
                service="github",
                encrypted_token=encrypted_token,
                encrypted_refresh_token=None,
                token_expiry=None  # GitHub tokens don't expire
            )
            
            return tokens['access_token']