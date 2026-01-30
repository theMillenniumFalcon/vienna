"""
Database models and operations for Vienna AI Agent Orchestration System.
Defines collection schemas and provides CRUD operations.
Also includes Pydantic models for task execution.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4

from pymongo.errors import DuplicateKeyError, PyMongoError
from pydantic import BaseModel, Field

from .mongodb_client import get_database


logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models for Task Execution
# ============================================================================

class Task(BaseModel):
    """
    Represents a single task to be executed by an agent.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_type: str = Field(..., description="Type of agent (gmail, github)")
    mode: str = Field(..., description="Agent mode (read, send, list_repos, etc.)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Mode parameters")
    dependencies: List[str] = Field(default_factory=list, description="List of task IDs this task depends on")
    required_inputs: Dict[str, str] = Field(default_factory=dict, description="Required inputs from other tasks")
    status: str = Field(default="pending", description="Task status: pending, running, completed, failed")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Task execution result")
    error: Optional[str] = Field(default=None, description="Error message if task failed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "task_123",
                "agent_type": "gmail",
                "mode": "read",
                "parameters": {"max_results": 10},
                "dependencies": [],
                "required_inputs": {},
                "status": "pending",
                "result": None,
                "error": None
            }
        }


class ExecutionPlan(BaseModel):
    """
    Represents a plan for executing multiple tasks.
    """
    tasks: List[Task] = Field(..., description="List of tasks to execute")
    execution_type: str = Field(..., description="Execution type: parallel or sequential")
    task_graph: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Dependency graph: task_id -> list of dependent task IDs"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "tasks": [
                    {
                        "id": "task_1",
                        "agent_type": "gmail",
                        "mode": "read",
                        "parameters": {"max_results": 5},
                        "dependencies": [],
                        "status": "pending"
                    },
                    {
                        "id": "task_2",
                        "agent_type": "github",
                        "mode": "list_repos",
                        "parameters": {"limit": 10},
                        "dependencies": [],
                        "status": "pending"
                    }
                ],
                "execution_type": "parallel",
                "task_graph": {}
            }
        }
    
    def get_execution_order(self) -> List[List[str]]:
        """
        Get the order in which tasks should be executed based on dependencies.
        
        Returns:
            List of task ID lists, where each inner list can be executed in parallel
        """
        # Build dependency map
        dependencies = {task.id: set(task.dependencies) for task in self.tasks}
        completed = set()
        execution_order = []
        
        while len(completed) < len(self.tasks):
            # Find tasks with no pending dependencies
            ready_tasks = [
                task.id for task in self.tasks
                if task.id not in completed and dependencies[task.id].issubset(completed)
            ]
            
            if not ready_tasks:
                # Circular dependency detected
                raise ValueError("Circular dependency detected in task graph")
            
            execution_order.append(ready_tasks)
            completed.update(ready_tasks)
        
        return execution_order


# Collection names
USERS_COLLECTION = "users"
CREDENTIALS_COLLECTION = "credentials"
SESSIONS_COLLECTION = "sessions"
TASKS_COLLECTION = "tasks"


# ============================================================================
# User Operations
# ============================================================================

def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve user document by user_id.
    
    Args:
        user_id: Unique user identifier
        
    Returns:
        User document or None if not found
    """
    try:
        db = get_database()
        user = db[USERS_COLLECTION].find_one({"user_id": user_id})
        if user:
            user['_id'] = str(user['_id'])  # Convert ObjectId to string
        return user
    except PyMongoError as e:
        logger.error(f"Error retrieving user {user_id}: {e}")
        return None


def create_user(user_id: str, email: str, preferences: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Create a new user document.
    
    Args:
        user_id: Unique user identifier
        email: User email address
        preferences: Optional user preferences
        
    Returns:
        Created user document or None if creation failed
    """
    try:
        db = get_database()
        
        default_preferences = {
            "default_email_limit": 10,
            "default_repo_limit": 10
        }
        
        if preferences:
            default_preferences.update(preferences)
        
        user_doc = {
            "user_id": user_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow(),
            "preferences": default_preferences
        }
        
        result = db[USERS_COLLECTION].insert_one(user_doc)
        user_doc['_id'] = str(result.inserted_id)
        
        logger.info(f"Created user: {user_id}")
        return user_doc
        
    except DuplicateKeyError:
        logger.warning(f"User {user_id} already exists")
        return None
    except PyMongoError as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return None


