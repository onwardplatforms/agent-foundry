"""Validation utilities for agent configuration."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    config_path: Path,
) -> Tuple[bool, List[str]]:
    """Validate an agent configuration file against the schema.

    Args:
        config_path: Path to the agent configuration file

    Returns:
        A tuple of (is_valid, error_messages)
    """
    # Load schema
    schema = load_schema()

    # Load config
    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in config file: {e}"]
    except FileNotFoundError:
        return False, [f"Config file not found: {config_path}"]

    # Validate against schema
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(config))

    if not errors:
        return True, []

    # Format error messages
    error_messages = []
    for error in errors:
        path = " -> ".join(str(p) for p in error.path)
        message = f"{path}: {error.message}" if path else error.message
        error_messages.append(message)

    return False, error_messages
