"""
Gmail agent for email operations.
Provides read, send, and search functionality for Gmail.
"""

import logging
import base64
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from src.agents.base_agent import BaseAgent
from src.auth import LazyAuthManager, get_credential_store
from src.database import get_credentials

logger = logging.getLogger(__name__)


class GmailAgent(BaseAgent):
    """
    Gmail agent for email operations.
    
    Supports modes: read, send, search
    """
    
    def __init__(self, user_id: str):
        """
        Initialize Gmail agent.
        
        Args:
            user_id: User identifier
        """
        super().__init__(user_id)
        self.service = None
        self.access_token = None
        self.refresh_token = None
    
    def _get_agent_type(self) -> str:
        """Return agent type identifier."""
        return "gmail"
    
    def authenticate(self) -> bool:
        """
        Authenticate with Gmail using lazy OAuth.
        
        Returns:
            bool: True if authentication successful
            
        Raises:
            Exception: If authentication fails
        """
        try:
            logger.info(f"Authenticating Gmail for user {self.user_id}")
            
            # Use lazy authentication - triggers OAuth if needed
            self.access_token = LazyAuthManager.ensure_gmail_auth(self.user_id)
            
            # Get refresh token from database
            creds_data = get_credentials(self.user_id, "gmail")
            if creds_data and creds_data.get('encrypted_refresh_token'):
                credential_store = get_credential_store()
                self.refresh_token = credential_store.decrypt_token(
                    creds_data['encrypted_refresh_token']
                )
            
            # Build Gmail service
            from src.config import get_settings
            settings = get_settings()
            
            credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret,
                scopes=settings.get_gmail_scopes()
            )
            
            self.service = build('gmail', 'v1', credentials=credentials)
            
            logger.info("Gmail authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            raise
    
    def validate_parameters(self, mode: str, parameters: Dict[str, Any]) -> bool:
        """
        Validate parameters for the given mode.
        
        Args:
            mode: Operation mode (read, send, search)
            parameters: Parameters to validate
            
        Returns:
            bool: True if valid
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Use registry for basic validation
        valid, error = self.registry.validate_mode_parameters(
            self.agent_type,
            mode,
            parameters
        )
        
        if not valid:
            raise ValueError(error)
        
        # Additional validation for specific modes
        if mode == "send":
            # Validate email addresses
            to = parameters.get('to')
            if not self._is_valid_email(to):
                raise ValueError(f"Invalid 'to' email address: {to}")
            
            cc = parameters.get('cc')
            if cc and not self._is_valid_email(cc):
                raise ValueError(f"Invalid 'cc' email address: {cc}")
        
        return True
    
    def execute(self, mode: str, parameters: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Gmail operation.
        
        Args:
            mode: Operation mode (read, send, search)
            parameters: Mode-specific parameters
            context: Execution context
            
        Returns:
            dict: Result data
            
        Raises:
            NotImplementedError: If mode is not supported
        """
        if mode == "read":
            return self._read_emails(parameters)
        elif mode == "send":
            return self._send_email(parameters)
        elif mode == "search":
            return self._search_emails(parameters)
        else:
            raise NotImplementedError(f"Mode '{mode}' is not implemented for Gmail agent")
    
    def _read_emails(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read emails from Gmail.
        
        Args:
            parameters: {
                'query': Optional search query,
                'max_results': Max emails to fetch (default: 10),
                'date_filter': Optional date filter (today, this_week)
            }
            
        Returns:
            dict: List of email objects with metadata
        """
        try:
            query = parameters.get('query', '')
            max_results = parameters.get('max_results', 10)
            date_filter = parameters.get('date_filter')
            
            # Build query string with date filter
            query_string = self._build_query_string(query, date_filter)
            
            logger.info(f"Reading emails with query: '{query_string}', max: {max_results}")
            
            # List messages
            self._increment_api_calls()
            results = self.service.users().messages().list(
                userId='me',
                q=query_string,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return {
                    'emails': [],
                    'count': 0,
                    'message': 'No emails found'
                }
            
            # Fetch full details for each message
            emails = []
            for msg in messages:
                try:
                    self._increment_api_calls()
                    full_msg = self.service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()
                    
                    email_data = self._parse_email_message(full_msg)
                    emails.append(email_data)
                    
                except HttpError as e:
                    logger.warning(f"Error fetching message {msg['id']}: {e}")
                    continue
            
            return {
                'emails': emails,
                'count': len(emails),
                'query': query_string,
                'total_available': results.get('resultSizeEstimate', len(emails))
            }
            
        except HttpError as e:
            return self._handle_http_error(e, "read emails")
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            raise
    
    def _send_email(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send an email via Gmail.
        
        Args:
            parameters: {
                'to': Recipient email (required),
                'subject': Email subject (required),
                'body': Email body (required),
                'cc': CC recipients (optional)
            }
            
        Returns:
            dict: Message ID and status
        """
        try:
            to = parameters['to']
            subject = parameters['subject']
            body = parameters['body']
            cc = parameters.get('cc')
            
            logger.info(f"Sending email to {to}")
            
            # Create message
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            
            if cc:
                message['cc'] = cc
            
            # Add body
            msg_body = MIMEText(body, 'plain')
            message.attach(msg_body)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode('utf-8')
            
            # Send message
            self._increment_api_calls()
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info(f"Email sent successfully: {sent_message['id']}")
            
            return {
                'message_id': sent_message['id'],
                'to': to,
                'subject': subject,
                'cc': cc,
                'status': 'sent',
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except HttpError as e:
            return self._handle_http_error(e, "send email")
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            raise
    
    def _search_emails(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search emails with Gmail query syntax.
        
        Args:
            parameters: {
                'query': Gmail search query (required),
                'max_results': Max results (optional, default: 10)
            }
            
        Returns:
            dict: Search results
        """
        try:
            query = parameters['query']
            max_results = parameters.get('max_results', 10)
            
            logger.info(f"Searching emails with query: '{query}'")
            
            # Use the query directly - supports Gmail operators
            self._increment_api_calls()
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return {
                    'emails': [],
                    'count': 0,
                    'query': query,
                    'message': 'No emails found matching query'
                }
            
            # Fetch full details
            emails = []
            for msg in messages:
                try:
                    self._increment_api_calls()
                    full_msg = self.service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()
                    
                    email_data = self._parse_email_message(full_msg)
                    emails.append(email_data)
                    
                except HttpError as e:
                    logger.warning(f"Error fetching message {msg['id']}: {e}")
                    continue
            
            return {
                'emails': emails,
                'count': len(emails),
                'query': query,
                'total_available': results.get('resultSizeEstimate', len(emails))
            }
            
        except HttpError as e:
            return self._handle_http_error(e, "search emails")
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            raise
    
    def _build_query_string(self, query: str, date_filter: Optional[str]) -> str:
        """
        Build Gmail query string with date filter.
        
        Args:
            query: Base query string
            date_filter: Date filter (today, this_week, or None)
            
        Returns:
            str: Complete query string
        """
        query_parts = []
        
        if query:
            query_parts.append(query)
        
        if date_filter:
            if date_filter.lower() == 'today':
                today = datetime.now().strftime('%Y/%m/%d')
                query_parts.append(f'after:{today}')
            
            elif date_filter.lower() == 'this_week':
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y/%m/%d')
                query_parts.append(f'after:{week_ago}')
        
        return ' '.join(query_parts) if query_parts else ''
    
    def _parse_email_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Gmail message into standardized format.
        
        Args:
            message: Raw Gmail message object
            
        Returns:
            dict: Parsed email data
        """
        headers = message['payload']['headers']
        
        # Extract headers
        subject = self._get_header(headers, 'Subject')
        from_email = self._get_header(headers, 'From')
        to_email = self._get_header(headers, 'To')
        date_str = self._get_header(headers, 'Date')
        
        # Get snippet
        snippet = message.get('snippet', '')
        
        # Parse date
        try:
            # Gmail date format varies, just store as string for now
            message_date = date_str
        except:
            message_date = None
        
        return {
            'id': message['id'],
            'thread_id': message['threadId'],
            'subject': subject,
            'from': from_email,
            'to': to_email,
            'date': message_date,
            'snippet': snippet,
            'labels': message.get('labelIds', [])
        }
    
    def _get_header(self, headers: List[Dict[str, str]], name: str) -> Optional[str]:
        """
        Get header value from message headers.
        
        Args:
            headers: List of header dictionaries
            name: Header name to find
            
        Returns:
            str: Header value or None
        """
        for header in headers:
            if header['name'].lower() == name.lower():
                return header['value']
        return None
    
    def _is_valid_email(self, email: str) -> bool:
        """
        Validate email address format.
        
        Args:
            email: Email address to validate
            
        Returns:
            bool: True if valid email format
        """
        if not email:
            return False
        
        # Simple email regex
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def _handle_http_error(self, error: HttpError, operation: str) -> Dict[str, Any]:
        """
        Handle Gmail API HTTP errors with specific error messages.
        
        Args:
            error: HTTP error from Gmail API
            operation: Operation being performed
            
        Returns:
            dict: Error details for proper handling
        """
        error_details = error.error_details if hasattr(error, 'error_details') else []
        status_code = error.resp.status if hasattr(error, 'resp') else None
        
        logger.error(f"Gmail API error during {operation}: {status_code} - {error_details}")
        
        # Handle specific error codes
        if status_code == 401:
            raise Exception("Authentication failed. Please re-authenticate.")
        
        elif status_code == 403:
            raise Exception("Insufficient permissions or quota exceeded. Check Gmail API quotas.")
        
        elif status_code == 429:
            raise Exception("Rate limit exceeded. Please wait before retrying.")
        
        elif status_code == 404:
            raise Exception(f"Resource not found during {operation}.")
        
        else:
            raise Exception(f"Gmail API error during {operation}: {str(error)}")