def update_user_login(user_id: str) -> bool:
    """
    Update user's last login timestamp.
    
    Args:
        user_id: User identifier
        
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        result = db[USERS_COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        return result.modified_count > 0
    except PyMongoError as e:
        logger.error(f"Error updating login for user {user_id}: {e}")
        return False


# ============================================================================
# Credentials Operations
# ============================================================================

def store_credentials(
    user_id: str,
    service: str,
    encrypted_token: str,
    encrypted_refresh_token: Optional[str] = None,
    token_expiry: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Store or update encrypted credentials for a service.
    
    Args:
        user_id: User identifier
        service: Service name (gmail, github)
        encrypted_token: Encrypted access token
        encrypted_refresh_token: Encrypted refresh token (optional)
        token_expiry: Token expiration datetime (optional)
        
    Returns:
        Stored credentials document or None if failed
    """
    try:
        db = get_database()
        
        credentials_doc = {
            "user_id": user_id,
            "service": service,
            "encrypted_token": encrypted_token,
            "encrypted_refresh_token": encrypted_refresh_token,
            "token_expiry": token_expiry,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Use upsert to update if exists, insert if not
        result = db[CREDENTIALS_COLLECTION].update_one(
            {"user_id": user_id, "service": service},
            {"$set": credentials_doc},
            upsert=True
        )
        
        logger.info(f"Stored credentials for user {user_id}, service {service}")
        return credentials_doc
        
    except PyMongoError as e:
        logger.error(f"Error storing credentials for user {user_id}, service {service}: {e}")
        return None


def get_credentials(user_id: str, service: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve encrypted credentials for a service.
    
    Args:
        user_id: User identifier
        service: Service name (gmail, github)
        
    Returns:
        Credentials document or None if not found
    """
    try:
        db = get_database()
        credentials = db[CREDENTIALS_COLLECTION].find_one({
            "user_id": user_id,
            "service": service
        })
        if credentials:
            credentials['_id'] = str(credentials['_id'])
        return credentials
    except PyMongoError as e:
        logger.error(f"Error retrieving credentials for user {user_id}, service {service}: {e}")
        return None


def delete_credentials(user_id: str, service: str) -> bool:
    """
    Delete credentials for a service.
    
    Args:
        user_id: User identifier
        service: Service name (gmail, github)
        
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        db = get_database()
        result = db[CREDENTIALS_COLLECTION].delete_one({
            "user_id": user_id,
            "service": service
        })
        logger.info(f"Deleted credentials for user {user_id}, service {service}")
        return result.deleted_count > 0
    except PyMongoError as e:
        logger.error(f"Error deleting credentials for user {user_id}, service {service}: {e}")
        return False


# ============================================================================
# Session Operations
# ============================================================================

def create_session(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Create a new session for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Created session document or None if failed
    """
    try:
        db = get_database()
        
        session_doc = {
            "session_id": str(uuid4()),
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "last_interaction": datetime.utcnow(),
            "conversation_history": []
        }
        
        result = db[SESSIONS_COLLECTION].insert_one(session_doc)
        session_doc['_id'] = str(result.inserted_id)
        
        logger.info(f"Created session {session_doc['session_id']} for user {user_id}")
        return session_doc
        
    except PyMongoError as e:
        logger.error(f"Error creating session for user {user_id}: {e}")
        return None


def update_session(
    session_id: str,
    user_input: str,
    system_response: str
) -> bool:
    """
    Add an interaction to session conversation history.
    
    Args:
        session_id: Session identifier
        user_input: User's input text
        system_response: System's response text
        
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        
        interaction = {
            "timestamp": datetime.utcnow(),
            "user_input": user_input,
            "system_response": system_response
        }
        
        result = db[SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$push": {"conversation_history": interaction},
                "$set": {"last_interaction": datetime.utcnow()}
            }
        )
        
        return result.modified_count > 0
        
    except PyMongoError as e:
        logger.error(f"Error updating session {session_id}: {e}")
        return False


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve session by session_id.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Session document or None if not found
    """
    try:
        db = get_database()
        session = db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
        if session:
            session['_id'] = str(session['_id'])
        return session
    except PyMongoError as e:
        logger.error(f"Error retrieving session {session_id}: {e}")
        return None


def get_user_sessions(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve recent sessions for a user.
    
    Args:
        user_id: User identifier
        limit: Maximum number of sessions to return
        
    Returns:
        List of session documents
    """
    try:
        db = get_database()
        sessions = list(db[SESSIONS_COLLECTION].find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit))
        
        for session in sessions:
            session['_id'] = str(session['_id'])
        
        return sessions
    except PyMongoError as e:
        logger.error(f"Error retrieving sessions for user {user_id}: {e}")
        return []


# ============================================================================
# Task Operations
# ============================================================================

def create_task(
    session_id: str,
    user_id: str,
    user_input: str,
    execution_plan: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Create a new task record.
    
    Args:
        session_id: Session identifier
        user_id: User identifier
        user_input: User's input command
        execution_plan: Planned execution details
        
    Returns:
        Created task document or None if failed
    """
    try:
        db = get_database()
        
        task_doc = {
            "task_id": str(uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "user_input": user_input,
            "execution_plan": execution_plan,
            "status": "pending",
            "results": {},
            "error": None,
            "created_at": datetime.utcnow(),
            "completed_at": None,
            "execution_time_ms": None
        }
        
        result = db[TASKS_COLLECTION].insert_one(task_doc)
        task_doc['_id'] = str(result.inserted_id)
        
        logger.info(f"Created task {task_doc['task_id']}")
        return task_doc
        
    except PyMongoError as e:
        logger.error(f"Error creating task: {e}")
        return None


def update_task_status(
    task_id: str,
    status: str,
    results: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> bool:
    """
    Update task status and results.
    
    Args:
        task_id: Task identifier
        status: New status (pending, running, completed, failed)
        results: Task results (optional)
        error: Error message if failed (optional)
        
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        
        # Get current task to calculate execution time
        task = db[TASKS_COLLECTION].find_one({"task_id": task_id})
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        update_fields = {"status": status}
        
        if results is not None:
            update_fields["results"] = results
        
        if error is not None:
            update_fields["error"] = error
        
        if status in ["completed", "failed"]:
            update_fields["completed_at"] = datetime.utcnow()
            # Calculate execution time
            if task.get("created_at"):
                execution_time = (datetime.utcnow() - task["created_at"]).total_seconds() * 1000
                update_fields["execution_time_ms"] = int(execution_time)
        
        result = db[TASKS_COLLECTION].update_one(
            {"task_id": task_id},
            {"$set": update_fields}
        )
        
        return result.modified_count > 0
        
    except PyMongoError as e:
        logger.error(f"Error updating task {task_id}: {e}")
        return False


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve task by task_id.
    
    Args:
        task_id: Task identifier
        
    Returns:
        Task document or None if not found
    """
    try:
        db = get_database()
        task = db[TASKS_COLLECTION].find_one({"task_id": task_id})
        if task:
            task['_id'] = str(task['_id'])
        return task
    except PyMongoError as e:
        logger.error(f"Error retrieving task {task_id}: {e}")
        return None


def get_session_tasks(session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all tasks for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        List of task documents
    """
    try:
        db = get_database()
        tasks = list(db[TASKS_COLLECTION].find(
            {"session_id": session_id}
        ).sort("created_at", -1))
        
        for task in tasks:
            task['_id'] = str(task['_id'])
        
        return tasks
    except PyMongoError as e:
        logger.error(f"Error retrieving tasks for session {session_id}: {e}")
        return []


def get_tasks_by_status(status: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve tasks by status.
    
    Args:
        status: Task status to filter by
        limit: Maximum number of tasks to return
        
    Returns:
        List of task documents
    """
    try:
        db = get_database()
        tasks = list(db[TASKS_COLLECTION].find(
            {"status": status}
        ).sort("created_at", -1).limit(limit))
        
        for task in tasks:
            task['_id'] = str(task['_id'])
        
        return tasks
    except PyMongoError as e:
        logger.error(f"Error retrieving tasks with status {status}: {e}")
        return []


# ============================================================================
# Index Creation
# ============================================================================

def create_indexes() -> bool:
    """
    Create all required database indexes for performance.
    
    Returns:
        True if indexes created successfully, False otherwise
    """
    try:
        db = get_database()
        
        # Users collection indexes
        db[USERS_COLLECTION].create_index("user_id", unique=True)
        logger.info("Created index: users.user_id (unique)")
        
        # Credentials collection indexes
        db[CREDENTIALS_COLLECTION].create_index(
            [("user_id", 1), ("service", 1)],
            unique=True
        )
        logger.info("Created index: credentials.user_id + service (compound, unique)")
        
        # Sessions collection indexes
        db[SESSIONS_COLLECTION].create_index("session_id", unique=True)
        logger.info("Created index: sessions.session_id (unique)")
        
        db[SESSIONS_COLLECTION].create_index("user_id")
        logger.info("Created index: sessions.user_id")
        
        # Tasks collection indexes
        db[TASKS_COLLECTION].create_index("task_id", unique=True)
        logger.info("Created index: tasks.task_id (unique)")
        
        db[TASKS_COLLECTION].create_index("session_id")
        logger.info("Created index: tasks.session_id")
        
        db[TASKS_COLLECTION].create_index("status")
        logger.info("Created index: tasks.status")
        
        logger.info("All database indexes created successfully")
        return True
        
    except PyMongoError as e:
        logger.error(f"Error creating indexes: {e}")
        return False