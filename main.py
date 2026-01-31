"""
Vienna AI Agent Orchestration System
Main application entry point
"""

import logging
import sys
from datetime import datetime

from src.config import get_settings
from src.database import (
    get_db_client,
    create_user,
    get_user,
    create_session,
    update_session,
    create_task,
    get_credentials
)
from src.core import parse_intent, ExecutionContext, execute_plan
from src.cli.terminal import (
    console,
    show_welcome,
    show_help,
    show_status,
    show_history,
    display_task_result,
    display_error,
    get_input,
    clear_screen
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vienna.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def check_agent_status(user_id: str) -> tuple[bool, bool]:
    """
    Check connection status for Gmail and GitHub agents.
    
    Args:
        user_id: User identifier
        
    Returns:
        tuple: (gmail_connected, github_connected)
    """
    try:
        gmail_creds = get_credentials(user_id, "gmail")
        gmail_connected = gmail_creds is not None
    except:
        gmail_connected = False
    
    try:
        github_creds = get_credentials(user_id, "github")
        github_connected = github_creds is not None
    except:
        github_connected = False
    
    return gmail_connected, github_connected


def main():
    """Main application loop."""
    try:
        # Load settings
        settings = get_settings()
        logger.info("Vienna starting up...")
        
        # Initialize database
        db_client = get_db_client()
        health = db_client.health_check()
        
        if health['status'] != 'healthy':
            console.print("[red]✗ Database connection failed.[/red]")
            console.print("[yellow]Please check your MongoDB connection settings in .env[/yellow]")
            return 1
        
        logger.info("Database connected successfully")
        
        # Show welcome
        show_welcome()
        
        # Get or create default user
        user_id = "default_user"
        user = get_user(user_id)
        
        if not user:
            console.print("[dim]Creating user profile...[/dim]")
            create_user(user_id, "user@vienna.local")
            logger.info(f"Created user: {user_id}")
        
        # Create session
        session = create_session(user_id)
        session_id = session['session_id']
        logger.info(f"Session created: {session_id}")
        
        # Initialize conversation history
        conversation_history = []
        
        # Main interaction loop
        while True:
            try:
                # Get user input
                user_input = get_input()
                
                # Handle empty input
                if not user_input.strip():
                    continue
                
                # Check for utility commands
                command = user_input.strip().lower()
                
                if command in ["exit", "quit", "bye", "q"]:
                    console.print("\n[yellow]Goodbye! Thanks for using Vienna.[/yellow]\n")
                    break
                
                elif command == "help":
                    show_help()
                    continue
                
                elif command == "status":
                    gmail_connected, github_connected = check_agent_status(user_id)
                    show_status(gmail_connected, github_connected)
                    continue
                
                elif command == "clear":
                    clear_screen()
                    show_welcome()
                    continue
                
                elif command == "history":
                    show_history(conversation_history)
                    continue
                
                # Process natural language command
                console.print("[dim]Analyzing your request...[/dim]")
                
                # Parse intent
                try:
                    execution_plan = parse_intent(
                        user_input,
                        user_id,
                        conversation_history
                    )
                    
                    logger.info(
                        f"Parsed intent: {len(execution_plan.tasks)} tasks, "
                        f"type: {execution_plan.execution_type}"
                    )
                    
                except Exception as e:
                    logger.error(f"Intent parsing failed: {e}")
                    display_error(
                        str(e),
                        "Try rephrasing your request or type 'help' for examples."
                    )
                    continue
                
                # Create execution context
                context = ExecutionContext(
                    session_id=session_id,
                    user_id=user_id,
                    user_input=user_input
                )
                
                # Execute plan
                try:
                    results_summary = execute_plan(execution_plan, context)
                    
                    # Display results
                    console.print("\n[bold green]Results:[/bold green]\n")
                    
                    has_results = False
                    for task in execution_plan.tasks:
                        result = context.get_result(task.id)
                        if result:
                            display_task_result(task, result)
                            has_results = True
                    
                    if not has_results:
                        console.print("[yellow]No results to display.[/yellow]")
                    
                    # Show execution summary if there were failures
                    if context.has_failures():
                        failed_count = len(context.get_failed_tasks())
                        console.print(
                            f"[yellow]⚠ {failed_count} task(s) failed during execution.[/yellow]"
                        )
                    
                except Exception as e:
                    logger.error(f"Execution failed: {e}")
                    display_error(
                        str(e),
                        "An error occurred while executing your request."
                    )
                    continue
                
                # Store in conversation history
                conversation_entry = {
                    "user_input": user_input,
                    "system_response": f"Executed {len(execution_plan.tasks)} tasks",
                    "timestamp": datetime.utcnow()
                }
                conversation_history.append(conversation_entry)
                
                # Update session in database
                try:
                    update_session(
                        session_id=session_id,
                        user_input=user_input,
                        system_response=conversation_entry["system_response"]
                    )
                except Exception as e:
                    logger.warning(f"Failed to update session: {e}")
                
                # Store task execution in database
                try:
                    task_data = {
                        "session_id": session_id,
                        "user_id": user_id,
                        "user_input": user_input,
                        "execution_plan": {
                            "tasks": [
                                {
                                    "id": t.id,
                                    "agent_type": t.agent_type,
                                    "mode": t.mode,
                                    "parameters": t.parameters
                                } for t in execution_plan.tasks
                            ],
                            "execution_type": execution_plan.execution_type
                        },
                        "status": "completed" if not context.has_failures() else "partial",
                        "results": context.get_all_results()
                    }
                    
                    create_task(
                        session_id=session_id,
                        user_id=user_id,
                        user_input=user_input,
                        execution_plan=task_data["execution_plan"]
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to store task: {e}")
            
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' to quit Vienna.[/yellow]")
                continue
            
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                display_error(
                    "An unexpected error occurred.",
                    "Please try again or type 'exit' to quit."
                )
                continue
        
        logger.info("Vienna shutting down...")
        return 0
        
    except Exception as e:
        console.print(f"\n[red]✗ Fatal error: {e}[/red]")
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())