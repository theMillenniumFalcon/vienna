"""
Execution engine for orchestrating agent tasks.
Handles parallel and sequential task execution with dependency management.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.database import Task, ExecutionPlan, update_task_status
from src.agents import GmailAgent, GitHubAgent
from .context_manager import ExecutionContext

logger = logging.getLogger(__name__)
console = Console()


class ExecutionEngine:
    """
    Orchestrates execution of tasks with dependency management.
    
    Supports both parallel and sequential execution modes.
    """
    
    def __init__(self):
        """Initialize the execution engine."""
        logger.info("Execution engine initialized")
    
    def execute(
        self,
        execution_plan: ExecutionPlan,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        Execute an execution plan.
        
        Args:
            execution_plan: Plan with tasks to execute
            context: Execution context
            
        Returns:
            dict: Execution results with summary
        """
        logger.info(
            f"Executing plan with {len(execution_plan.tasks)} tasks "
            f"(type: {execution_plan.execution_type})"
        )
        
        try:
            # Build task graph
            graph = self._build_task_graph(execution_plan.tasks)
            
            # Execute based on type
            if execution_plan.execution_type == "parallel":
                results = self._execute_parallel(execution_plan.tasks, context)
            else:  # sequential
                results = self._execute_sequential(execution_plan, context, graph)
            
            # Get summary
            summary = context.get_summary()
            summary['results'] = results
            
            logger.info(
                f"Execution complete: {summary['successful_tasks']}/{summary['total_tasks']} "
                f"tasks succeeded in {summary['execution_time']:.2f}s"
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise
    
    def _build_task_graph(self, tasks: List[Task]) -> Dict[str, Any]:
        """
        Build dependency graph for tasks.
        
        Args:
            tasks: List of tasks
            
        Returns:
            dict: Task graph with nodes, edges, and independent tasks
        """
        graph = {
            "nodes": {task.id: task for task in tasks},
            "edges": {},  # task_id -> list of dependent task_ids
            "independent": []  # tasks with no dependencies
        }
        
        # Build edges and find independent tasks
        for task in tasks:
            if not task.dependencies:
                graph["independent"].append(task.id)
            else:
                for dep in task.dependencies:
                    if dep not in graph["edges"]:
                        graph["edges"][dep] = []
                    graph["edges"][dep].append(task.id)
        
        return graph
    
    def _get_agent(self, agent_type: str, user_id: str):
        """
        Get agent instance for agent type.
        
        Args:
            agent_type: Type of agent (gmail, github)
            user_id: User identifier
            
        Returns:
            BaseAgent: Agent instance
            
        Raises:
            ValueError: If agent type is unknown
        """
        if agent_type == "gmail":
            return GmailAgent(user_id)
        elif agent_type == "github":
            return GitHubAgent(user_id)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
    
    def _execute_parallel(
        self,
        tasks: List[Task],
        context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """
        Execute tasks in parallel.
        
        Args:
            tasks: List of tasks to execute
            context: Execution context
            
        Returns:
            list: List of task results
        """
        console.print(
            Panel(
                f"[bold cyan]Executing {len(tasks)} tasks in parallel[/bold cyan]",
                title="Parallel Execution",
                border_style="cyan"
            )
        )
        
        # Execute using asyncio
        results = asyncio.run(self._execute_parallel_async(tasks, context))
        
        # Display summary
        self._display_summary(context)
        
        return results
    
    async def _execute_parallel_async(
        self,
        tasks: List[Task],
        context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """
        Execute tasks in parallel using asyncio.
        
        Args:
            tasks: List of tasks
            context: Execution context
            
        Returns:
            list: List of results
        """
        # Create async tasks
        async_tasks = [
            self._execute_task_async(task, context)
            for task in tasks
        ]
        
        # Execute all in parallel, capturing exceptions
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        return results
    
    async def _execute_task_async(
        self,
        task: Task,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        Execute a single task asynchronously.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            dict: Task result
        """
        # Run in thread pool since agent operations are synchronous
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._execute_task_sync,
            task,
            context
        )
        return result
    
    def _execute_task_sync(
        self,
        task: Task,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        Execute a single task synchronously with progress display.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            dict: Task result
        """
        try:
            # Show start
            console.print(
                f"⚡ [cyan]Starting {task.agent_type}.{task.mode}[/cyan] (task: {task.id})"
            )
            
            # Get agent
            agent = self._get_agent(task.agent_type, context.user_id)
            
            # Execute task (agent handles authentication, validation, execution)
            result = agent.execute_task(task, context.get_all_results())
            
            # Store result in context
            context.store_result(task.id, result)
            
            # Update task status in database
            if result['status'] == 'success':
                update_task_status(
                    task.id,
                    status='completed',
                    results=result['data']
                )
                console.print(
                    f"✓ [green]{task.agent_type}.{task.mode} completed[/green] "
                    f"({result['metadata']['execution_time']:.2f}s)"
                )
            else:
                update_task_status(
                    task.id,
                    status='failed',
                    error=result['error']['message'] if result.get('error') else None
                )
                console.print(
                    f"✗ [red]{task.agent_type}.{task.mode} failed[/red]: "
                    f"{result['error']['message'] if result.get('error') else 'Unknown error'}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            
            # Create error result
            error_result = {
                'status': 'error',
                'data': None,
                'metadata': {
                    'execution_time': 0,
                    'timestamp': datetime.utcnow().isoformat()
                },
                'error': {
                    'type': type(e).__name__,
                    'message': str(e)
                }
            }
            
            # Store in context
            context.store_result(task.id, error_result)
            
            # Update database
            update_task_status(task.id, status='failed', error=str(e))
            
            console.print(
                f"✗ [red]{task.agent_type}.{task.mode} failed[/red]: {str(e)}"
            )
            
            return error_result
    
    def _execute_sequential(
        self,
        execution_plan: ExecutionPlan,
        context: ExecutionContext,
        graph: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute tasks sequentially based on dependencies.
        
        Args:
            execution_plan: Execution plan
            context: Execution context
            graph: Task dependency graph
            
        Returns:
            list: List of results
        """
        console.print(
            Panel(
                f"[bold yellow]Executing {len(execution_plan.tasks)} tasks sequentially[/bold yellow]",
                title="Sequential Execution",
                border_style="yellow"
            )
        )
        
        # Get execution order
        execution_order = execution_plan.get_execution_order()
        
        results = []
        
        # Execute in order
        for batch in execution_order:
            console.print(f"\n[bold]Executing batch: {', '.join(batch)}[/bold]")
            
            # Get tasks for this batch
            batch_tasks = [graph['nodes'][task_id] for task_id in batch]
            
            # Execute batch (can be parallel within batch if independent)
            if len(batch_tasks) == 1:
                # Single task - execute synchronously
                result = self._execute_task_sync(batch_tasks[0], context)
                results.append(result)
            else:
                # Multiple tasks - execute in parallel
                batch_results = asyncio.run(
                    self._execute_parallel_async(batch_tasks, context)
                )
                results.extend(batch_results)
            
            # Check for failures
            if context.has_failures():
                failed = context.get_failed_tasks()
                console.print(
                    f"\n[yellow]Warning: {len(failed)} task(s) failed. "
                    f"Continuing with remaining tasks...[/yellow]"
                )
        
        # Display summary
        self._display_summary(context)
        
        return results
    
    def _display_summary(self, context: ExecutionContext) -> None:
        """
        Display execution summary.
        
        Args:
            context: Execution context
        """
        summary = context.get_summary()
        
        # Create summary table
        table = Table(title="Execution Summary", border_style="blue")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Total Tasks", str(summary['total_tasks']))
        table.add_row(
            "Successful",
            f"[green]{summary['successful_tasks']}[/green]"
        )
        table.add_row(
            "Failed",
            f"[red]{summary['failed_tasks']}[/red]"
        )
        table.add_row(
            "Execution Time",
            f"{summary['execution_time']:.2f}s"
        )
        
        console.print("\n")
        console.print(table)
        console.print("\n")


# Singleton instance
_execution_engine: Optional[ExecutionEngine] = None


def get_execution_engine() -> ExecutionEngine:
    """
    Get the singleton ExecutionEngine instance.
    
    Returns:
        ExecutionEngine: The execution engine instance
    """
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = ExecutionEngine()
    return _execution_engine


def execute_plan(
    execution_plan: ExecutionPlan,
    context: ExecutionContext
) -> Dict[str, Any]:
    """
    Execute an execution plan.
    
    Args:
        execution_plan: Plan to execute
        context: Execution context
        
    Returns:
        dict: Execution results
    """
    engine = get_execution_engine()
    return engine.execute(execution_plan, context)