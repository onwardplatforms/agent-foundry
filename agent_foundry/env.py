"""Environment variable handling for Agent Foundry."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env_files(agent_id: Optional[str] = None) -> None:
    """Load environment variables from .env files.

    Order of precedence (highest to lowest):
    1. Agent-specific .env file (if agent_id provided)
    2. Root .env file

    Args:
        agent_id: Optional agent ID to load agent-specific env file
    """
    # Load root .env file first (lowest precedence)
    root_env = Path(".env")
    if root_env.exists():
        load_dotenv(root_env)

    # Load agent-specific .env file if provided (highest precedence)
    if agent_id:
        agent_env = Path(f".agents/{agent_id}/.env")
        if agent_env.exists():
            load_dotenv(agent_env, override=True)


def get_env_var(
    key: str, default: Optional[str] = None, agent_id: Optional[str] = None
) -> Optional[str]:
    """Get environment variable with proper precedence.

    Order of precedence (highest to lowest):
    1. Agent-specific .env file (if agent_id provided)
    2. Root .env file
    3. Default value

    Args:
        key: Environment variable key
        default: Default value if not found
        agent_id: Optional agent ID to check agent-specific env file

    Returns:
        Environment variable value or default
    """
    # Load env files if agent_id provided
    if agent_id:
        load_env_files(agent_id)
    else:
        # Load just root .env if no agent_id
        root_env = Path(".env")
        if root_env.exists():
            load_dotenv(root_env)

    return os.getenv(key, default)
