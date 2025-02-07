"""Tests for the validation module."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from agent_runtime.validation import validate_agent_config


@pytest.fixture
def valid_config() -> Dict[str, Any]:
    """Create a valid agent configuration for testing."""
    return {
        "name": "test-agent",
        "description": "A test agent",
        "system_prompt": "You are a test agent",
        "model": {
            "provider": "openai",
            "name": "gpt-3.5-turbo",
            "settings": {"temperature": 0.7, "max_tokens": 1000},
        },
        "plugins": [
            {
                "name": "search",
                "source": "github.com/example/search-plugin",
                "version": "v1.0.0",
                "variables": {"api_key": "$SEARCH_API_KEY"},
            }
        ],
    }


@pytest.fixture
def config_file(tmp_path: Path, valid_config: Dict[str, Any]) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "agent.json"
    with open(config_file, "w") as f:
        json.dump(valid_config, f)
    return config_file


def test_validate_valid_config(valid_config: Dict[str, Any]) -> None:
    """Test validation of a valid configuration dictionary."""
    is_valid, errors = validate_agent_config(valid_config)
    assert is_valid
    assert not errors


def test_validate_valid_config_file(config_file: Path) -> None:
    """Test validation of a valid configuration file."""
    is_valid, errors = validate_agent_config(config_file)
    assert is_valid
    assert not errors


def test_validate_missing_required_fields(valid_config: Dict[str, Any]) -> None:
    """Test validation fails when required fields are missing."""
    # Remove required fields
    del valid_config["name"]
    del valid_config["model"]

    is_valid, errors = validate_agent_config(valid_config)
    assert not is_valid
    assert len(errors) == 2
    assert any("name" in error for error in errors)
    assert any("model" in error for error in errors)


def test_validate_invalid_model_settings(valid_config: Dict[str, Any]) -> None:
    """Test validation fails with invalid model settings."""
    # Set invalid temperature
    valid_config["model"]["settings"]["temperature"] = 2.0

    is_valid, errors = validate_agent_config(valid_config)
    assert not is_valid
    assert len(errors) == 1
    assert "temperature" in errors[0]


def test_validate_invalid_plugin_config(valid_config: Dict[str, Any]) -> None:
    """Test validation fails with invalid plugin configuration."""
    # Add plugin without required fields
    valid_config["plugins"].append(
        {
            "name": "invalid-plugin"
            # Missing source and version
        }
    )

    is_valid, errors = validate_agent_config(valid_config)
    assert not is_valid
    assert len(errors) == 2  # Missing both source and version
    assert any("source" in error for error in errors)
    assert any("version" in error for error in errors)


def test_validate_nonexistent_file() -> None:
    """Test validation fails with nonexistent file."""
    is_valid, errors = validate_agent_config(Path("nonexistent.json"))
    assert not is_valid
    assert len(errors) == 1
    assert "File not found" in errors[0]


def test_validate_invalid_json_file(tmp_path: Path) -> None:
    """Test validation fails with invalid JSON file."""
    invalid_json_file = tmp_path / "invalid.json"
    with open(invalid_json_file, "w") as f:
        f.write("{ invalid json }")

    is_valid, errors = validate_agent_config(invalid_json_file)
    assert not is_valid
    assert len(errors) == 1
    assert "Invalid JSON" in errors[0]


def test_validate_plugin_variables(valid_config: Dict[str, Any]) -> None:
    """Test validation of plugin variables."""
    # Test valid environment variable reference
    plugin = valid_config["plugins"][0]
    plugin["variables"]["api_key"] = "$VALID_ENV_VAR"
    is_valid, errors = validate_agent_config(valid_config)
    assert is_valid
    assert not errors

    # Test invalid environment variable reference
    plugin["variables"]["api_key"] = "INVALID_ENV_VAR"  # Missing $
    is_valid, errors = validate_agent_config(valid_config)
    assert not is_valid
    assert len(errors) == 1
    assert "environment variable" in errors[0]
