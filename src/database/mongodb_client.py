"""
MongoDB client for Vienna AI Agent Orchestration System.
Provides singleton access to MongoDB Atlas with connection pooling and health checks.
"""

import logging
from typing import Optional
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
)

from ..config import get_settings


logger = logging.getLogger(__name__)


class MongoDBClient:
    """
    Singleton MongoDB client with connection pooling and health checks.
    """
    
    _instance: Optional['MongoDBClient'] = None
    _client: Optional[MongoClient] = None
    
    def __new__(cls) -> 'MongoDBClient':
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize MongoDB client if not already initialized."""
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize MongoDB client with connection pooling."""
        try:
            settings = get_settings()
            
            # Create MongoDB client with connection pooling
            self._client = MongoClient(
                settings.mongodb_uri,
                maxPoolSize=50,  # Maximum number of connections in the pool
                minPoolSize=10,  # Minimum number of connections in the pool
                maxIdleTimeMS=30000,  # Close connections after 30 seconds of inactivity
                serverSelectionTimeoutMS=5000,  # 5 second timeout for server selection
                connectTimeoutMS=10000,  # 10 second connection timeout
                socketTimeoutMS=20000,  # 20 second socket timeout
            )
            
            # Verify connection
            self._client.admin.command('ping')
            
            logger.info(f"Successfully connected to MongoDB database: {settings.database_name}")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise ConnectionError(f"Could not connect to MongoDB: {e}")
        except Exception as e:
            logger.error(f"Unexpected error initializing MongoDB client: {e}")
            raise
    
    @property
    def client(self) -> MongoClient:
        """
        Get the MongoDB client instance.
        
        Returns:
            MongoClient: The MongoDB client
            
        Raises:
            ConnectionError: If client is not initialized
        """
        if self._client is None:
            raise ConnectionError("MongoDB client is not initialized")
        return self._client
    
    @property
    def database(self):
        """
        Get the configured database.
        
        Returns:
            Database: MongoDB database instance
        """
        settings = get_settings()
        return self.client[settings.database_name]
    
    def health_check(self) -> dict:
        """
        Perform a health check on the MongoDB connection.
        
        Returns:
            dict: Health check status with details
        """
        try:
            # Ping the database
            start_time = datetime.utcnow()
            self.client.admin.command('ping')
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Get server status
            server_status = self.client.admin.command('serverStatus')
            
            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "database": get_settings().database_name,
                "connections": server_status.get('connections', {}),
                "uptime_seconds": server_status.get('uptime', 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Unexpected error during health check: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("MongoDB connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Singleton accessor function
_db_client: Optional[MongoDBClient] = None


def get_db_client() -> MongoDBClient:
    """
    Get the singleton MongoDB client instance.
    
    Returns:
        MongoDBClient: The MongoDB client instance
    """
    global _db_client
    if _db_client is None:
        _db_client = MongoDBClient()
    return _db_client


def get_database():
    """
    Get the MongoDB database instance.
    
    Returns:
        Database: MongoDB database
    """
    return get_db_client().database