"""
Base agent class for all Vienna agents.
Provides common functionality and defines the agent interface.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

from src.config import get_agent_registry
from src.database import Task

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    All agents must inherit from this class and implement the required methods.
    """
    
    def __init__(self, user_id: str):
        """
        Initialize the base agent.
        
        Args:
            user_id: User identifier for authentication and data access
        """
        self.user_id = user_id
        self.agent_type = self._get_agent_type()
        self.registry = get_agent_registry()
        self.capabilities = self._load_capabilities()
        self._api_call_count = 0
        
        logger.info(f"Initialized {self.agent_type} agent for user {user_id}")
    
    @abstractmethod
    def _get_agent_type(self) -> str:
        """
        Get the agent type identifier.
        
        Returns:
            str: Agent type (gmail, github, etc.)
        """
        pass
    
    def _load_capabilities(self) -> Dict[str, Any]:
        """
        Load agent capabilities from the registry.
        
        Returns:
            dict: Agent configuration including modes and parameters
        """
        try:
            config = self.registry.get_agent_config(self.agent_type)
            return {
                'name': config.get('name'),
                'type': config.get('type'),
                'description': config.get('description'),
                'modes': list(config.get('modes', {}).keys()),
                'oauth_required': config.get('oauth_required', False),
                'scopes': config.get('scopes', [])
            }
        except Exception as e:
            logger.error(f"Error loading capabilities for {self.agent_type}: {e}")
            raise
    
    @abstractmethod
    def execute(self, mode: str, parameters: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an agent operation.
        
        Args:
            mode: Operation mode (read, send, list_repos, etc.)
            parameters: Mode-specific parameters
            context: Execution context with results from previous tasks
            
        Returns:
            dict: Standardized result dictionary
            
        Raises:
            ValueError: If mode or parameters are invalid
            NotImplementedError: If mode is not implemented
        """
        pass
    
    @abstractmethod
    def validate_parameters(self, mode: str, parameters: Dict[str, Any]) -> bool:
        """
        Validate that parameters are correct for the given mode.
        
        Args:
            mode: Operation mode
            parameters: Parameters to validate
            
        Returns:
            bool: True if valid
            
        Raises:
            ValueError: If parameters are invalid with descriptive message
        """
        pass
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Ensure agent is authenticated.
        
        Should check if credentials exist, trigger OAuth if needed,
        and refresh tokens if expired.
        
        Returns:
            bool: True if authentication successful
            
        Raises:
            Exception: If authentication fails
        """
        pass
    
    def execute_task(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task with full error handling and formatting.
        
        Args:
            task: Task object to execute
            context: Execution context
            
        Returns:
            dict: Formatted result with status, data, metadata, and error
        """
        start_time = time.time()
        self._api_call_count = 0
        
        try:
            # Validate agent type matches
            if task.agent_type != self.agent_type:
                raise ValueError(
                    f"Task agent type '{task.agent_type}' does not match "
                    f"agent type '{self.agent_type}'"
                )
            
            # Authenticate if required
            if self.capabilities.get('oauth_required'):
                logger.info(f"Authenticating {self.agent_type} agent...")
                self.authenticate()
            
            # Validate parameters
            self.validate_parameters(task.mode, task.parameters)
            
            # Execute the task
            logger.info(f"Executing {self.agent_type}.{task.mode} for user {self.user_id}")
            raw_result = self.execute(task.mode, task.parameters, context)
            
            # Format successful output
            execution_time = time.time() - start_time
            return self.format_output(
                raw_result,
                execution_time=execution_time,
                api_calls=self._api_call_count
            )
            
        except Exception as e:
            # Handle errors
            execution_time = time.time() - start_time
            logger.error(f"Error executing task {task.id}: {e}")
            return self.handle_error(
                e,
                execution_time=execution_time,
                api_calls=self._api_call_count
            )
    
    def format_output(
        self,
        raw_data: Dict[str, Any],
        execution_time: float,
        api_calls: int
    ) -> Dict[str, Any]:
        """
        Standardize output format.
        
        Args:
            raw_data: Raw result data from execution
            execution_time: Time taken to execute in seconds
            api_calls: Number of API calls made
            
        Returns:
            dict: Standardized output format
        """
        return {
            "status": "success",
            "data": raw_data,
            "metadata": {
                "execution_time": round(execution_time, 3),
                "api_calls": api_calls,
                "timestamp": datetime.utcnow().isoformat(),
                "agent_type": self.agent_type,
                "user_id": self.user_id
            },
            "error": None
        }
    
    def handle_error(
        self,
        error: Exception,
        execution_time: float,
        api_calls: int
    ) -> Dict[str, Any]:
        """
        Handle and format errors.
        
        Args:
            error: The exception that occurred
            execution_time: Time taken before error in seconds
            api_calls: Number of API calls made before error
            
        Returns:
            dict: Standardized error response
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Log the error
        logger.error(
            f"{self.agent_type} agent error: {error_type}: {error_message}",
            exc_info=True
        )
        
        # Determine if error is retryable
        retryable = self._is_retryable_error(error)
        
        return {
            "status": "error",
            "data": None,
            "metadata": {
                "execution_time": round(execution_time, 3),
                "api_calls": api_calls,
                "timestamp": datetime.utcnow().isoformat(),
                "agent_type": self.agent_type,
                "user_id": self.user_id,
                "retryable": retryable
            },
            "error": {
                "type": error_type,
                "message": error_message
            }
        }
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Args:
            error: The exception to check
            
        Returns:
            bool: True if error is retryable
        """
        # Network errors, timeouts, and rate limits are typically retryable
        retryable_types = (
            'ConnectionError',
            'TimeoutError',
            'HTTPError',
            'RateLimitError',
            'ServerError'
        )
        
        error_type = type(error).__name__
        
        # Check error type
        if error_type in retryable_types:
            return True
        
        # Check error message for retryable indicators
        error_message = str(error).lower()
        retryable_keywords = ['timeout', 'rate limit', 'temporarily', 'try again']
        
        return any(keyword in error_message for keyword in retryable_keywords)
    
    def _increment_api_calls(self) -> None:
        """Increment the API call counter."""
        self._api_call_count += 1
    
    def get_supported_modes(self) -> list[str]:
        """
        Get list of supported modes for this agent.
        
        Returns:
            list: List of mode names
        """
        return self.capabilities.get('modes', [])
    
    def get_mode_description(self, mode: str) -> str:
        """
        Get description for a specific mode.
        
        Args:
            mode: Mode name
            
        Returns:
            str: Mode description
        """
        return self.registry.get_mode_description(self.agent_type, mode)
    
    def get_required_parameters(self, mode: str) -> list[str]:
        """
        Get required parameters for a mode.
        
        Args:
            mode: Mode name
            
        Returns:
            list: List of required parameter names
        """
        return self.registry.get_required_parameters(self.agent_type, mode)
    
    def __repr__(self) -> str:
        """String representation of the agent."""
        return f"{self.__class__.__name__}(user_id='{self.user_id}', type='{self.agent_type}')"