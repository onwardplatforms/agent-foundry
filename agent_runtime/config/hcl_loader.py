# agent_runtime/config/hcl_loader.py

import os
import logging
from typing import Dict, Any, List, Union, Optional
import hcl2
from pathlib import Path
import re

from ..validation import get_schema_validator, ValidationContext

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Base class for configuration-related errors."""

    pass


class InterpolationError(ConfigurationError):
    """Error during value interpolation."""

    def __init__(self, message: str, path: List[str]):
        self.path = path
        super().__init__(f"{' -> '.join(path)}: {message}")


class ConversionError(ConfigurationError):
    """Error during value type conversion."""

    def __init__(self, value: Any, target_type: str, message: str):
        super().__init__(f"Failed to convert '{value}' to {target_type}: {message}")


class ValueConverter:
    """Handles type conversion of configuration values."""

    @staticmethod
    def convert(value: Any, target_type: str) -> Any:
        """Convert a value to the specified type."""
        try:
            return ValueConverter._convert_value(value, target_type)
        except (ValueError, TypeError) as e:
            raise ConversionError(value, target_type, str(e))

    @staticmethod
    def _convert_value(value: Any, target_type: str) -> Any:
        """Internal conversion implementation."""
        # If value is already the right type, return it
        if target_type == "number" and isinstance(value, (int, float)):
            return value
        elif target_type == "float" and isinstance(value, float):
            return value
        elif target_type == "int" and isinstance(value, int):
            return value
        elif target_type == "bool" and isinstance(value, bool):
            return value
        elif target_type == "string" and isinstance(value, str):
            return value

        # Otherwise convert string values
        if isinstance(value, str):
            if target_type == "number":
                try:
                    if "." in value:
                        return float(value)
                    return int(value)
                except (ValueError, TypeError):
                    return float(value)
            elif target_type == "float":
                return float(value)
            elif target_type == "int":
                return int(value)
            elif target_type == "bool":
                return value.lower() in ("true", "1", "yes", "on")
            elif target_type == "string":
                return value

        # For non-string values that don't match target type, convert through string
        return ValueConverter._convert_value(str(value), target_type)


class ValueInterpolator:
    """Handles value interpolation and reference resolution."""

    def __init__(
        self, variables: Dict[str, Any], models: Dict[str, Any], plugins: Dict[str, Any]
    ):
        self.variables = variables
        self.models = models
        self.plugins = plugins
        self._current_path: List[str] = []

    def interpolate(self, value: Any, path: Optional[List[str]] = None) -> Any:
        """Interpolate a value, including basic ternary conditionals and references."""
        if path is not None:
            self._current_path = path

        try:
            return self._interpolate_value(value)
        except InterpolationError:
            raise
        except Exception as e:
            raise InterpolationError(str(e), self._current_path)

    def _interpolate_value(self, value: Any) -> Any:
        """Internal interpolation implementation."""
        if isinstance(value, str):
            # 1) If there's a top-level ? and :, try ternary parse
            if "?" in value and ":" in value and not value.startswith("${"):
                new_val = self._evaluate_ternary(value)
                if new_val != value:
                    return new_val

            # 2) Handle ${...} references
            pattern = re.compile(r"\$\{([^}]+)\}")
            result = value
            while True:
                match = pattern.search(result)
                if not match:
                    break
                full_expr = match.group(0)  # '${...}'
                inner_expr = match.group(1).strip()
                # If there's a ? and :, attempt ternary
                if "?" in inner_expr and ":" in inner_expr:
                    sub_val = self._evaluate_ternary(inner_expr)
                else:
                    sub_val = self._basic_ref_interpolation(inner_expr)

                if isinstance(sub_val, dict):
                    return sub_val  # Return dict directly if needed

                if not isinstance(sub_val, str):
                    sub_val = str(sub_val)
                start, end = match.span()
                result = result[:start] + sub_val + result[end:]
            return result

        elif isinstance(value, dict):
            return {k: self._interpolate_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(v) for v in value]
        return value

    def _evaluate_ternary(self, expr: str) -> Any:
        """Evaluate a ternary expression."""
        pattern = re.compile(r"^(.*?)\?(.*?)\:(.*)$")
        m = pattern.match(expr.strip())
        if not m:
            return expr

        condition_part = m.group(1).strip()
        true_part = m.group(2).strip()
        false_part = m.group(3).strip()

        # Evaluate condition
        cond_str = str(self._interpolate_value(condition_part))

        try:
            # Block builtins for safety
            result_bool = eval(cond_str, {"__builtins__": None}, {})
        except Exception as e:
            logger.debug(f"Failed to evaluate condition '{cond_str}': {e}")
            result_bool = False

        chosen_str = true_part if result_bool else false_part
        return self._interpolate_value(chosen_str)

    def _basic_ref_interpolation(self, expr: str) -> Any:
        """Handle basic references like var.x, model.y, plugin.z."""
        parts = expr.split(".")
        if len(parts) < 2:
            return expr

        ref_type = parts[0]
        if ref_type == "var" and len(parts) == 2:
            var_name = parts[1]
            var_def = self.variables.get(var_name)
            if var_def is None:
                raise InterpolationError(
                    f"Variable '{var_name}' not found", self._current_path
                )
            # Return just the default value from the variable definition
            if isinstance(var_def, dict):
                return var_def.get("default", "")
            return var_def

        elif ref_type == "model" and len(parts) == 2:
            model_name = parts[1]
            result = self.models.get(model_name)
            if result is None:
                raise InterpolationError(
                    f"Model '{model_name}' not found", self._current_path
                )
            return result

        elif ref_type == "plugin" and len(parts) == 3:
            plugin_type, plugin_name = parts[1:]
            plugin_key = f"{plugin_type}:{plugin_name}"
            result = self.plugins.get(plugin_key)
            if result is None:
                raise InterpolationError(
                    f"Plugin '{plugin_key}' not found", self._current_path
                )
            return result

        return expr


class BlockProcessor:
    """Handles processing of specific block types."""

    def __init__(self, interpolator: ValueInterpolator):
        self.interpolator = interpolator

    def process_model(
        self, model_name: str, model_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a model block configuration."""
        logger.debug("Processing model '%s': %s", model_name, model_config)
        processed_config = dict(model_config)  # copy

        # Replace variable references in settings if any
        if "settings" in processed_config:
            settings = self.interpolator.interpolate(
                processed_config["settings"], ["model", model_name, "settings"]
            )
            logger.debug("Interpolated settings: %s", settings)

            # If settings is a list with one item (HCL block syntax), extract the item
            if isinstance(settings, list) and len(settings) == 1:
                settings = settings[0]

            # Mark settings as a block if it came from HCL block syntax
            if isinstance(settings, dict) and settings.get("_is_block", False):
                del settings["_is_block"]

            setting_types = {
                "temperature": "float",
                "max_tokens": "int",
                "top_p": "float",
                "frequency_penalty": "float",
                "presence_penalty": "float",
                "top_k": "int",
                "repeat_penalty": "float",
                "stop": "string",
            }

            if isinstance(settings, dict):
                for key, value in settings.items():
                    if key in setting_types:
                        original = settings[key]
                        settings[key] = ValueConverter.convert(
                            value, setting_types[key]
                        )
                        logger.debug(
                            "Converted setting %s: %s => %s",
                            key,
                            original,
                            settings[key],
                        )

            processed_config["settings"] = settings

        # Ensure required fields
        if "provider" not in processed_config:
            logger.error("Model '%s' missing required 'provider' field", model_name)
        if "name" not in processed_config:
            logger.error("Model '%s' missing required 'name' field", model_name)

        logger.debug("Final model config for '%s': %s", model_name, processed_config)
        return processed_config

    def process_plugin(
        self, plugin_key: str, plugin_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a plugin block configuration."""
        logger.debug("Processing plugin '%s': %s", plugin_key, plugin_config)
        processed_config = dict(plugin_config)  # copy

        # Basic checks
        if "source" not in processed_config:
            raise ConfigurationError(
                f"Plugin {plugin_key} is missing required 'source' field"
            )

        plugin_type, plugin_name = plugin_key.split(":")

        # Check plugin type
        if plugin_type == "local":
            if "version" in processed_config:
                raise ConfigurationError(
                    f"Local plugin {plugin_name} cannot specify a version"
                )
            if not (
                processed_config["source"].startswith("./")
                or processed_config["source"].startswith("../")
            ):
                raise ConfigurationError(
                    f"Local plugin {plugin_name} source must start with ./ or ../"
                )
        elif plugin_type == "remote":
            if "version" not in processed_config:
                raise ConfigurationError(
                    f"Remote plugin {plugin_name} is missing required 'version' field"
                )

        # Ensure variables exists and interpolate them
        if "variables" not in processed_config:
            processed_config["variables"] = {}
        processed_config["variables"]["name"] = plugin_name

        # Interpolate all variable values
        if processed_config["variables"]:
            processed_config["variables"] = self.interpolator.interpolate(
                processed_config["variables"], ["plugin", plugin_key, "variables"]
            )

        logger.debug("Final plugin config for '%s': %s", plugin_key, processed_config)
        return processed_config

    def process_agent(
        self, agent_name: str, agent_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process an agent block configuration."""
        logger.debug("Processing agent '%s': %s", agent_name, agent_config)
        processed_config = dict(agent_config)  # copy

        # Replace model references
        if "model" in processed_config:
            model_ref = processed_config["model"]
            if isinstance(model_ref, str):
                model_ref = self.interpolator.interpolate(
                    model_ref, ["agent", agent_name, "model"]
                )
                processed_config["model"] = model_ref

        # Replace plugin references
        if "plugins" in processed_config:
            plugins = []
            for i, plugin_ref in enumerate(processed_config["plugins"]):
                if isinstance(plugin_ref, str):
                    plugin_ref = self.interpolator.interpolate(
                        plugin_ref, ["agent", agent_name, f"plugins[{i}]"]
                    )
                    if plugin_ref is not None:
                        plugins.append(plugin_ref)
                else:
                    plugins.append(plugin_ref)
            processed_config["plugins"] = plugins

        # Interpolate any remaining top-level agent attributes
        for key, value in list(processed_config.items()):
            if key not in ["model", "plugins"]:
                processed_config[key] = self.interpolator.interpolate(
                    value, ["agent", agent_name, key]
                )

        logger.debug("Final agent config for '%s': %s", agent_name, processed_config)
        return processed_config


class BlockMerger:
    """Handles merging of HCL blocks."""

    def __init__(self):
        self.variables = {}
        self.models = {}
        self.plugins = {}
        self.agents = {}
        self.runtime = {}

    def merge_config(self, config: Dict[str, Any]) -> None:
        """Merge a configuration dictionary into the current state."""
        logger.debug("Merging configuration: %s", config)
        # HCL structure is different from JSON - blocks are lists of single-key dicts
        for block_type, blocks in config.items():
            logger.debug("Processing block type '%s': %s", block_type, blocks)
            if not isinstance(blocks, list):
                logger.debug("Skipping non-list block: %s", blocks)
                continue

            for block in blocks:
                if not isinstance(block, dict):
                    logger.debug("Skipping invalid block: %s", block)
                    continue

                if block_type == "runtime":
                    # Store the entire runtime block
                    self.runtime = self._convert_block_values(block)
                elif block_type == "variable":
                    block_name, block_value = next(iter(block.items()))
                    self.variables[block_name] = self._convert_block_values(block_value)
                elif block_type == "model":
                    block_name, block_value = next(iter(block.items()))
                    self.models[block_name] = self._convert_block_values(block_value)
                elif block_type == "plugin":
                    # Handle dual identifiers for plugins, e.g. plugin "local" "echo"
                    if len(block) != 1:
                        logger.debug("Skipping invalid plugin block: %s", block)
                        continue
                    plugin_type, inner_block = next(iter(block.items()))
                    if not isinstance(inner_block, dict) or len(inner_block) != 1:
                        logger.debug(
                            "Skipping invalid plugin inner block: %s", inner_block
                        )
                        continue
                    plugin_name, plugin_value = next(iter(inner_block.items()))
                    # Store with combined key
                    self.plugins[f"{plugin_type}:{plugin_name}"] = {
                        "type": plugin_type,
                        "name": plugin_name,
                        **self._convert_block_values(plugin_value),
                    }
                elif block_type == "agent":
                    block_name, block_value = next(iter(block.items()))
                    self.agents[block_name] = self._convert_block_values(block_value)

    def _convert_block_values(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """Convert values in a block based on their apparent types."""
        result = {}
        for key, value in block.items():
            if isinstance(value, str):
                # Try to convert strings that look like numbers or booleans
                if value.lower() in ("true", "false"):
                    result[key] = value.lower() == "true"
                else:
                    try:
                        if "." in value:
                            result[key] = float(value)
                        else:
                            result[key] = int(value)
                    except ValueError:
                        result[key] = value
            elif isinstance(value, dict):
                # If this is a block (no equals sign in HCL), mark it
                if value.get("_block", False):
                    value["_is_block"] = True
                    del value["_block"]
                result[key] = self._convert_block_values(value)
            elif isinstance(value, list):
                result[key] = [
                    self._convert_block_values(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # For non-string values (already numbers, bools, etc), use as-is
                result[key] = value
                logger.debug("Using value as-is: %s = %s (%s)", key, value, type(value))
        return result


class HCLConfigLoader:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        # Initialize state variables
        self.variables = {}
        self.models = {}
        self.plugins = {}
        self.agents = {}
        self.runtime = {}

        self.block_merger = BlockMerger()
        self.interpolator = ValueInterpolator(self.variables, self.models, self.plugins)
        self.block_processor = BlockProcessor(self.interpolator)

    def _merge_config(self, config: Dict[str, Any]) -> None:
        """Merge a configuration dictionary into the current state."""
        self.block_merger.merge_config(config)
        # Update references after merging
        self.variables = self.block_merger.variables
        self.models = self.block_merger.models
        self.plugins = self.block_merger.plugins
        self.agents = self.block_merger.agents
        self.runtime = self.block_merger.runtime

        # Update interpolator references
        self.interpolator.variables = self.variables
        self.interpolator.models = self.models
        self.interpolator.plugins = self.plugins

    def _process_variables(self):
        """Process all variables after merging configurations"""
        logger.debug("Processing variables: %s", self.variables)
        processed_vars = {}
        for var_name, var_config in self.variables.items():
            # Variables should already be type-converted from merge
            if isinstance(var_config, dict):
                processed_vars[var_name] = var_config.get("default", "")
            else:
                processed_vars[var_name] = var_config
        logger.debug("Processed variables: %s", processed_vars)
        self.variables = processed_vars

    def _process_models(self):
        """Process all models after merging configurations"""
        logger.debug("Processing models: %s", self.models)
        processed_models = {}
        for model_name, model_config in self.models.items():
            processed_models[model_name] = self.block_processor.process_model(
                model_name, model_config
            )
        self.models = processed_models

    def _process_plugins(self):
        """Process all plugins after merging configurations"""
        logger.debug("Processing plugins: %s", self.plugins)
        processed_plugins = {}
        for plugin_key, plugin_config in self.plugins.items():
            processed_plugins[plugin_key] = self.block_processor.process_plugin(
                plugin_key, plugin_config
            )
        self.plugins = processed_plugins

    def _process_agents(self):
        """Process all agents after merging configurations"""
        logger.debug("Processing agents: %s", self.agents)
        processed_agents = {}
        for agent_name, agent_config in self.agents.items():
            processed_agents[agent_name] = self.block_processor.process_agent(
                agent_name, agent_config
            )
        self.agents = processed_agents

    def load_config(self) -> Dict[str, Any]:
        """Load and merge all HCL files in the directory, then validate them all."""
        all_errors = []
        raw_configs = []

        # Find all .hcl files
        hcl_files = list(self.config_dir.glob("*.hcl"))
        logger.debug("Found HCL files: %s", [str(f) for f in hcl_files])

        # First load & validate each raw file
        validator = get_schema_validator()

        for hcl_file in hcl_files:
            file_errors = []
            logger.debug("Loading HCL file: %s", hcl_file)
            with open(hcl_file) as f:
                raw_config = hcl2.load(f)
                logger.debug("Raw HCL content from %s: %s", hcl_file, raw_config)
                raw_configs.append(raw_config)

                # Create a validation context for this file
                context = ValidationContext()

                # Validate each block type
                for block_type, blocks in raw_config.items():
                    if not isinstance(blocks, list):
                        continue

                    for block_instance in blocks:
                        if block_type == "runtime":
                            validator.validate_type(block_instance, "runtime", context)

                        elif block_type == "variable":
                            for label, block_content in block_instance.items():
                                with context.path("variable", label):
                                    validator.validate_type(
                                        block_content, "variable", context
                                    )

                        elif block_type == "model":
                            for label, block_content in block_instance.items():
                                with context.path("model", label):
                                    validator.validate_type(
                                        block_content, "model", context
                                    )

                        elif block_type == "plugin":
                            for plugin_type, inner_block in block_instance.items():
                                for plugin_name, block_content in inner_block.items():
                                    with context.path(
                                        "plugin", f"{plugin_type}:{plugin_name}"
                                    ):
                                        validator.validate_type(
                                            block_content, "plugin", context
                                        )

                        elif block_type == "agent":
                            for label, block_content in block_instance.items():
                                with context.path("agent", label):
                                    # Create a copy for validation
                                    validation_content = dict(block_content)

                                    # For model references, validate inline definitions
                                    if "model" in validation_content:
                                        model_value = validation_content["model"]
                                        if isinstance(model_value, dict):
                                            with context.path("model"):
                                                validator.validate_type(
                                                    model_value, "model", context
                                                )

                                    # For plugin references, validate inline definitions
                                    if "plugins" in validation_content:
                                        plugins = validation_content["plugins"]
                                        if isinstance(plugins, list):
                                            for i, plugin in enumerate(plugins):
                                                if isinstance(plugin, dict):
                                                    with context.path(f"plugin[{i}]"):
                                                        validator.validate_type(
                                                            plugin, "plugin", context
                                                        )

                                    # Validate the agent block itself
                                    validator.validate_type(
                                        validation_content, "agent", context
                                    )

                # If we have errors in this file, record them
                if context.has_errors:
                    file_errors.append(f"In file {hcl_file.name}:")
                    file_errors.extend(f"  {error}" for error in context.errors)
                    file_errors.append("")  # blank line
                    all_errors.extend(file_errors)

        # If we have any validation errors across any file, raise them all
        if all_errors:
            error_msg = "Configuration validation failed:\n\n"
            error_msg += "\n".join(all_errors)
            raise RuntimeError(error_msg)

        # If validation succeeded, merge configs
        for raw_config in raw_configs:
            self._merge_config(raw_config)
            logger.debug("After merging config, state is: plugins=%s", self.plugins)

        # After merging, do further processing (not schema errors but typed references, etc.)
        self._process_variables()
        self._process_models()
        self._process_plugins()
        self._process_agents()

        return {
            "runtime": self.runtime,
            "variable": self.variables,
            "model": self.models,
            "plugin": self.plugins,
            "agent": self.agents,
        }

    def _resolve_reference(self, ref: str) -> Any:
        """Resolve a reference like var.x, model.name, plugin.type.name, etc."""
        logger.debug("Resolving reference: %s (type: %s)", ref, type(ref))

        if not isinstance(ref, str):
            return ref

        parts = ref.split(".")
        if len(parts) < 2:
            return ref

        ref_type = parts[0]

        if ref_type == "var" and len(parts) == 2:
            var_name = parts[1]
            result = self.variables.get(var_name)
            if result is None:
                logger.warning("Variable '%s' not found", var_name)
                return ""
            return result

        elif ref_type == "model" and len(parts) == 2:
            model_name = parts[1]
            return self.models.get(model_name)

        elif ref_type == "plugin" and len(parts) == 3:
            plugin_type, plugin_name = parts[1:]
            plugin_key = f"{plugin_type}:{plugin_name}"
            return self.plugins.get(plugin_key)

        return ref
