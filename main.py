"""
Vienna - AI Agent Orchestration System
Main entry point for the application.
"""

from src.config import get_settings


def main():
    """Main application entry point."""
    print("Vienna - AI Agent Orchestration System")
    print("=" * 50)
    
    try:
        # Load settings to verify configuration
        settings = get_settings()
        print(f"✓ Configuration loaded successfully")
        print(f"✓ Database: {settings.database_name}")
        print(f"✓ Log level: {settings.log_level}")
        print(f"✓ Agent registry: {settings.agent_registry_path}")
        print("\nSystem initialized. Ready for Phase 2 implementation.")
        
    except Exception as e:
        print(f"✗ Error loading configuration: {e}")
        print("\nPlease ensure .env file is created and all required fields are set.")
        print("Refer to .env.example for the required configuration.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())