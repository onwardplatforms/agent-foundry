import os
import logging
from typing import Dict, Any, List
import hcl2
from pathlib import Path
from glob import glob

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
                if not isinstance(block, dict) or len(block) != 1:
                    logger.debug("Skipping invalid block: %s", block)
                    continue

                block_name, block_value = next(iter(block.items()))
                logger.debug(
                    "Processing block '%s.%s': %s", block_type, block_name, block_value
                )

                if block_type == "runtime":
                    self.runtime = block_value
                elif block_type == "variable":
                    self.variables[block_name] = block_value
                elif block_type == "model":
                    self.models[block_name] = block_value
                elif block_type == "plugin":
                    self.plugins[block_name] = block_value
                elif block_type == "agent":
                    self.agents[block_name] = block_value

    def _process_variables(self):
        """Process all variables after merging configurations"""
        logger.debug("Processing variables: %s", self.variables)
        processed_vars = {}
        for var_name, var_config in self.variables.items():
            processed_vars[var_name] = var_config.get("default")
        logger.debug("Processed variables: %s", processed_vars)
        self.variables = processed_vars

    def _process_models(self):
        """Process all models after merging configurations"""
        logger.debug("Processing models: %s", self.models)
        for model_name, model_config in self.models.items():
            # Replace variable references
            if "settings" in model_config:
                for key, value in model_config["settings"].items():
                    if isinstance(value, str) and value.startswith("var."):
                        var_name = value.split(".")[1]
                        model_config["settings"][key] = self.variables.get(var_name)
        logger.debug("Processed models: %s", self.models)

    def _process_plugins(self):
        """Process and validate all plugins after merging configurations"""
        logger.debug("Processing plugins: %s", self.plugins)
        for plugin_name, plugin_config in self.plugins.items():
            # Validate plugin configuration
            if "source" not in plugin_config:
                raise ValueError(
                    f"Plugin {plugin_name} is missing required 'source' field"
                )

            # For local plugins, source should be a directory path
            if plugin_name.endswith("_local"):
                plugin_config["source"] = plugin_config["source"]
                # Extract name from directory path
                plugin_config["name"] = os.path.basename(plugin_config["source"])
            else:
                # Remote plugins require version
                if "version" not in plugin_config:
                    raise ValueError(
                        f"Remote plugin {plugin_name} is missing required 'version' field"
                    )
                plugin_config["name"] = plugin_name.replace("_remote", "")

            # Add plugin name to variables for reference
            if "variables" not in plugin_config:
                plugin_config["variables"] = {}
            plugin_config["variables"]["name"] = plugin_config["name"]

        logger.debug("Processed plugins: %s", self.plugins)

    def _process_agents(self):
        """Process all agents after merging configurations"""
        logger.debug("Processing agents: %s", self.agents)
        for agent_name, agent_config in self.agents.items():
            logger.debug("Processing agent '%s': %s", agent_name, agent_config)

            # Replace model references
            if "model" in agent_config:
                model_ref = agent_config["model"]
                logger.debug("Processing model reference: %s", model_ref)
                if isinstance(model_ref, str) and model_ref.startswith("${model."):
                    model_name = model_ref[8:-1]  # Remove ${model. and }
                    logger.debug("Extracted model name: %s", model_name)
                    if model_name not in self.models:
                        raise ValueError(
                            f"Model '{model_name}' referenced by agent '{agent_name}' not found"
                        )
                    agent_config["model"] = dict(self.models[model_name])

            # Replace plugin references
            if "plugins" in agent_config:
                plugins = []
                logger.debug(
                    "Processing plugin references: %s", agent_config["plugins"]
                )
                for plugin_ref in agent_config["plugins"]:
                    logger.debug(
                        "Processing plugin reference: %s (type: %s)",
                        plugin_ref,
                        type(plugin_ref),
                    )
                    if isinstance(plugin_ref, str) and plugin_ref.startswith(
                        "${plugin."
                    ):
                        plugin_name = plugin_ref[9:-1]  # Remove ${plugin. and }
                        logger.debug("Extracted plugin name: %s", plugin_name)
                        if plugin_name not in self.plugins:
                            raise ValueError(
                                f"Plugin '{plugin_name}' referenced by agent '{agent_name}' not found"
                            )
                        plugin_config = dict(self.plugins[plugin_name])
                        logger.debug("Original plugin config: %s", plugin_config)
                        # Keep only the necessary fields
                        processed_plugin = {
                            "source": plugin_config["source"],
                            "variables": plugin_config.get("variables", {}),
                        }
                        if "version" in plugin_config:
                            processed_plugin["version"] = plugin_config["version"]
                        plugins.append(processed_plugin)
                    else:
                        logger.debug(
                            "Unexpected plugin reference format: %s", plugin_ref
                        )
                logger.debug("Final plugins list: %s", plugins)
                agent_config["plugins"] = plugins
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
