"""
Context manager for task execution.
Manages execution state, task results, and context data.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ExecutionContext:
    """
    Manages execution context for a task execution session.
    
    Stores task results and provides access to them for dependent tasks.
    """
    
    def __init__(self, session_id: str, user_id: str, user_input: str):
        """
        Initialize execution context.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            user_input: Original user input
        """
        self.session_id = session_id
        self.user_id = user_id
        self.user_input = user_input
        self.task_results: Dict[str, Dict[str, Any]] = {}
        self.start_time = datetime.utcnow()
        
        logger.info(f"Created execution context for session {session_id}")
    
    def store_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """
        Store task execution result.
        
        Args:
            task_id: Task identifier
            result: Task execution result
        """
        self.task_results[task_id] = result
        logger.debug(f"Stored result for task {task_id}")
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task execution result.
        
        Args:
            task_id: Task identifier
            
        Returns:
            dict: Task result or None if not found
        """
        return self.task_results.get(task_id)
    
    def get_all_results(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all task results.
        
        Returns:
            dict: All task results (task_id -> result)
        """
        return self.task_results.copy()
    
    def get_execution_time(self) -> float:
        """
        Get total execution time in seconds.
        
        Returns:
            float: Execution time in seconds
        """
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    def get_successful_tasks(self) -> list[str]:
        """
        Get list of successful task IDs.
        
        Returns:
            list: Task IDs that succeeded
        """
        return [
            task_id for task_id, result in self.task_results.items()
            if result.get('status') == 'success'
        ]
    
    def get_failed_tasks(self) -> list[str]:
        """
        Get list of failed task IDs.
        
        Returns:
            list: Task IDs that failed
        """
        return [
            task_id for task_id, result in self.task_results.items()
            if result.get('status') == 'error'
        ]
    
    def has_failures(self) -> bool:
        """
        Check if any tasks failed.
        
        Returns:
            bool: True if any tasks failed
        """
        return len(self.get_failed_tasks()) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get execution summary.
        
        Returns:
            dict: Execution summary with stats
        """
        total_tasks = len(self.task_results)
        successful = len(self.get_successful_tasks())
        failed = len(self.get_failed_tasks())
        
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'user_input': self.user_input,
            'total_tasks': total_tasks,
            'successful_tasks': successful,
            'failed_tasks': failed,
            'execution_time': self.get_execution_time(),
            'start_time': self.start_time.isoformat()
        }