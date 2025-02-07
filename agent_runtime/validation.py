"""Validation utilities for agent configuration."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jsonschema


def load_schema() -> Dict[str, Any]:
    """Load the agent configuration schema.

    Returns:
        The JSON schema for agent configuration
    """
    schema_path = Path(__file__).parent / "schema" / "agent_schema.json"
    with open(schema_path) as f:
        return json.load(f)


def validate_agent_config(
    config: Union[Path, Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Validate an agent configuration against the schema.

    Args:
        config: Either a path to a config file or a config dictionary

    Returns:
        A tuple of (is_valid, error_messages)
    """
    # Load schema
    schema = load_schema()

    # Load config if path provided
    if isinstance(config, Path):
        try:
            with open(config) as f:
                config_dict = json.load(f)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON in config file: {e}"]
        except FileNotFoundError:
            return False, [f"Config file not found: {config}"]
    else:
        config_dict = config

    # Validate against schema
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(config_dict))

    if not errors:
        return True, []

    # Format error messages
    error_messages = []
    for error in errors:
        path = " -> ".join(str(p) for p in error.path)
        message = f"{path}: {error.message}" if path else error.message
        error_messages.append(message)

    return False, error_messages


def validate_plugin_variables(
    variables: Dict[str, str], env_vars: Optional[Dict[str, str]] = None
) -> Tuple[bool, List[str]]:
    """Validate plugin variables and their resolution.

    Args:
        variables: Dictionary of plugin variables
        env_vars: Optional dictionary of environment variables for testing

    Returns:
        A tuple of (is_valid, error_messages)
    """
    errors = []

    for key, value in variables.items():
        # Check for environment variable references
        if value.startswith("$"):
            env_var = value[1:]  # Remove $
            if env_vars is not None:
                # Use provided env vars for testing
                if env_var not in env_vars:
                    errors.append(f"Environment variable not found: {env_var}")
            else:
                # In real usage, we don't validate env var existence
                # as they might be set later or in different environments
                pass

        # Validate key format
        if not key.isidentifier():
            errors.append(
                f"Invalid variable name '{key}': must be a valid Python identifier"
            )

    return len(errors) == 0, errors
