"""Agents module for Vienna AI Agent Orchestration System."""

from .base_agent import BaseAgent
from .gmail_agent import GmailAgent

__all__ = [
    "BaseAgent",
    "GmailAgent",
]