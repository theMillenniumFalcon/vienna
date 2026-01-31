"""
Intent parser for natural language command interpretation.
Uses Claude AI to convert user input into structured execution plans.
"""

import json
import logging
from typing import List, Dict, Any, Optional

from anthropic import Anthropic
from pydantic import ValidationError

from src.config import get_settings, get_agent_registry
from src.database import Task, ExecutionPlan

logger = logging.getLogger(__name__)


# System prompt for Claude
SYSTEM_PROMPT = """You are an intent parser for Vienna, an AI agent orchestration system.

Your job is to analyze user input and convert it into structured tasks that agents can execute.

AVAILABLE AGENTS:
1. GmailAgent
    Capabilities:
    - READ mode: Retrieve emails from Gmail
        Parameters: query (optional), max_results (optional), date_filter (optional: today, this_week)
    - SEND mode: Send email via Gmail
        Parameters: to (required), subject (required), body (required), cc (optional)
    - SEARCH mode: Search emails with filters
        Parameters: query (required), max_results (optional)

2. GitHubAgent
    Capabilities:
    - LIST_REPOS mode: List user's GitHub repositories
        Parameters: sort_by (optional: stars, updated, created, pushed), limit (optional), visibility (optional: all, public, private)
    - GET_REPO mode: Get detailed repository information
        Parameters: repo_name (required)

TASK STRUCTURE:
Each task must have:
- id: unique identifier (task_1, task_2, etc.)
- agent_type: "gmail" or "github"
- mode: specific operation mode
- parameters: dict of parameters for that mode
- dependencies: list of task IDs this task depends on (empty if independent)
- required_inputs: dict mapping parameter names to source task outputs

EXECUTION TYPES:
- "parallel": Tasks are independent and can run simultaneously
- "sequential": Tasks have dependencies and must run in order

EXAMPLES:

Input: "Check my email for today's emails and show my top 5 GitHub repos"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "gmail",
            "mode": "read",
            "parameters": {"date_filter": "today"},
            "dependencies": [],
            "required_inputs": {}
        },
        {
            "id": "task_2",
            "agent_type": "github",
            "mode": "list_repos",
            "parameters": {"sort_by": "stars", "limit": 5},
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}

Input: "Email peter@example.com the names of my top 5 repositories"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "github",
            "mode": "list_repos",
            "parameters": {"sort_by": "stars", "limit": 5},
            "dependencies": [],
            "required_inputs": {}
        },
        {
            "id": "task_2",
            "agent_type": "gmail",
            "mode": "send",
            "parameters": {
                "to": "peter@example.com",
                "subject": "My Top 5 Repositories",
                "body_template": "Hi,\\n\\nHere are my top 5 repositories:\\n{repo_list}\\n\\nBest regards"
            },
            "dependencies": ["task_1"],
            "required_inputs": {
                "repo_list": "task_1.repo_names"
            }
        }
    ],
    "execution_type": "sequential"
}

Input: "Find emails from GitHub and tell me how many there are"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "gmail",
            "mode": "search",
            "parameters": {"query": "from:github.com"},
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}
Note: For this case, counting is done by the system after receiving results, not a separate task.

Input: "Show me my latest 10 emails"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "gmail",
            "mode": "read",
            "parameters": {"max_results": 10},
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}

Input: "List my GitHub repositories sorted by stars"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "github",
            "mode": "list_repos",
            "parameters": {"sort_by": "stars"},
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}

Input: "Get details about my project called 'awesome-app'"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "github",
            "mode": "get_repo",
            "parameters": {"repo_name": "awesome-app"},
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}

Input: "Send an email to john@example.com about our meeting tomorrow"
Output:
{
    "tasks": [
        {
            "id": "task_1",
            "agent_type": "gmail",
            "mode": "send",
            "parameters": {
                "to": "john@example.com",
                "subject": "Meeting Tomorrow",
                "body": "Hi John,\\n\\nJust a reminder about our meeting tomorrow.\\n\\nBest regards"
            },
            "dependencies": [],
            "required_inputs": {}
        }
    ],
    "execution_type": "parallel"
}

RULES:
1. Always return valid JSON
2. Use task_1, task_2, task_3 for task IDs
3. If tasks are independent, use execution_type: "parallel"
4. If one task needs output from another, use execution_type: "sequential" and specify dependencies
5. For email sending with data from previous tasks, use body_template with {placeholders} and required_inputs
6. If user input is unclear, make reasonable assumptions based on context
7. If a request cannot be fulfilled with available agents, return a single task with agent_type: "error" and explain what's missing in parameters
8. For date filters in emails, use "today" or "this_week" when appropriate
9. When user mentions specific email addresses, include them exactly as provided
10. When counting or summarizing results, let the system handle it after task execution - don't create extra tasks for counting

OUTPUT FORMAT:
Return only valid JSON, no markdown, no explanations, no code blocks. Just the raw JSON object."""


