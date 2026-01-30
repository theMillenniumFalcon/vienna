"""
Agent registry loader for Vienna AI Agent Orchestration System.
Loads and provides access to agent configurations from agent_registry.yaml.
"""

import logging
from typing import Dict, List, Any, Optional
import yaml

from .settings import get_settings

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Loads and manages agent configurations from YAML registry."""
    
    def __init__(self):
        """Initialize the agent registry."""
        self._registry: Optional[Dict[str, Any]] = None
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load the agent registry from YAML file."""
        settings = get_settings()
        registry_path = settings.agent_registry_path
        
        try:
            with open(registry_path, 'r') as f:
                data = yaml.safe_load(f)
                self._registry = data.get('agents', {})
            
            logger.info(f"Loaded agent registry with {len(self._registry)} agents")
            
        except FileNotFoundError:
            logger.error(f"Agent registry file not found: {registry_path}")
            raise FileNotFoundError(f"Agent registry not found at {registry_path}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing agent registry YAML: {e}")
            raise ValueError(f"Invalid YAML in agent registry: {e}")
        except Exception as e:
            logger.error(f"Error loading agent registry: {e}")
            raise
    
    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """
        Get complete configuration for an agent.
        
        Args:
            agent_type: Agent type identifier (gmail, github)
            
        Returns:
            dict: Complete agent configuration
            
        Raises:
            ValueError: If agent type not found
        """
        if self._registry is None:
            raise RuntimeError("Agent registry not loaded")
        
        if agent_type not in self._registry:
            available = list(self._registry.keys())
            raise ValueError(
                f"Agent type '{agent_type}' not found. "
                f"Available agents: {available}"
            )
        
        return self._registry[agent_type]
    
    def get_agent_modes(self, agent_type: str) -> List[str]:
        """
        Get list of available modes for an agent.
        
        Args:
            agent_type: Agent type identifier (gmail, github)
            
        Returns:
            list: List of mode names
            
        Raises:
            ValueError: If agent type not found
        """
        config = self.get_agent_config(agent_type)
        modes = config.get('modes', {})
        return list(modes.keys())
    
    def get_mode_parameters(self, agent_type: str, mode: str) -> Dict[str, Any]:
        """
        Get parameter specifications for a specific agent mode.
        
        Args:
            agent_type: Agent type identifier (gmail, github)
            mode: Mode name (read, send, list_repos, etc.)
            
        Returns:
            dict: Mode configuration including parameters
            
        Raises:
            ValueError: If agent type or mode not found
        """
        config = self.get_agent_config(agent_type)
        modes = config.get('modes', {})
        
        if mode not in modes:
            available = list(modes.keys())
            raise ValueError(
                f"Mode '{mode}' not found for agent '{agent_type}'. "
                f"Available modes: {available}"
            )
        
        return modes[mode]
    
    def get_mode_description(self, agent_type: str, mode: str) -> str:
        """
        Get description for a specific agent mode.
        
        Args:
            agent_type: Agent type identifier
            mode: Mode name
            
        Returns:
            str: Mode description
        """
        mode_config = self.get_mode_parameters(agent_type, mode)
        return mode_config.get('description', 'No description available')
    
    def get_required_parameters(self, agent_type: str, mode: str) -> List[str]:
        """
        Get list of required parameters for a mode.
        
        Args:
            agent_type: Agent type identifier
            mode: Mode name
            
        Returns:
            list: List of required parameter names
        """
        mode_config = self.get_mode_parameters(agent_type, mode)
        parameters = mode_config.get('parameters', [])
        
        # Parse parameter strings to extract required ones
        required = []
        for param in parameters:
            # Format: "name (required)" or "name (optional, default: value)"
            param_name = param.split('(')[0].strip()
            if '(required)' in param.lower():
                required.append(param_name)
        
        return required
    
    def get_optional_parameters(self, agent_type: str, mode: str) -> Dict[str, Any]:
        """
        Get dictionary of optional parameters with their defaults.
        
        Args:
            agent_type: Agent type identifier
            mode: Mode name
            
        Returns:
            dict: Parameter name -> default value mapping
        """
        mode_config = self.get_mode_parameters(agent_type, mode)
        parameters = mode_config.get('parameters', [])
        
        optional = {}
        for param in parameters:
            if '(optional' in param.lower():
                param_name = param.split('(')[0].strip()
                
                # Extract default value if present
                if 'default:' in param.lower():
                    default_str = param.split('default:')[1].split(')')[0].strip()
                    try:
                        # Try to parse as int
                        default = int(default_str)
                    except ValueError:
                        # Keep as string
                        default = default_str
                    optional[param_name] = default
                else:
                    optional[param_name] = None
        
        return optional
    
    def list_all_agents(self) -> List[Dict[str, Any]]:
        """
        Get list of all available agents with their basic info.
        
        Returns:
            list: List of agent info dictionaries
        """
        if self._registry is None:
            raise RuntimeError("Agent registry not loaded")
        
        agents = []
        for agent_type, config in self._registry.items():
            agents.append({
                'type': agent_type,
                'name': config.get('name'),
                'description': config.get('description'),
                'modes': list(config.get('modes', {}).keys()),
                'oauth_required': config.get('oauth_required', False)
            })
        
        return agents
    
    def requires_oauth(self, agent_type: str) -> bool:
        """
        Check if an agent requires OAuth authentication.
        
        Args:
            agent_type: Agent type identifier
            
        Returns:
            bool: True if OAuth is required
        """
        config = self.get_agent_config(agent_type)
        return config.get('oauth_required', False)
    
    def get_oauth_scopes(self, agent_type: str) -> List[str]:
        """
        Get OAuth scopes required for an agent.
        
        Args:
            agent_type: Agent type identifier
            
        Returns:
            list: List of OAuth scope strings
        """
        config = self.get_agent_config(agent_type)
        return config.get('scopes', [])
    
    def validate_mode_parameters(
        self,
        agent_type: str,
        mode: str,
        parameters: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all required parameters are present.
        
        Args:
            agent_type: Agent type identifier
            mode: Mode name
            parameters: Parameters dictionary to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            required = self.get_required_parameters(agent_type, mode)
            
            # Check for missing required parameters
            missing = [p for p in required if p not in parameters]
            
            if missing:
                return False, f"Missing required parameters: {', '.join(missing)}"
            
            return True, None
            
        except Exception as e:
            return False, str(e)


# Singleton instance
_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """
    Get the singleton AgentRegistry instance.
    
    Returns:
        AgentRegistry: The agent registry instance
    """
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


# Convenience functions
def get_agent_config(agent_type: str) -> Dict[str, Any]:
    """Get agent configuration."""
    return get_agent_registry().get_agent_config(agent_type)


def get_agent_modes(agent_type: str) -> List[str]:
    """Get agent modes."""
    return get_agent_registry().get_agent_modes(agent_type)


def get_mode_parameters(agent_type: str, mode: str) -> Dict[str, Any]:
    """Get mode parameters."""
    return get_agent_registry().get_mode_parameters(agent_type, mode)


def list_all_agents() -> List[Dict[str, Any]]:
    """List all agents."""
    return get_agent_registry().list_all_agents()