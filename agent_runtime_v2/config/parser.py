"""Configuration parsing and validation module."""

import yaml
import json
import jsonschema
import re
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from uuid import uuid4

from dotenv import load_dotenv

from .types import AgentConfig, ModelConfig, PluginConfig
from ..plugins.sources import LocalPluginSource, GitHubPluginSource
from ..utils import LogLevel

logger = logging.getLogger(__name__)

# Environment variable pattern: ${{ env.VARIABLE_NAME }}
ENV_VAR_PATTERN = re.compile(r"\$\{\{\s*env\.([A-Za-z0-9_]+)\s*\}\}")


def load_agent_config(file_path: Union[str, Path]) -> AgentConfig:
    """Load agent configuration from YAML.

    Args:
        file_path: Path to the YAML configuration file

    Returns:
        AgentConfig instance

    Raises:
        FileNotFoundError: If the configuration file doesn't exist
        jsonschema.exceptions.ValidationError: If the configuration is invalid
    """
    file_path = Path(file_path)
    logger.info(f"Loading agent configuration from {file_path}")

    if not file_path.exists():
        logger.error(f"Configuration file not found: {file_path}")
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    # 1. Load YAML file
    try:
        with open(file_path, "r") as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded YAML configuration: {config}")
    except Exception as e:
        logger.error(f"Error loading YAML: {e}")
        raise ValueError(f"Error loading YAML configuration: {e}")

    # 2. Validate against schema
    schema_path = Path(__file__).parent / "schema.json"
    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)
        jsonschema.validate(config, schema)
        logger.debug("Configuration validated successfully")
    except jsonschema.exceptions.ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise ValueError(f"Error validating configuration: {e}")

    # 3. Resolve environment variables
    load_dotenv()  # Load .env file if exists
    config = resolve_environment_variables(config)

    # 4. Convert to AgentConfig
    return create_agent_config(config, file_path)


def resolve_environment_variables(config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve environment variables in configuration.

    Args:
        config: Configuration dictionary

    Returns:
        Configuration with environment variables resolved
    """
    if isinstance(config, dict):
        # Special handling for env section - skip env var resolution for keys
        if "env" in config and isinstance(config["env"], dict):
            # Create a copy of the env section and resolve env vars in values
            env_section = config["env"].copy()
            for key, value in env_section.items():
                if isinstance(value, str):
                    # Only resolve env vars in values, not keys
                    env_section[key] = resolve_env_vars_in_string(value)

            # Update other keys normally
            result = {
                k: resolve_environment_variables(v)
                for k, v in config.items()
                if k != "env"
            }
            result["env"] = env_section
            return result
        else:
            return {k: resolve_environment_variables(v) for k, v in config.items()}

    elif isinstance(config, list):
        return [resolve_environment_variables(item) for item in config]
    elif isinstance(config, str):
        return resolve_env_vars_in_string(config)
    else:
        return config


def resolve_env_vars_in_string(text: str) -> str:
    """Resolve environment variables in a string.

    Args:
        text: String that may contain environment variable references

    Returns:
        String with environment variables resolved
    """
    if not isinstance(text, str):
        return text

    def replace_env_var(match):
        var_name = match.group(1)
        var_value = os.environ.get(var_name)
        if var_value is None:
            logger.warning(f"Environment variable not found: {var_name}")
            return f"${{{{{var_name}}}}}"  # Return original if not found
        return var_value

    return ENV_VAR_PATTERN.sub(replace_env_var, text)


def create_agent_config(yaml_config: Dict[str, Any], config_path: Path) -> AgentConfig:
    """Convert YAML configuration to AgentConfig object.

    Args:
        yaml_config: Parsed YAML configuration
        config_path: Path to the configuration file (for resolving relative paths)

    Returns:
        AgentConfig instance
    """
    logger.debug("Creating AgentConfig from YAML")

    # Generate agent ID if not provided
    agent_id = yaml_config.get("id", f"agent-{uuid4().hex[:8]}")

    # Create model config
    model_config = ModelConfig(
        provider=yaml_config["model"]["provider"],
        model=yaml_config["model"]["model"],
        temperature=yaml_config["model"].get("temperature", 0.7),
        max_tokens=yaml_config["model"].get("max_tokens"),
        top_p=yaml_config["model"].get("top_p"),
        frequency_penalty=yaml_config["model"].get("frequency_penalty"),
        presence_penalty=yaml_config["model"].get("presence_penalty"),
    )

    # Create plugin configs
    plugin_configs = []
    for plugin_yaml in yaml_config.get("plugins", []):
        source_yaml = plugin_yaml["source"]
        source_type = source_yaml["type"]

        if source_type == "local":
            # Resolve relative path from config file location
            plugin_path = source_yaml["path"]
            if not os.path.isabs(plugin_path):
                plugin_path = (config_path.parent / plugin_path).resolve()
            source = LocalPluginSource(Path(plugin_path))
        elif source_type == "github":
            source = GitHubPluginSource(
                repo_url=source_yaml["repo"],
                version_tag=source_yaml["version"],
                plugin_path=source_yaml["plugin_path"],
            )
        else:
            logger.error(f"Unknown plugin source type: {source_type}")
            raise ValueError(f"Unknown plugin source type: {source_type}")

        plugin_configs.append(
            PluginConfig(source=source, variables=plugin_yaml.get("variables", {}))
        )

    # Set log level
    log_level = LogLevel.NONE  # Default

    # Create agent config
    return AgentConfig(
        id=agent_id,
        name=yaml_config["name"],
        description=yaml_config.get("description", ""),
        system_prompt=yaml_config["system_prompt"],
        model=model_config,
        plugins=plugin_configs,
        log_level=log_level,
    )
