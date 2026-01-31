"""
Terminal interface for Vienna AI Agent Orchestration System.
Provides rich console UI for user interaction and result display.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.markdown import Markdown

logger = logging.getLogger(__name__)
console = Console()


def show_welcome() -> None:
    """Display welcome message."""
    welcome_text = """[bold cyan]Vienna[/bold cyan]
AI Agent Orchestration System

[dim]Available commands:[/dim]
• Natural language queries (e.g., "Show my latest emails")
• [yellow]help[/yellow] - Show examples and commands
• [yellow]status[/yellow] - Check agent connection status
• [yellow]clear[/yellow] - Clear terminal screen
• [yellow]history[/yellow] - Show recent commands
• [yellow]exit[/yellow] - Quit Vienna

[dim]Type your command below:[/dim]"""
    
    console.print(Panel.fit(
        welcome_text,
        border_style="cyan",
        padding=(1, 2)
    ))


def show_help() -> None:
    """Display help information with examples."""
    help_text = """
# Vienna Help

## Gmail Commands

• **Read emails**: "Show me my latest 10 emails"
• **Read today's emails**: "Show emails from today"
• **Search emails**: "Find emails from GitHub"
• **Send email**: "Send an email to john@example.com about the meeting"

## GitHub Commands

• **List repositories**: "Show my GitHub repositories"
• **Sort by stars**: "List my repos sorted by stars"
• **Get repo details**: "Get details about my project called awesome-app"

## Combined Commands

• **Parallel**: "Show my emails and list my GitHub repos"
• **Sequential**: "Email john@example.com the names of my top 5 repositories"

## Utility Commands

