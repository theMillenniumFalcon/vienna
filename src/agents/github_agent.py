"""
GitHub agent for repository operations.
Provides list_repos and get_repo functionality for GitHub.
"""

import logging
from typing import Dict, Any

from github import Github, GithubException, RateLimitExceededException
from github.Repository import Repository
from github.GithubObject import NotSet

from src.agents.base_agent import BaseAgent
from src.auth import LazyAuthManager

logger = logging.getLogger(__name__)


class GitHubAgent(BaseAgent):
    """
    GitHub agent for repository operations.
    
    Supports modes: list_repos, get_repo
    """
    
    def __init__(self, user_id: str):
        """
        Initialize GitHub agent.
        
        Args:
            user_id: User identifier
        """
        super().__init__(user_id)
        self.github_client = None
        self.access_token = None
        self.authenticated_user = None
    
    def _get_agent_type(self) -> str:
        """Return agent type identifier."""
        return "github"
    
    def authenticate(self) -> bool:
        """
        Authenticate with GitHub using lazy OAuth.
        
        Returns:
            bool: True if authentication successful
            
        Raises:
            Exception: If authentication fails
        """
        try:
            logger.info(f"Authenticating GitHub for user {self.user_id}")
            
            # Use lazy authentication - triggers OAuth if needed
            self.access_token = LazyAuthManager.ensure_github_auth(self.user_id)
            
            # Create GitHub client
            self.github_client = Github(self.access_token)
            
            # Get authenticated user
            self.authenticated_user = self.github_client.get_user()
            
            # Verify authentication by getting user login
            username = self.authenticated_user.login
            logger.info(f"GitHub authentication successful for {username}")
            
            return True
            
        except Exception as e:
            logger.error(f"GitHub authentication failed: {e}")
            raise
    
    def validate_parameters(self, mode: str, parameters: Dict[str, Any]) -> bool:
        """
        Validate parameters for the given mode.
        
        Args:
            mode: Operation mode (list_repos, get_repo)
            parameters: Parameters to validate
            
        Returns:
            bool: True if valid
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Use registry for basic validation
        valid, error = self.registry.validate_mode_parameters(
            self.agent_type,
            mode,
            parameters
        )
        
        if not valid:
            raise ValueError(error)
        
        # Additional validation for specific modes
        if mode == "list_repos":
            sort_by = parameters.get('sort_by')
            if sort_by and sort_by not in ['stars', 'updated', 'created', 'pushed']:
                raise ValueError(
                    f"Invalid sort_by value: {sort_by}. "
                    "Must be one of: stars, updated, created, pushed"
                )
            
            visibility = parameters.get('visibility')
            if visibility and visibility not in ['all', 'public', 'private']:
                raise ValueError(
                    f"Invalid visibility value: {visibility}. "
                    "Must be one of: all, public, private"
                )
        
        return True
    
    def execute(self, mode: str, parameters: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute GitHub operation.
        
        Args:
            mode: Operation mode (list_repos, get_repo)
            parameters: Mode-specific parameters
            context: Execution context
            
        Returns:
            dict: Result data
            
        Raises:
            NotImplementedError: If mode is not supported
        """
        if mode == "list_repos":
            return self._list_repositories(parameters)
        elif mode == "get_repo":
            return self._get_repository(parameters)
        else:
            raise NotImplementedError(f"Mode '{mode}' is not implemented for GitHub agent")
    
    def _list_repositories(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        List user repositories.
        
        Args:
            parameters: {
                'sort_by': Optional sort field (stars, updated, created, pushed),
                'limit': Max repos to return (default: 10),
                'visibility': Filter by visibility (all, public, private)
            }
            
        Returns:
            dict: List of repository objects with metadata
        """
        try:
            sort_by = parameters.get('sort_by', 'updated')
            limit = parameters.get('limit', 10)
            visibility = parameters.get('visibility', 'all')
            
            logger.info(f"Listing repositories: sort={sort_by}, limit={limit}, visibility={visibility}")
            
            # Check rate limit before proceeding
            rate_limit_info = self._check_rate_limit()
            
            # Map sort_by to PyGithub parameter
            sort_map = {
                'stars': 'stargazers',
                'updated': 'updated',
                'created': 'created',
                'pushed': 'pushed'
            }
            pygithub_sort = sort_map.get(sort_by, 'updated')
            
            # Get repositories
            self._increment_api_calls()
            repos = self.authenticated_user.get_repos(
                sort=pygithub_sort,
                direction='desc',
                visibility=visibility if visibility != 'all' else NotSet
            )
            
            # Parse repositories
            repo_list = []
            repo_names = []
            repo_urls = []
            
            count = 0
            for repo in repos:
                if count >= limit:
                    break
                
                self._increment_api_calls()
                repo_data = self._parse_repository(repo)
                repo_list.append(repo_data)
                repo_names.append(repo_data['name'])
                repo_urls.append(repo_data['url'])
                
                count += 1
            
            return {
                'repos': repo_list,
                'repo_names': repo_names,
                'repo_urls': repo_urls,
                'count': len(repo_list),
                'sort_by': sort_by,
                'visibility': visibility,
                'rate_limit': rate_limit_info
            }
            
        except RateLimitExceededException as e:
            return self._handle_rate_limit_error(e)
        except GithubException as e:
            return self._handle_github_error(e, "list repositories")
        except Exception as e:
            logger.error(f"Error listing repositories: {e}")
            raise
    
    def _get_repository(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed repository information.
        
        Args:
            parameters: {
                'repo_name': Repository name (required)
            }
            
        Returns:
            dict: Detailed repository information
        """
        try:
            repo_name = parameters['repo_name']
            
            logger.info(f"Getting repository details for: {repo_name}")
            
            # Check rate limit
            rate_limit_info = self._check_rate_limit()
            
            # Get repository
            self._increment_api_calls()
            repo = self.authenticated_user.get_repo(repo_name)
            
            # Get basic info
            repo_data = self._parse_repository(repo, detailed=True)
            
            # Get additional details
            self._increment_api_calls()
            
            # Get languages
            try:
                self._increment_api_calls()
                languages = repo.get_languages()
                repo_data['languages'] = dict(languages)
            except:
                repo_data['languages'] = {}
            
            # Get top contributors
            try:
                self._increment_api_calls()
                contributors = repo.get_contributors()
                top_contributors = []
                for i, contributor in enumerate(contributors):
                    if i >= 5:  # Top 5 contributors
                        break
                    self._increment_api_calls()
                    top_contributors.append({
                        'username': contributor.login,
                        'contributions': contributor.contributions,
                        'url': contributor.html_url
                    })
                repo_data['top_contributors'] = top_contributors
            except:
                repo_data['top_contributors'] = []
            
            # Get README (optional)
            try:
                self._increment_api_calls()
                readme = repo.get_readme()
                self._increment_api_calls()
                repo_data['readme_content'] = readme.decoded_content.decode('utf-8')[:1000]  # First 1000 chars
                repo_data['readme_url'] = readme.html_url
            except:
                repo_data['readme_content'] = None
                repo_data['readme_url'] = None
            
            repo_data['rate_limit'] = rate_limit_info
            
            return repo_data
            
        except GithubException as e:
            if e.status == 404:
                raise ValueError(f"Repository '{parameters['repo_name']}' not found")
            return self._handle_github_error(e, "get repository")
        except RateLimitExceededException as e:
            return self._handle_rate_limit_error(e)
        except Exception as e:
            logger.error(f"Error getting repository: {e}")
            raise
    
    def _parse_repository(self, repo: Repository, detailed: bool = False) -> Dict[str, Any]:
        """
        Parse GitHub repository into standardized format.
        
        Args:
            repo: GitHub Repository object
            detailed: Whether to include detailed information
            
        Returns:
            dict: Parsed repository data
        """
        basic_data = {
            'name': repo.name,
            'full_name': repo.full_name,
            'description': repo.description,
            'stars': repo.stargazers_count,
            'forks': repo.forks_count,
            'language': repo.language,
            'url': repo.html_url,
            'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
        }
        
        if detailed:
            basic_data.update({
                'open_issues': repo.open_issues_count,
                'watchers': repo.watchers_count,
                'created_at': repo.created_at.isoformat() if repo.created_at else None,
                'pushed_at': repo.pushed_at.isoformat() if repo.pushed_at else None,
                'size': repo.size,
                'default_branch': repo.default_branch,
                'is_private': repo.private,
                'is_fork': repo.fork,
                'is_archived': repo.archived,
                'license': repo.license.name if repo.license else None,
                'topics': repo.get_topics() if hasattr(repo, 'get_topics') else [],
            })
        
        return basic_data
    
    def _check_rate_limit(self) -> Dict[str, Any]:
        """
        Check GitHub API rate limit.
        
        Returns:
            dict: Rate limit information
        """
        try:
            self._increment_api_calls()
            rate_limit = self.github_client.get_rate_limit()
            
            core_limit = rate_limit.core
            
            rate_info = {
                'remaining': core_limit.remaining,
                'limit': core_limit.limit,
                'reset': core_limit.reset.isoformat() if core_limit.reset else None
            }
            
            # Warn if low on requests
            if core_limit.remaining < 10:
                logger.warning(
                    f"GitHub API rate limit low: {core_limit.remaining} requests remaining. "
                    f"Resets at {core_limit.reset}"
                )
            
            return rate_info
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return {
                'remaining': 'unknown',
                'limit': 5000,
                'reset': None
            }
    
    def _handle_rate_limit_error(self, error: RateLimitExceededException) -> Dict[str, Any]:
        """
        Handle GitHub rate limit exceeded error.
        
        Args:
            error: Rate limit exception
            
        Returns:
            dict: Error details for proper handling
        """
        try:
            rate_limit = self.github_client.get_rate_limit()
            reset_time = rate_limit.core.reset
            
            error_msg = (
                f"GitHub API rate limit exceeded. "
                f"Limit resets at {reset_time.strftime('%Y-%m-%d %H:%M:%S UTC')}. "
                f"Please wait before retrying."
            )
        except:
            error_msg = "GitHub API rate limit exceeded. Please wait before retrying."
        
        logger.error(error_msg)
        raise Exception(error_msg)
    
    def _handle_github_error(self, error: GithubException, operation: str) -> Dict[str, Any]:
        """
        Handle GitHub API errors with specific error messages.
        
        Args:
            error: GitHub exception
            operation: Operation being performed
            
        Returns:
            dict: Error details for proper handling
        """
        status = error.status
        
        logger.error(f"GitHub API error during {operation}: {status} - {error.data}")
        
        # Handle specific error codes
        if status == 401:
            raise Exception("GitHub authentication failed. Please re-authenticate.")
        
        elif status == 403:
            if 'rate limit' in str(error.data).lower():
                raise Exception("GitHub API rate limit exceeded. Please wait before retrying.")
            else:
                raise Exception("Insufficient permissions for this operation.")
        
        elif status == 404:
            raise Exception(f"Resource not found during {operation}.")
        
        elif status == 422:
            raise Exception(f"Invalid request: {error.data}")
        
        else:
            raise Exception(f"GitHub API error during {operation}: {str(error)}")