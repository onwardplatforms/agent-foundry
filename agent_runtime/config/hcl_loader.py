import os
import logging
from typing import Dict, Any, List
import hcl2
from pathlib import Path
from glob import glob
import re

logger = logging.getLogger(__name__)


class HCLConfigLoader:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.variables = {}
        self.models = {}
        self.plugins = {}
        self.agents = {}
        self.runtime = {}

    def _load_hcl_file(self, file_path: str) -> Dict[str, Any]:
        """Load and parse HCL file."""
        logger.debug("Loading HCL file: %s", file_path)
        with open(file_path, "r") as f:
            config = hcl2.load(f)
            logger.debug("Raw HCL content: %s", config)
            return config

    def _merge_config(self, config: Dict[str, Any]):
        """Merge a configuration dictionary into the current state"""
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
                    # Handle dual identifiers for plugins
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

    def _process_variables(self):
        """Process all variables after merging configurations"""
        logger.debug("Processing variables: %s", self.variables)
        processed_vars = {}
        for var_name, var_config in self.variables.items():
            # Variables should already be type-converted from merge
            processed_vars[var_name] = var_config.get("default")
        logger.debug("Processed variables: %s", processed_vars)
        self.variables = processed_vars

    def _evaluate_ternary(self, expr: str) -> str:
        """
        Given something like 'var.environment == "prod" ? "big" : "small"',
        parse it, evaluate the condition, and return "big" or "small".
        We only handle a single '? :', no nesting.
        """
        # e.g. expr might be: var.environment == "prod" ? "big" : "small"
        pattern = re.compile(r"^(.*?)\?(.*?)\:(.*)$")
        m = pattern.match(expr.strip())
        if not m:
            # If there's no match, just return expr as-is
            return expr

        condition_part = m.group(1).strip()
        true_part = m.group(2).strip()
        false_part = m.group(3).strip()

        # Evaluate condition. We'll do a naive approach:
        # 1) Interpolate references in condition_part
        cond_str = str(self._interpolate_value(condition_part))
        # 2) Evaluate as a python expression (careful if untrusted!)
        try:
            # We'll block builtins for safety
            result_bool = eval(cond_str, {"__builtins__": None}, {})
        except Exception as e:
            logger.debug(f"Failed to evaluate condition '{cond_str}': {e}")
            # fallback => treat as false
            result_bool = False

        # Then pick true_part or false_part
        chosen_str = true_part if result_bool else false_part
        # also interpolate references inside chosen_str
        chosen_str = str(self._interpolate_value(chosen_str))
        return chosen_str

    def _interpolate_value(self, value: Any) -> Any:
        """Interpolate a value, including basic ternary conditionals and references."""
        logger.debug("Interpolating value: %s (type: %s)", value, type(value))
        if isinstance(value, str):
            # 1) If there's a top-level "?" and ":", try ternary parse
            #    but only if we don't see braces (like "prefix-${...}")
            #    We'll handle the simpler expression-only scenario
            if "?" in value and ":" in value and not value.startswith("${"):
                # naive approach, see if we can parse it as a ternary
                # caution: won't handle partial "prefix- x ? y : z -suffix"
                new_val = self._evaluate_ternary(value)
                if new_val != value:
                    return new_val

            # 2) Handle ${...} references or conditionals
            # We'll do multiple passes if there's more than one
            pattern = re.compile(r"\$\{([^}]+)\}")
            result = value
            while True:
                match = pattern.search(result)
                if not match:
                    break
                full_expr = match.group(0)  # e.g. '${var.something}'
                inner_expr = match.group(1).strip()  # might contain references or ? :
                # If there's a ? and :, attempt ternary first
                if "?" in inner_expr and ":" in inner_expr:
                    # Evaluate as ternary
                    sub_val = self._evaluate_ternary(inner_expr)
                else:
                    # Otherwise do normal reference interpolation
                    sub_val = self._basic_ref_interpolation(inner_expr)

                # If sub_val is a dict, return it directly
                if isinstance(sub_val, dict):
                    return sub_val

                # Convert to str if not already
                if not isinstance(sub_val, str):
                    sub_val = str(sub_val)
                # Replace
                start, end = match.span()
                result = result[:start] + sub_val + result[end:]
            return result

        elif isinstance(value, dict):
            return {k: self._interpolate_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(v) for v in value]
        return value

    def _basic_ref_interpolation(self, expr: str) -> Any:
        """
        Handle references like var.x, model.y, plugin.z.
        Uses the generic reference resolution system.
        """
        return self._resolve_reference(expr)

    def _convert_value(self, value: Any, target_type: str) -> Any:
        """Convert a value to the specified type.

        Args:
            value: The value to convert
            target_type: The type to convert to ('number', 'string', 'int', 'float', 'bool')

        Returns:
            The converted value
        """
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
        return self._convert_value(str(value), target_type)

    def _process_models(self):
        """Process all models after merging configurations"""
        logger.debug("Processing models: %s", self.models)
        for model_name, model_config in self.models.items():
            logger.debug("Processing model '%s': %s", model_name, model_config)

            # Replace variable references
            if "settings" in model_config:
                settings = self._interpolate_value(model_config["settings"])
                logger.debug("Interpolated settings: %s", settings)

                # Get type information from the model config
                setting_types = model_config.get("setting_types", {})
                if not setting_types:
                    # Default type mappings if not specified
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
                logger.debug("Using setting types: %s", setting_types)

                # Convert settings to proper types
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        if key in setting_types:
                            original = settings[key]
                            settings[key] = self._convert_value(
                                value, setting_types[key]
                            )
                            logger.debug(
                                "Converted setting %s: %s => %s",
                                key,
                                original,
                                settings[key],
                            )

                model_config["settings"] = settings

            # Ensure other required fields
            if "provider" not in model_config:
                logger.error("Model '%s' missing required 'provider' field", model_name)
            if "name" not in model_config:
                logger.error("Model '%s' missing required 'name' field", model_name)

            logger.debug("Final model config for '%s': %s", model_name, model_config)

    def _process_plugins(self):
        """Process and validate all plugins after merging configurations"""
        logger.debug("Processing plugins: %s", self.plugins)
        for plugin_key, plugin_config in self.plugins.items():
            # Validate plugin configuration
            if "source" not in plugin_config:
                raise ValueError(
                    f"Plugin {plugin_key} is missing required 'source' field"
                )

            plugin_type = plugin_config["type"]
            plugin_name = plugin_config["name"]

            # Validate based on plugin type
            if plugin_type == "local":
                if "version" in plugin_config:
                    raise ValueError(
                        f"Local plugin {plugin_name} cannot specify a version"
                    )
                if not (
                    plugin_config["source"].startswith("./")
                    or plugin_config["source"].startswith("../")
                ):
                    raise ValueError(
                        f"Local plugin {plugin_name} source must start with ./ or ../"
                    )
            elif plugin_type == "remote":
                if "version" not in plugin_config:
                    raise ValueError(
                        f"Remote plugin {plugin_name} is missing required 'version' field"
                    )
            else:
                raise ValueError(
                    f"Invalid plugin type '{plugin_type}' for plugin {plugin_name}"
                )

            # Add plugin name to variables for reference
            if "variables" not in plugin_config:
                plugin_config["variables"] = {}
            plugin_config["variables"]["name"] = plugin_name

        logger.debug("Processed plugins: %s", self.plugins)

    def _resolve_reference(self, ref: str) -> Any:
        """Resolve a reference like 'model.name' or 'plugin.type.name' to its actual value."""
        logger.debug("Resolving reference: %s (type: %s)", ref, type(ref))

        if not isinstance(ref, str):
            logger.debug("Reference is not a string, returning as-is: %s", ref)
            return ref

        parts = ref.split(".")
        if len(parts) < 2:
            logger.debug("Reference has insufficient parts, returning as-is: %s", ref)
            return ref

        ref_type = parts[0]
        logger.debug("Reference type: %s, parts: %s", ref_type, parts)

        if ref_type == "var" and len(parts) == 2:
            result = self.variables.get(parts[1])
            logger.debug("Resolved variable reference: %s => %s", ref, result)
            return result

        elif ref_type == "model" and len(parts) == 2:
            model_name = parts[1]
            if model_name not in self.models:
                logger.debug("Model not found: %s", model_name)
                return None

            # Get the model config and ensure it has required fields
            model_config = dict(self.models[model_name])
            logger.debug("Found model config: %s", model_config)

            if not all(k in model_config for k in ["provider", "name"]):
                logger.error("Model %s missing required fields", model_name)
                return None

            # Ensure settings are properly processed
            if "settings" in model_config:
                settings = model_config["settings"]
                if isinstance(settings, dict):
                    # Convert known setting types
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
                    processed_settings = {}
                    for key, value in settings.items():
                        if key in setting_types:
                            processed_settings[key] = self._convert_value(
                                value, setting_types[key]
                            )
                        else:
                            processed_settings[key] = value
                    model_config["settings"] = processed_settings
                    logger.debug("Processed model settings: %s", processed_settings)

            logger.debug("Returning resolved model config: %s", model_config)
            return model_config

        elif ref_type == "plugin" and len(parts) == 3:
            plugin_type, plugin_name = parts[1:]
            plugin_key = f"{plugin_type}:{plugin_name}"
            if plugin_key not in self.plugins:
                return None

            # Get the plugin config and ensure it has required fields
            plugin_config = dict(self.plugins[plugin_key])
            if not all(k in plugin_config for k in ["type", "name", "source"]):
                logger.error("Plugin %s missing required fields", plugin_key)
                return None

            # Process variables if present
            if "variables" in plugin_config:
                variables = plugin_config["variables"]
                if isinstance(variables, dict):
                    # Convert any typed variables
                    processed_vars = {}
                    for var_name, var_value in variables.items():
                        if isinstance(var_value, dict) and "type" in var_value:
                            processed_vars[var_name] = self._convert_value(
                                var_value.get("value"), var_value["type"]
                            )
                        else:
                            processed_vars[var_name] = var_value
                    plugin_config["variables"] = processed_vars

            return plugin_config

        return ref

    def _process_agents(self):
        """Process all agents after merging configurations"""
        logger.debug("Processing agents: %s", self.agents)
        processed_agents = {}

        for agent_name, agent_config in self.agents.items():
            logger.debug("Processing agent '%s': %s", agent_name, agent_config)
            processed_config = dict(agent_config)  # Create a copy to modify

            # Replace model references
            if "model" in processed_config:
                model_ref = processed_config["model"]
                logger.debug("Processing model reference: %s", model_ref)

                # If it's a direct reference (no ${...}), resolve it directly
                if isinstance(model_ref, str) and not "${" in model_ref:
                    resolved_model = self._resolve_reference(model_ref)
                    if resolved_model is None:
                        raise ValueError(
                            f"Model referenced by agent '{agent_name}' not found"
                        )
                    processed_config["model"] = resolved_model
                    logger.debug("Resolved direct model reference: %s", resolved_model)
                else:
                    # Handle interpolated references
                    model_ref = self._interpolate_value(model_ref)
                    logger.debug("After interpolation: %s", model_ref)

                    if isinstance(model_ref, str):
                        resolved_model = self._resolve_reference(model_ref)
                        if resolved_model is None:
                            raise ValueError(
                                f"Model referenced by agent '{agent_name}' not found"
                            )
                        processed_config["model"] = resolved_model
                        logger.debug("Resolved interpolated model: %s", resolved_model)
                    elif isinstance(model_ref, dict):
                        # Already resolved during interpolation
                        processed_config["model"] = model_ref
                        logger.debug("Using pre-resolved model: %s", model_ref)

            # Replace plugin references
            if "plugins" in processed_config:
                plugins = []
                logger.debug(
                    "Processing plugin references: %s", processed_config["plugins"]
                )
                for plugin_ref in processed_config["plugins"]:
                    logger.debug(
                        "Processing plugin reference: %s (type: %s)",
                        plugin_ref,
                        type(plugin_ref),
                    )

                    # If it's a direct reference (no ${...}), resolve it directly
                    if isinstance(plugin_ref, str) and not "${" in plugin_ref:
                        resolved_plugin = self._resolve_reference(plugin_ref)
                        if resolved_plugin is not None:
                            plugins.append(resolved_plugin)
                            logger.debug("Resolved direct plugin: %s", resolved_plugin)
                        else:
                            logger.debug(
                                "Invalid or unresolved plugin reference: %s", plugin_ref
                            )
                    else:
                        # Handle interpolated references
                        plugin_ref = self._interpolate_value(plugin_ref)
                        logger.debug("After interpolation: %s", plugin_ref)

                        if isinstance(plugin_ref, str):
                            resolved_plugin = self._resolve_reference(plugin_ref)
                            if resolved_plugin is not None:
                                plugins.append(resolved_plugin)
                                logger.debug(
                                    "Resolved interpolated plugin: %s", resolved_plugin
                                )
                            else:
                                logger.debug(
                                    "Invalid or unresolved plugin reference: %s",
                                    plugin_ref,
                                )
                        elif isinstance(plugin_ref, dict):
                            # Already resolved during interpolation
                            plugins.append(plugin_ref)
                            logger.debug("Using pre-resolved plugin: %s", plugin_ref)

                logger.debug("Final plugins list: %s", plugins)
                processed_config["plugins"] = plugins

            # Interpolate any other values in the agent config
            for key, value in list(processed_config.items()):
                if key not in ["model", "plugins"]:
                    processed_config[key] = self._interpolate_value(value)

            processed_agents[agent_name] = processed_config

        self.agents = processed_agents
        logger.debug("Processed agents: %s", self.agents)

    def load_config(self) -> Dict[str, Any]:
        """Load and process all HCL files in the configuration directory"""
        # Find all .hcl files in the directory
        hcl_files = glob(os.path.join(self.config_dir, "*.hcl"))
        if not hcl_files:
            raise FileNotFoundError(
                f"No HCL configuration files found in {self.config_dir}"
            )

        logger.debug("Found HCL files: %s", hcl_files)

        # Load and merge all configurations
        for file_path in hcl_files:
            config = self._load_hcl_file(file_path)
            self._merge_config(config)

        # Process all configuration blocks in order
        self._process_variables()
        self._process_models()
        self._process_plugins()
        self._process_agents()

        # Return the processed agent configurations
        return self.agents
