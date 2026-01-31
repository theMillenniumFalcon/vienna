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
    
    def _topological_sort(self, graph: Dict[str, Any]) -> List[str]:
        """
        Topological sort using Kahn's algorithm.
        
        Args:
            graph: Task dependency graph
            
        Returns:
            list: Task IDs in execution order
            
        Raises:
            ValueError: If circular dependency detected
        """
        # Calculate in-degrees
        in_degree = {node: 0 for node in graph["nodes"]}
        
        for task_id, dependents in graph["edges"].items():
            for dependent in dependents:
                in_degree[dependent] += 1
        
        # Queue of tasks with no dependencies
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        sorted_tasks = []
        
        while queue:
            task_id = queue.pop(0)
            sorted_tasks.append(task_id)
            
            # Reduce in-degree for dependents
            if task_id in graph["edges"]:
                for dependent in graph["edges"][task_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        # Check if all tasks processed (no cycles)
        if len(sorted_tasks) != len(graph["nodes"]):
            raise ValueError("Circular dependency detected in task graph")
        
        return sorted_tasks
    
    def _extract_required_data(
        self,
        context: ExecutionContext,
        required_inputs: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extract specific fields from previous task results.
        
        Args:
            context: Execution context with task results
            required_inputs: Mapping of parameter names to source paths
                            e.g., {"repo_list": "task_1.repo_names"}
            
        Returns:
            dict: Extracted data
        """
        extracted = {}
        
        for param_name, source_path in required_inputs.items():
            try:
                # Parse source_path: "task_1.repo_names" or "task_1.data.repos[0].name"
                parts = source_path.split(".", 1)
                task_id = parts[0]
                field_path = parts[1] if len(parts) > 1 else ""
                
                # Get task result
                source_result = context.get_result(task_id)
                
                if not source_result:
                    logger.warning(f"Task {task_id} result not found for {param_name}")
                    continue
                
                # Start with the full result
                value = source_result
                
                # Navigate to field
                if field_path:
                    for field in field_path.split("."):
                        # Handle array indexing: repos[0]
                        if "[" in field and "]" in field:
                            field_name = field.split("[")[0]
                            index = int(field.split("[")[1].split("]")[0])
                            value = value[field_name][index]
                        else:
                            value = value.get(field, value)
                
                extracted[param_name] = value
                
            except Exception as e:
                logger.error(f"Error extracting {param_name} from {source_path}: {e}")
                continue
        
        return extracted
    
    def _fill_template(self, template: str, data: Dict[str, Any]) -> str:
        """
        Replace {placeholders} in template with actual data.
        
        Args:
            template: Template string with {placeholders}
            data: Data to fill into template
            
        Returns:
            str: Filled template
        """
        result = template
        
        for key, value in data.items():
            placeholder = f"{{{key}}}"
            
            # Format value appropriately
            if isinstance(value, list):
                # Convert list to numbered format
                formatted = "\n".join([f"{i+1}. {item}" for i, item in enumerate(value)])
            elif isinstance(value, dict):
                # Convert dict to key: value format
                formatted = "\n".join([f"{k}: {v}" for k, v in value.items()])
            else:
                formatted = str(value)
            
            result = result.replace(placeholder, formatted)
        
        return result
    
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
        
        # Get execution order using topological sort
        try:
            ordered_task_ids = self._topological_sort(graph)
        except ValueError as e:
            logger.error(f"Cannot execute sequential plan: {e}")
            console.print(f"[red]Error: {e}[/red]")
            raise
        
        results = []
        
        # Execute in order
        for task_id in ordered_task_ids:
            task = graph['nodes'][task_id]
            
            console.print(f"\n[bold]Executing: {task_id}[/bold]")
            
            # Check if dependencies succeeded
            if task.dependencies:
                failed_deps = []
                for dep_id in task.dependencies:
                    dep_result = context.get_result(dep_id)
                    if not dep_result or dep_result.get('status') != 'success':
                        failed_deps.append(dep_id)
                
                if failed_deps:
                    error_msg = (
                        f"Cannot execute {task_id}: "
                        f"dependency {', '.join(failed_deps)} failed"
                    )
                    logger.error(error_msg)
                    console.print(f"[red]⚠ {error_msg}[/red]")
                    
                    # Store error result
                    error_result = {
                        'status': 'error',
                        'data': None,
                        'metadata': {
                            'execution_time': 0,
                            'timestamp': datetime.utcnow().isoformat()
                        },
                        'error': {
                            'type': 'DependencyError',
                            'message': error_msg
                        }
                    }
                    context.store_result(task_id, error_result)
                    update_task_status(task_id, status='failed', error=error_msg)
                    results.append(error_result)
                    
                    # Continue to next task (don't break - show all dependency failures)
                    continue
            
            # Extract required data from previous tasks
            if task.required_inputs:
                try:
                    extracted_data = self._extract_required_data(
                        context,
                        task.required_inputs
                    )
                    
                    # Fill templates in parameters
                    for param_name, param_value in task.parameters.items():
                        if isinstance(param_value, str) and "{" in param_value:
                            # This is a template, fill it
                            task.parameters[param_name] = self._fill_template(
                                param_value,
                                extracted_data
                            )
                        elif param_name in extracted_data:
                            # Direct replacement
                            task.parameters[param_name] = extracted_data[param_name]
                    
                    logger.info(f"Filled parameters for {task_id}: {task.parameters}")
                    
                except Exception as e:
                    logger.error(f"Error extracting data for {task_id}: {e}")
                    console.print(f"[red]Error extracting data: {e}[/red]")
                    
                    error_result = {
                        'status': 'error',
                        'data': None,
                        'metadata': {
                            'execution_time': 0,
                            'timestamp': datetime.utcnow().isoformat()
                        },
                        'error': {
                            'type': 'DataExtractionError',
                            'message': f"Failed to extract required data: {e}"
                        }
                    }
                    context.store_result(task_id, error_result)
                    results.append(error_result)
                    continue
            
            # Execute task
            result = self._execute_task_sync(task, context)
            results.append(result)
            
            # Update task object
            task.result = result
            task.status = "completed" if result["status"] == "success" else "failed"
        
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