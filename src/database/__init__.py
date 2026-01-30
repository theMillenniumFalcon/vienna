"""Database module for Vienna AI Agent Orchestration System."""

from .mongodb_client import MongoDBClient, get_db_client, get_database
from .models import (
    # Collection names
    USERS_COLLECTION,
    CREDENTIALS_COLLECTION,
    SESSIONS_COLLECTION,
    TASKS_COLLECTION,
    # User operations
    get_user,
    create_user,
    update_user_login,
    # Credentials operations
    store_credentials,
    get_credentials,
    delete_credentials,
    # Session operations
    create_session,
    update_session,
    get_session,
    get_user_sessions,
    # Task operations
    create_task,
    update_task_status,
    get_task,
    get_session_tasks,
    get_tasks_by_status,
    # Index creation
    create_indexes,
)

__all__ = [
    # Client
    "MongoDBClient",
    "get_db_client",
    "get_database",
    # Collection names
    "USERS_COLLECTION",
    "CREDENTIALS_COLLECTION",
    "SESSIONS_COLLECTION",
    "TASKS_COLLECTION",
    # User operations
    "get_user",
    "create_user",
    "update_user_login",
    # Credentials operations
    "store_credentials",
    "get_credentials",
    "delete_credentials",
    # Session operations
    "create_session",
    "update_session",
    "get_session",
    "get_user_sessions",
    # Task operations
    "create_task",
    "update_task_status",
    "get_task",
    "get_session_tasks",
    "get_tasks_by_status",
    # Index creation
    "create_indexes",
]