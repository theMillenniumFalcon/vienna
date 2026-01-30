"""
Vienna - AI Agent Orchestration System
Main entry point for the application.
"""

import logging
from src.config import get_settings
from src.database import get_db_client, create_indexes


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main application entry point."""
    print("\n" + "=" * 60)
    print("Vienna - AI Agent Orchestration System")
    print("=" * 60 + "\n")
    
    try:
        # Load settings
        settings = get_settings()
        print(f"✓ Configuration loaded successfully")
        print(f"  - Database: {settings.database_name}")
        print(f"  - Log level: {settings.log_level}")
        print(f"  - Agent registry: {settings.agent_registry_path.name}")
        
        # Initialize database connection
        print("\n" + "-" * 60)
        print("Database Connection")
        print("-" * 60)
        
        db_client = get_db_client()
        health = db_client.health_check()
        
        if health["status"] == "healthy":
            print(f"✓ MongoDB connected")
            print(f"  - Response time: {health['response_time_ms']}ms")
            print(f"  - Database: {health['database']}")
            print(f"  - Active connections: {health['connections'].get('current', 'N/A')}")
        else:
            print(f"✗ Database health check failed")
            print(f"  - Error: {health.get('error', 'Unknown error')}")
            print("\nPlease verify your MongoDB Atlas connection string in .env")
            return 1
        
        # Verify/create indexes
        print("\n" + "-" * 60)
        print("Database Indexes")
        print("-" * 60)
        
        if create_indexes():
            print("✓ All database indexes verified/created")
        else:
            print("✗ Failed to create some indexes (check logs)")
        
        # Summary
        print("\n" + "=" * 60)
        print("System Status: READY")
        print("=" * 60)
        print("\nPhase 2 completed. Database layer is fully operational.")
        print("Ready for Phase 3 implementation.\n")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error initializing system: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure .env file exists with all required fields")
        print("2. Verify MongoDB Atlas connection string is correct")
        print("3. Check that your IP is whitelisted in MongoDB Atlas")
        print("4. Refer to .env.example for required configuration\n")
        logger.exception("System initialization failed")
        return 1


if __name__ == "__main__":
    exit(main())