class IntentParser:
    """
    Parses natural language input into structured execution plans.
    """
    
    def __init__(self):
        """Initialize the intent parser."""
        self.settings = get_settings()
        self.registry = get_agent_registry()
        self.client = Anthropic(api_key=self.settings.anthropic_api_key)
    
    def parse_intent(
        self,
        user_input: str,
        user_id: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> ExecutionPlan:
        """
        Parse user input into an execution plan.
        
        Args:
            user_input: Natural language input from user
            user_id: User identifier
            conversation_history: Previous conversation turns
            
        Returns:
            ExecutionPlan: Structured execution plan
            
        Raises:
            ValueError: If parsing or validation fails
        """
        logger.info(f"Parsing intent for user {user_id}: '{user_input}'")
        
        try:
            # Build messages with conversation history
            messages = self._build_messages(user_input, conversation_history)
            
            # Call Claude API
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=messages
            )
            
            # Extract response text
            response_text = response.content[0].text.strip()
            logger.debug(f"Claude response: {response_text}")
            
            # Parse JSON response
            parsed = self._parse_json_response(response_text)
            
            # Validate structure
            self._validate_response(parsed)
            
            # Convert to ExecutionPlan
            execution_plan = self._build_execution_plan(parsed)
            
            # Validate execution plan
            self._validate_execution_plan(execution_plan)
            
            logger.info(
                f"Intent parsed successfully: {len(execution_plan.tasks)} tasks, "
                f"execution_type: {execution_plan.execution_type}"
            )
            
            return execution_plan
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            raise ValueError(f"Invalid task structure: {e}")
        except Exception as e:
            logger.error(f"Intent parsing error: {e}")
            raise
    
    def _build_messages(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """
        Build messages array with conversation history.
        
        Args:
            user_input: Current user input
            conversation_history: Previous conversation turns
            
        Returns:
            list: Messages for Claude API
        """
        messages = []
        
        # Add conversation history (last 5 interactions)
        if conversation_history:
            for interaction in conversation_history[-5:]:
                messages.append({
                    "role": "user",
                    "content": interaction.get("user_input", "")
                })
                messages.append({
                    "role": "assistant",
                    "content": interaction.get("system_response", "")
                })
        
        # Add current input
        messages.append({
            "role": "user",
            "content": user_input
        })
        
        return messages
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse JSON from Claude's response.
        
        Handles cases where response might include markdown code blocks.
        
        Args:
            response_text: Raw response from Claude
            
        Returns:
            dict: Parsed JSON
        """
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            # Find the JSON content between code blocks
            lines = response_text.split("\n")
            json_lines = []
            in_code_block = False
            
            for line in lines:
                if line.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block or (not line.startswith("```") and json_lines):
                    json_lines.append(line)
            
            response_text = "\n".join(json_lines).strip()
        
        # Parse JSON
        return json.loads(response_text)
    
    def _validate_response(self, parsed: Dict[str, Any]) -> None:
        """
        Validate that the parsed response has required structure.
        
        Args:
            parsed: Parsed JSON response
            
        Raises:
            ValueError: If structure is invalid
        """
        # Check required fields
        if "tasks" not in parsed:
            raise ValueError("Response missing 'tasks' field")
        
        if "execution_type" not in parsed:
            raise ValueError("Response missing 'execution_type' field")
        
        # Validate execution type
        if parsed["execution_type"] not in ["parallel", "sequential"]:
            raise ValueError(
                f"Invalid execution_type: {parsed['execution_type']}. "
                "Must be 'parallel' or 'sequential'"
            )
        
        # Validate tasks is a list
        if not isinstance(parsed["tasks"], list):
            raise ValueError("'tasks' must be a list")
        
        if len(parsed["tasks"]) == 0:
            raise ValueError("'tasks' list cannot be empty")
    
    def _build_execution_plan(self, parsed: Dict[str, Any]) -> ExecutionPlan:
        """
        Build ExecutionPlan from parsed JSON.
        
        Args:
            parsed: Parsed JSON response
            
        Returns:
            ExecutionPlan: Execution plan with Task objects
        """
        # Convert task dicts to Task objects
        tasks = []
        for task_data in parsed["tasks"]:
            # Ensure all required fields have defaults
            task_dict = {
                "id": task_data.get("id"),
                "agent_type": task_data.get("agent_type"),
                "mode": task_data.get("mode"),
                "parameters": task_data.get("parameters", {}),
                "dependencies": task_data.get("dependencies", []),
                "required_inputs": task_data.get("required_inputs", {}),
                "status": "pending",
                "result": None,
                "error": None
            }
            
            task = Task(**task_dict)
            tasks.append(task)
        
        # Create execution plan
        execution_plan = ExecutionPlan(
            tasks=tasks,
            execution_type=parsed["execution_type"]
        )
        
        return execution_plan
    
    def _validate_execution_plan(self, plan: ExecutionPlan) -> None:
        """
        Validate that the execution plan is valid.
        
        Args:
            plan: Execution plan to validate
            
        Raises:
            ValueError: If plan is invalid
        """
        # Validate each task
        for task in plan.tasks:
            self._validate_task(task, plan)
    
    def _validate_task(self, task: Task, plan: ExecutionPlan) -> None:
        """
        Validate a single task.
        
        Args:
            task: Task to validate
            plan: Execution plan containing this task
            
        Raises:
            ValueError: If task is invalid
        """
        # Check if agent_type exists
        try:
            agent_config = self.registry.get_agent_config(task.agent_type)
        except ValueError:
            raise ValueError(
                f"Task {task.id}: Unknown agent_type '{task.agent_type}'"
            )
        
        # Check if mode is valid for agent
        available_modes = self.registry.get_agent_modes(task.agent_type)
        if task.mode not in available_modes:
            raise ValueError(
                f"Task {task.id}: Invalid mode '{task.mode}' for agent '{task.agent_type}'. "
                f"Available modes: {available_modes}"
            )
        
        # Validate dependencies reference existing tasks
        task_ids = {t.id for t in plan.tasks}
        for dep_id in task.dependencies:
            if dep_id not in task_ids:
                raise ValueError(
                    f"Task {task.id}: Dependency '{dep_id}' not found in task list"
                )
        
        # Check for circular dependencies
        self._check_circular_dependencies(task, plan)
    
    def _check_circular_dependencies(self, task: Task, plan: ExecutionPlan) -> None:
        """
        Check for circular dependencies.
        
        Args:
            task: Task to check
            plan: Execution plan
            
        Raises:
            ValueError: If circular dependency detected
        """
        visited = set()
        path = set()
        
        def visit(task_id: str) -> bool:
            if task_id in path:
                return True  # Circular dependency
            if task_id in visited:
                return False
            
            path.add(task_id)
            visited.add(task_id)
            
            # Find task
            current_task = next((t for t in plan.tasks if t.id == task_id), None)
            if current_task:
                for dep_id in current_task.dependencies:
                    if visit(dep_id):
                        return True
            
            path.remove(task_id)
            return False
        
        if visit(task.id):
            raise ValueError(f"Circular dependency detected involving task {task.id}")


# Convenience function
_parser: Optional[IntentParser] = None


def get_intent_parser() -> IntentParser:
    """
    Get the singleton IntentParser instance.
    
    Returns:
        IntentParser: The intent parser instance
    """
    global _parser
    if _parser is None:
        _parser = IntentParser()
    return _parser


def parse_intent(
    user_input: str,
    user_id: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> ExecutionPlan:
    """
    Parse user input into an execution plan.
    
    Args:
        user_input: Natural language input from user
        user_id: User identifier
        conversation_history: Previous conversation turns
        
    Returns:
        ExecutionPlan: Structured execution plan
    """
    parser = get_intent_parser()
    return parser.parse_intent(user_input, user_id, conversation_history)