• `help` - Show this help message
• `status` - Check Gmail and GitHub connection status
• `clear` - Clear the terminal screen
• `history` - Show your recent commands
• `exit` - Exit Vienna
"""
    
    console.print(Markdown(help_text))


def show_status(gmail_connected: bool, github_connected: bool) -> None:
    """
    Display connection status for agents.
    
    Args:
        gmail_connected: Whether Gmail is connected
        github_connected: Whether GitHub is connected
    """
    table = Table(title="Agent Status", border_style="blue")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", style="white")
    
    gmail_status = "[green]✓ Connected[/green]" if gmail_connected else "[red]✗ Not connected[/red]"
    github_status = "[green]✓ Connected[/green]" if github_connected else "[red]✗ Not connected[/red]"
    
    table.add_row("Gmail", gmail_status)
    table.add_row("GitHub", github_status)
    
    console.print("\n")
    console.print(table)
    console.print("\n")


def show_history(history: List[Dict[str, Any]], limit: int = 10) -> None:
    """
    Display conversation history.
    
    Args:
        history: List of conversation entries
        limit: Max number of entries to show
    """
    if not history:
        console.print("[yellow]No command history yet.[/yellow]")
        return
    
    table = Table(title=f"Recent Commands (last {min(limit, len(history))})", border_style="blue")
    table.add_column("#", style="dim", width=4)
    table.add_column("Time", style="cyan", width=20)
    table.add_column("Command", style="white")
    
    # Show last N entries
    recent = history[-limit:]
    for i, entry in enumerate(recent, 1):
        timestamp = entry.get('timestamp', datetime.now())
        if isinstance(timestamp, str):
            time_str = timestamp
        else:
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        command = entry.get('user_input', '')
        table.add_row(str(i), time_str, command)
    
    console.print("\n")
    console.print(table)
    console.print("\n")


def display_email_results(emails: List[Dict[str, Any]]) -> None:
    """
    Display email results in a formatted table.
    
    Args:
        emails: List of email dictionaries
    """
    if not emails:
        console.print("[yellow]No emails found.[/yellow]")
        return
    
    table = Table(title=f"Emails ({len(emails)} found)", border_style="cyan")
    table.add_column("Date", style="cyan", width=20)
    table.add_column("From", style="green", width=30)
    table.add_column("Subject", style="yellow")
    
    for email in emails[:20]:  # Limit to 20 for display
        date = email.get("date", "")
        sender = email.get("from", "")
        subject = email.get("subject", "(no subject)")
        
        # Truncate long subjects
        if len(subject) > 60:
            subject = subject[:57] + "..."
        
        table.add_row(date, sender, subject)
    
    console.print("\n")
    console.print(table)
    
    if len(emails) > 20:
        console.print(f"[dim]... and {len(emails) - 20} more emails[/dim]")
    
    console.print("\n")


def display_repo_results(repos: List[Dict[str, Any]]) -> None:
    """
    Display repository results in a formatted table.
    
    Args:
        repos: List of repository dictionaries
    """
    if not repos:
        console.print("[yellow]No repositories found.[/yellow]")
        return
    
    table = Table(title=f"Repositories ({len(repos)} found)", border_style="cyan")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("⭐ Stars", style="yellow", justify="right", width=10)
    table.add_column("Language", style="green", width=15)
    table.add_column("Description")
    
    for repo in repos:
        name = repo.get("name", "")
        stars = str(repo.get("stars", 0))
        language = repo.get("language") or "N/A"
        description = repo.get("description") or ""
        
        # Truncate long descriptions
        if len(description) > 50:
            description = description[:47] + "..."
        
        table.add_row(name, stars, language, description)
    
    console.print("\n")
    console.print(table)
    console.print("\n")


def display_repo_details(repo: Dict[str, Any]) -> None:
    """
    Display detailed repository information.
    
    Args:
        repo: Repository details dictionary
    """
    console.print(f"\n[bold cyan]Repository: {repo.get('name', 'Unknown')}[/bold cyan]\n")
    
    # Create info table
    table = Table(show_header=False, border_style="blue", box=None)
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white")
    
    # Add fields
    if repo.get('full_name'):
        table.add_row("Full Name", repo['full_name'])
    
    if repo.get('description'):
        table.add_row("Description", repo['description'])
    
    table.add_row("⭐ Stars", str(repo.get('stars', 0)))
    table.add_row("🍴 Forks", str(repo.get('forks', 0)))
    
    if repo.get('language'):
        table.add_row("Language", repo['language'])
    
    if repo.get('open_issues'):
        table.add_row("Open Issues", str(repo['open_issues']))
    
    if repo.get('created_at'):
        table.add_row("Created", repo['created_at'])
    
    if repo.get('updated_at'):
        table.add_row("Updated", repo['updated_at'])
    
    console.print(table)
    
    # Show top contributors if available
    if repo.get('top_contributors'):
        console.print("\n[bold]Top Contributors:[/bold]")
        for i, contributor in enumerate(repo['top_contributors'][:5], 1):
            console.print(f"  {i}. {contributor['username']} ({contributor['contributions']} contributions)")
    
    console.print("\n")


def display_task_result(task: Any, result: Dict[str, Any]) -> None:
    """
    Display result for a single task.
    
    Args:
        task: Task object
        result: Task result dictionary
    """
    if result.get('status') != 'success':
        return
    
    data = result.get('data', {})
    
    # Gmail results
    if task.agent_type == "gmail":
        if task.mode == "read" or task.mode == "search":
            if "emails" in data:
                display_email_results(data["emails"])
        elif task.mode == "send":
            console.print(f"[green]✓ Email sent successfully to {data.get('to', 'recipient')}[/green]")
            if data.get('message_id'):
                console.print(f"[dim]Message ID: {data['message_id']}[/dim]")
    
    # GitHub results
    elif task.agent_type == "github":
        if task.mode == "list_repos":
            if "repos" in data:
                display_repo_results(data["repos"])
        elif task.mode == "get_repo":
            display_repo_details(data)


def display_error(error_message: str, helpful_hint: Optional[str] = None) -> None:
    """
    Display error message with optional helpful hint.
    
    Args:
        error_message: Error message to display
        helpful_hint: Optional helpful hint for user
    """
    console.print(f"\n[red]✗ Error:[/red] {error_message}")
    
    if helpful_hint:
        console.print(f"[dim]{helpful_hint}[/dim]")
    
    console.print()


def display_success(message: str) -> None:
    """
    Display success message.
    
    Args:
        message: Success message to display
    """
    console.print(f"[green]✓ {message}[/green]")


def get_input(prompt: str = "You") -> str:
    """
    Get user input with custom prompt.
    
    Args:
        prompt: Prompt text
        
    Returns:
        str: User input
    """
    return console.input(f"\n[bold cyan]{prompt}:[/bold cyan] ")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()