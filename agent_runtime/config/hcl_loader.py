# agent_runtime/config/hcl_loader.py

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import hcl2
import re
import json

logger = logging.getLogger(__name__)

##############################################################################
# 1) OPTIONAL: SIMPLE SCHEMA VALIDATOR (STUB)
##############################################################################


class SchemaValidator:
    """
    Validates HCL configuration including peer-to-peer references.
    The validate() method returns a list of errors (strings).
    If empty, means valid; otherwise, you can raise an exception.
    """

    REF_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(self):
        # Load the schema from the JSON file
        schema_path = Path(__file__).parent.parent / "schema" / "agent_schema.json"
        logger.debug(f"Loading schema from: {schema_path}")
        with open(schema_path, "r") as f:
            self.schema = json.load(f)
        logger.debug(f"Loaded schema version: {self.schema.get('format_version')}")

    def validate(self, raw_config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        logger.debug(
            f"Starting validation of config: {json.dumps(raw_config, indent=2)}"
        )

        # First collect all defined names and their structures
        self.defined_vars: Dict[str, Any] = {}
        self.defined_models: Dict[str, Any] = {}
        self.defined_plugins: Dict[str, Any] = {}
        self.defined_agents: Dict[str, Any] = {}

        # Extract and validate each block type
        for block_type, blocks in raw_config.items():
            logger.debug(f"Validating block type: {block_type}")

            # Skip if block type not in schema
            if block_type not in self.schema["schemas"]:
                errors.append(f"Unknown block type: {block_type}")
                continue

            block_schema = self.schema["schemas"][block_type]
            logger.debug(
                f"Using schema for {block_type}: {json.dumps(block_schema, indent=2)}"
            )

            if not isinstance(blocks, list):
                errors.append(
                    f"Expected list of {block_type} blocks, got {type(blocks)}"
                )
                continue

            # Validate each block of this type
            for block in blocks:
                if not isinstance(block, dict):
                    errors.append(
                        f"Expected dictionary for {block_type} block, got {type(block)}"
                    )
                    continue

                # Special handling for plugin blocks which have a nested structure
                if block_type == "plugin":
                    for plugin_type, plugin_blocks in block.items():
                        # Validate plugin type
                        if plugin_type not in block_schema:
                            errors.append(
                                f"Unknown plugin type '{plugin_type}', must be one of: {', '.join(k for k in block_schema.keys() if k != 'version')}"
                            )
                            continue

                        if not isinstance(plugin_blocks, dict):
                            errors.append(
                                f"Expected dictionary for plugin type '{plugin_type}', got {type(plugin_blocks)}"
                            )
                            continue

                        # Get the schema for this plugin type
                        type_schema = block_schema[plugin_type]

                        for plugin_name, plugin_content in plugin_blocks.items():
                            logger.debug(
                                f"Validating plugin block '{plugin_type}.{plugin_name}': {json.dumps(plugin_content, indent=2)}"
                            )

                            # Store for reference validation
                            plugin_key = f"{plugin_type}:{plugin_name}"
                            self.defined_plugins[plugin_key] = plugin_content

                            # Validate against type-specific schema
                            block_errors = self._validate_block_content(
                                plugin_content,
                                type_schema["block"],
                                f"plugin.{plugin_type}.{plugin_name}",
                            )
                            errors.extend(block_errors)
                else:
                    # For non-plugin blocks, they just have a single label for identification
                    for block_name, block_content in block.items():
                        logger.debug(
                            f"Validating {block_type} block '{block_name}': {json.dumps(block_content, indent=2)}"
                        )

                        # Store in appropriate collection for reference validation
                        if block_type == "variable":
                            self.defined_vars[block_name] = block_content
                        elif block_type == "model":
                            self.defined_models[block_name] = block_content
                        elif block_type == "agent":
                            self.defined_agents[block_name] = block_content

                        # Get the schema - for non-plugin blocks it's directly in the block field
                        block_schema_to_use = block_schema["block"]

                        # Validate the block content against the schema
                        block_errors = self._validate_block_content(
                            block_content,
                            block_schema_to_use,
                            f"{block_type}.{block_name}",
                        )
                        errors.extend(block_errors)

        # Now validate all references in the config
        logger.debug("Starting reference validation")
        self._validate_references_in_dict(raw_config, errors)

        if errors:
            logger.debug("Validation failed with errors: %s", errors)
        else:
            logger.debug("Configuration validation successful")

        return errors

    def _validate_block_content(
        self, content: Dict[str, Any], schema: Dict[str, Any], path: str
    ) -> List[str]:
        """Validate a block's content against its schema."""
        errors = []

        # If content is not a dictionary, validate it directly as an attribute
        if not isinstance(content, dict):
            # Find the attribute schema for this path
            path_parts = path.split(".")
            if len(path_parts) >= 2:
                block_type, attr_name = path_parts[-2:]
                block_schema = self.schema["schemas"].get(block_type)
                if block_schema:
                    attr_schema = block_schema["block"]["attributes"].get(attr_name)
                    if attr_schema:
                        attr_errors = self._validate_attribute(
                            content, attr_schema, path
                        )
                        errors.extend(attr_errors)
                    else:
                        errors.append(f"In {path}: Unknown attribute '{attr_name}'")
            return errors

        # Get all valid attribute names from schema
        valid_attributes = set(schema.get("attributes", {}).keys())
        valid_block_types = set(schema.get("block_types", {}).keys())

        # Check for unknown attributes (only for non-map attributes)
        for attr_name, attr_value in content.items():
            # Skip validation if this attribute is a map type (allows arbitrary keys)
            attr_schema = schema.get("attributes", {}).get(attr_name)
            if attr_schema and attr_schema.get("type") == "map":
                continue

            if attr_name not in valid_attributes and attr_name not in valid_block_types:
                errors.append(f"In {path}: Unknown attribute '{attr_name}'")

        # Validate required attributes
        if "attributes" in schema:
            for attr_name, attr_schema in schema["attributes"].items():
                if attr_schema.get("required", False) and attr_name not in content:
                    errors.append(
                        f"In {path}: Missing required attribute '{attr_name}'"
                    )
                elif attr_name in content:
                    attr_value = content[attr_name]
                    attr_errors = self._validate_attribute(
                        attr_value, attr_schema, f"{path}.{attr_name}"
                    )
                    errors.extend(attr_errors)

        # Validate nested blocks
        if "block_types" in schema:
            for block_type, block_schema in schema["block_types"].items():
                if block_type in content:
                    if not isinstance(content[block_type], dict):
                        errors.append(
                            f"In {path}.{block_type}: Expected dictionary, got {type(content[block_type]).__name__}"
                        )
                    else:
                        block_errors = self._validate_block_content(
                            content[block_type],
                            block_schema["block"],
                            f"{path}.{block_type}",
                        )
                        errors.extend(block_errors)

        return errors

    def _validate_attribute(
        self, value: Any, schema: Dict[str, Any], path: str
    ) -> List[str]:
        """Validate a single attribute against its schema."""
        errors = []
        attr_type = schema.get("type")

        logger.debug(
            f"Validating attribute at {path}: {value} against schema: {schema}"
        )

        # Special handling for 'any' type - accept anything
        if attr_type == "any":
            return errors

        # For block types, validate as a dictionary
        if isinstance(value, dict):
            # If it's a dictionary but schema expects a primitive, that's an error
            if attr_type in ["string", "number", "bool"]:
                errors.append(f"In {path}: Expected {attr_type}, got dictionary")
            return errors

        # For primitive types, validate according to schema
        if attr_type == "string":
            if not isinstance(value, str):
                errors.append(f"In {path}: Expected string, got {type(value).__name__}")
            elif "pattern" in schema:
                pattern = re.compile(schema["pattern"])
                if not pattern.match(str(value)):
                    errors.append(
                        f"In {path}: Value '{value}' does not match pattern {schema['pattern']}"
                    )
            elif "options" in schema and value not in schema["options"]:
                errors.append(
                    f"In {path}: Value '{value}' must be one of: {', '.join(schema['options'])}"
                )

        elif attr_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"In {path}: Expected number, got {type(value).__name__}")
            elif "constraints" in schema:
                constraints = schema["constraints"]
                if "min" in constraints and value < constraints["min"]:
                    errors.append(
                        f"In {path}: Value {value} must be greater than or equal to {constraints['min']}"
                    )
                if "max" in constraints and value > constraints["max"]:
                    errors.append(
                        f"In {path}: Value {value} must be less than or equal to {constraints['max']}"
                    )

        elif attr_type == "bool":
            if not isinstance(value, bool):
                errors.append(
                    f"In {path}: Expected boolean, got {type(value).__name__}"
                )

        elif attr_type == "list":
            if not isinstance(value, list):
                errors.append(f"In {path}: Expected list, got {type(value).__name__}")

        elif attr_type == "map":
            if not isinstance(value, dict):
                errors.append(f"In {path}: Expected map, got {type(value).__name__}")

        return errors

    def _validate_references_in_dict(
        self, d: Dict[str, Any], errors: List[str], path: str = ""
    ) -> None:
        """Recursively validate all references in a dictionary."""
        for k, v in d.items():
            current_path = f"{path}.{k}" if path else k

            if isinstance(v, dict):
                self._validate_references_in_dict(v, errors, current_path)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        self._validate_references_in_dict(
                            item, errors, f"{current_path}[{i}]"
                        )
                    elif isinstance(item, str):
                        self._validate_string_references(
                            item, errors, f"{current_path}[{i}]"
                        )
            elif isinstance(v, str):
                self._validate_string_references(v, errors, current_path)

    def _validate_string_references(
        self, val: str, errors: List[str], path: str
    ) -> None:
        """Validate all references in a string value."""
        for m in self.REF_PATTERN.finditer(val):
            ref = m.group(1).strip()
            self._validate_reference(ref, errors, path)

    def _validate_reference(self, ref: str, errors: List[str], path: str) -> None:
        """Validate a single reference, handling nested paths."""
        parts = ref.split(".")

        if not parts:
            return

        # Handle the root reference first
        if parts[0] == "var":
            if len(parts) < 2:
                errors.append(f"In {path}: Invalid variable reference '{ref}'")
                return
            var_name = parts[1]
            if var_name not in self.defined_vars:
                available = (
                    ", ".join(sorted(self.defined_vars.keys())) or "none defined"
                )
                errors.append(
                    f"In {path}: Reference to undefined variable 'var.{var_name}'\n"
                    f"  Available variables: {available}"
                )
                return
            # For nested references, validate against the variable's structure
            if len(parts) > 2:
                self._validate_nested_reference(
                    parts[2:],
                    self.defined_vars[var_name],
                    f"var.{var_name}",
                    errors,
                    path,
                )

        elif parts[0] == "model":
            if len(parts) < 2:
                errors.append(f"In {path}: Invalid model reference '{ref}'")
                return
            model_name = parts[1]
            if model_name not in self.defined_models:
                available = (
                    ", ".join(sorted(self.defined_models.keys())) or "none defined"
                )
                errors.append(
                    f"In {path}: Reference to undefined model 'model.{model_name}'\n"
                    f"  Available models: {available}"
                )
                return
            # For nested references, validate against the model's structure
            if len(parts) > 2:
                self._validate_nested_reference(
                    parts[2:],
                    self.defined_models[model_name],
                    f"model.{model_name}",
                    errors,
                    path,
                )

        elif parts[0] == "plugin":
            if len(parts) < 3:
                errors.append(f"In {path}: Invalid plugin reference '{ref}'")
                return
            plugin_key = f"{parts[1]}:{parts[2]}"
            if plugin_key not in self.defined_plugins:
                available = (
                    ", ".join(sorted(self.defined_plugins.keys())) or "none defined"
                )
                errors.append(
                    f"In {path}: Reference to undefined plugin 'plugin.{parts[1]}.{parts[2]}'\n"
                    f"  Available plugins: {available}"
                )
                return
            # For nested references, validate against the plugin's structure
            if len(parts) > 3:
                self._validate_nested_reference(
                    parts[3:],
                    self.defined_plugins[plugin_key],
                    f"plugin.{parts[1]}.{parts[2]}",
                    errors,
                    path,
                )

        elif parts[0] == "agent":
            if len(parts) < 2:
                errors.append(f"In {path}: Invalid agent reference '{ref}'")
                return
            agent_name = parts[1]
            if agent_name not in self.defined_agents:
                available = (
                    ", ".join(sorted(self.defined_agents.keys())) or "none defined"
                )
                errors.append(
                    f"In {path}: Reference to undefined agent 'agent.{agent_name}'\n"
                    f"  Available agents: {available}"
                )
                return
            # For nested references, validate against the agent's structure
            if len(parts) > 2:
                self._validate_nested_reference(
                    parts[2:],
                    self.defined_agents[agent_name],
                    f"agent.{agent_name}",
                    errors,
                    path,
                )

    def _validate_nested_reference(
        self,
        parts: List[str],
        structure: Any,
        ref_path: str,
        errors: List[str],
        path: str,
    ) -> None:
        """Validate nested reference parts against a structure."""
        current = structure
        logger.debug(
            f"Validating nested reference: {ref_path}.{'.'.join(parts)} at {path}"
        )
        logger.debug(f"Structure: {current}")

        for i, part in enumerate(parts):
            if not isinstance(current, dict):
                errors.append(
                    f"In {path}: Invalid nested reference '{ref_path}.{'.'.join(parts[:i+1])}' - parent is not a dictionary"
                )
                return
            if part not in current:
                errors.append(
                    f"In {path}: Invalid nested reference '{ref_path}.{'.'.join(parts[:i+1])}' - field does not exist"
                )
                return
            current = current[part]
            logger.debug(f"After part {part}: {current}")


##############################################################################
# 2) BLOCK MERGER
##############################################################################


class BlockMerger:
    """
    Collects all blocks from HCL files into top-level dicts:
        runtime, variables_def, models, plugins, agents

    For variable blocks, we store the entire definition (type, default, etc.)
    in variables_def. Then later we compute final variable values from that.
    """

    def __init__(self):
        self.runtime: Dict[str, Any] = {}
        self.variables_def: Dict[str, Dict[str, Any]] = {}
        self.models: Dict[str, Any] = {}
        self.plugins: Dict[str, Any] = {}
        self.agents: Dict[str, Any] = {}

    def merge_hcl_config(self, raw_config: Dict[str, Any]) -> None:
        """
        Merge a single HCL config dictionary into the aggregator fields.
        raw_config has shape like:
          {
            "runtime": [...],
            "variable": [...],
            "model": [...],
            "plugin": [...],
            "agent": [...]
          }
        Each key is a list of block definitions.
        """
        for block_type, block_list in raw_config.items():
            if not isinstance(block_list, list):
                continue
            for block_def in block_list:
                if not isinstance(block_def, dict):
                    continue
                self._merge_one_block(block_type, block_def)

    def _merge_one_block(self, block_type: str, block_def: Dict[str, Any]) -> None:
        """
        Merge a single block (e.g. 'model' => {"llama2_instance": {...}}) into our aggregator.
        """
        if block_type == "runtime":
            # Typically there's only one runtime block, but let's just do an update
            merged_vals = self._convert_block_values(block_def)
            self.runtime.update(merged_vals)

        elif block_type == "variable":
            # E.g. {"model_temperature": {"description":"...", "type":"number", "default":0.7}}
            var_name, var_content = next(iter(block_def.items()))
            var_content_conv = self._convert_block_values(var_content)
            self.variables_def[var_name] = var_content_conv

        elif block_type == "model":
            # E.g. {"llama2_instance": {"provider": "...", ...}}
            name, content = next(iter(block_def.items()))
            self.models[name] = self._convert_block_values(content)

        elif block_type == "plugin":
            # e.g. {"local": {"echo": { ... }}} => plugin type: local, name: echo
            if len(block_def) == 1:
                (plugin_type, inner) = next(iter(block_def.items()))
                if isinstance(inner, dict) and len(inner) == 1:
                    (plugin_name, plugin_content) = next(iter(inner.items()))
                    full_key = f"{plugin_type}:{plugin_name}"
                    merged = {"type": plugin_type, "name": plugin_name}
                    merged.update(self._convert_block_values(plugin_content))

                    # Add validation for remote plugins requiring version
                    if plugin_type == "remote" and "version" not in merged:
                        raise ValueError(
                            f"Version is required for remote plugin 'plugin.{plugin_type}.{plugin_name}'"
                        )

                    self.plugins[full_key] = merged

        elif block_type == "agent":
            # e.g. {"local": {"name":"...", ...}}
            name, content = next(iter(block_def.items()))
            self.agents[name] = self._convert_block_values(content)

    def _convert_block_values(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert raw string numbers ("123", "0.7") to ints/floats if they parse,
        and "true"/"false" to bool.  Leaves references like "${var.foo}" alone.
        """
        result: Dict[str, Any] = {}
        for k, v in block.items():
            if isinstance(v, str):
                lv = v.lower()
                if lv == "true":
                    result[k] = True
                elif lv == "false":
                    result[k] = False
                else:
                    # Try int or float
                    try:
                        if "." in v:
                            result[k] = float(v)
                        else:
                            result[k] = int(v)
                    except ValueError:
                        result[k] = v  # keep as string
            elif isinstance(v, dict):
                result[k] = self._convert_block_values(v)
            elif isinstance(v, list):
                new_list = []
                for item in v:
                    if isinstance(item, dict):
                        new_list.append(self._convert_block_values(item))
                    else:
                        new_list.append(item)
                result[k] = new_list
            else:
                # already bool/int/float
                result[k] = v
        return result


##############################################################################
# 3) COMPUTE FINAL VARIABLE VALUES
##############################################################################


def compute_final_variables(
    variables_def: Dict[str, Dict[str, Any]],
    external_var_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    For each variable definition in variables_def, pick final runtime value.
    Use external_var_values if provided, otherwise fallback to 'default' in def.
    E.g. variables_def["provider"] = {"description":"...", "type":"string", "default":"ollama"}
    => final_vars["provider"] = "ollama"
    """
    final_vars = {}
    overrides = external_var_values or {}

    for var_name, var_def in variables_def.items():
        if var_name in overrides:
            final_vars[var_name] = overrides[var_name]
        else:
            final_vars[var_name] = var_def.get("default", None)
        # If you want to ensure no missing defaults, do:
        # if final_vars[var_name] is None:
        #     raise ValueError(f"No override or default for variable '{var_name}'")

    return final_vars


##############################################################################
# 4) SINGLE PASS INTERPOLATOR + TYPE CONVERSION
##############################################################################


class Interpolator:
    """
    Recursively expands references (like ${var.something}, ${model.x}, ${plugin.local.echo}, etc.)
    and also handles ternary expressions (like "some_expr ? valTrue : valFalse").
    Then tries converting numeric/boolean strings to actual types.
    """

    TERNARY_PATTERN = re.compile(r"^(.*?)\?(.*?)\:(.*)$", re.DOTALL)
    REF_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(
        self,
        runtime: Dict[str, Any],
        variables: Dict[str, Any],
        models: Dict[str, Any],
        plugins: Dict[str, Any],
        agents: Dict[str, Any],
        max_passes: int = 5,
    ):
        self.runtime = runtime
        self.variables = variables
        self.models = models
        self.plugins = plugins
        self.agents = agents
        self.max_passes = max_passes

    def interpolate_all(self) -> None:
        """
        We'll do multiple passes so that if references produce new references,
        we eventually resolve them. If a pass doesn't change anything, we stop.
        """
        for _ in range(self.max_passes):
            before = self._snapshot()
            self._interpolate_dict(self.runtime, ["runtime"])
            self._interpolate_dict(self.variables, ["variable"])
            self._interpolate_dict(self.models, ["model"])
            self._interpolate_dict(self.plugins, ["plugin"])
            self._interpolate_dict(self.agents, ["agent"])
            after = self._snapshot()
            if after == before:
                # no changes => stable
                break

    def _snapshot(self) -> str:
        return json.dumps(
            {
                "runtime": self.runtime,
                "variables": self.variables,
                "models": self.models,
                "plugins": self.plugins,
                "agents": self.agents,
            },
            sort_keys=True,
        )

    def _interpolate_dict(self, d: Dict[str, Any], path: List[str]) -> None:
        for k in list(d.keys()):
            val = d[k]
            new_val = self._interpolate_value(val, path + [k])
            d[k] = new_val

    def _interpolate_value(self, val: Any, path: List[str]) -> Any:
        """
        If val is a dict or list, recurse. If it's a string, do reference + ternary expansion,
        then do best-effort numeric/boolean conversion.
        """
        if isinstance(val, dict):
            for dk in list(val.keys()):
                val[dk] = self._interpolate_value(val[dk], path + [dk])
            return val

        if isinstance(val, list):
            for i in range(len(val)):
                val[i] = self._interpolate_value(val[i], path + [str(i)])
            return val

        if isinstance(val, str):
            # 1) Try to parse it as a ternary expression: "cond ? x : y"
            ternary_result = self._try_ternary(val, path)
            if ternary_result is not None:
                # recursively process the result if it's a string
                val = self._interpolate_value(ternary_result, path)
                return self._try_convert_primitive(val)

            # 2) Expand all references like ${...} in the string
            replaced = self._expand_references(val, path)
            # 3) Attempt type conversion (bool, int, float)
            return self._try_convert_primitive(replaced)

        return val

    def _try_ternary(self, val: str, path: List[str]) -> Optional[str]:
        """
        If val looks like a ternary "expr ? yes : no", we parse the expr,
        evaluate it as a python bool, and return yes/no. Otherwise None.
        """
        # skip if it starts with "${", so we don't interpret e.g. "${var.cond}" as ternary
        if val.strip().startswith("${"):
            return None

        m = self.TERNARY_PATTERN.match(val.strip())
        if not m:
            return None

        condition_part = m.group(1).strip()
        true_part = m.group(2).strip()
        false_part = m.group(3).strip()

        # expand references inside condition
        cond_expanded = self._expand_references(condition_part, path)

        # evaluate as bool
        result_bool = False
        try:
            result_bool = bool(eval(cond_expanded, {"__builtins__": None}, {}))
        except Exception as e:
            logger.debug(f"Failed ternary condition '{val}' => {e}")

        return true_part if result_bool else false_part

    def _expand_references(self, val: str, path: List[str]) -> str:
        """
        Replace all ${...} references with actual values from
        var, model, plugin, agent, runtime, etc.
        """
        replaced = val
        while True:
            m = self.REF_PATTERN.search(replaced)
            if not m:
                break
            expr = m.group(1).strip()  # stuff inside ${...}
            sub_val = self._resolve_expr(expr, path)

            # If the entire string is just ${...}, return the original value type
            if m.start() == 0 and m.end() == len(replaced):
                return sub_val

            # Otherwise, we're doing string interpolation, so convert to string
            if not isinstance(sub_val, str):
                sub_val = str(sub_val)
            start, end = m.span()
            replaced = replaced[:start] + sub_val + replaced[end:]
        return replaced

    def _resolve_expr(self, expr: str, path: List[str]) -> Any:
        """
        We support references:
          var.name, model.name, plugin.local.echo, agent.remote, runtime.something
        And nested references like:
          model.llama2_instance.name, var.settings.temperature, etc.
        If unknown, return "" (empty string).
        """
        parts = expr.split(".")
        if not parts:
            return expr

        # Get the root object first
        root_val = None
        if parts[0] == "var" and len(parts) > 1:
            root_val = self.variables.get(parts[1], "")
        elif parts[0] == "model" and len(parts) > 1:
            root_val = self.models.get(parts[1], "")
        elif parts[0] == "plugin" and len(parts) > 2:
            plugin_key = f"{parts[1]}:{parts[2]}"
            root_val = self.plugins.get(plugin_key, "")
            parts = (
                [parts[0]] + [f"{parts[1]}:{parts[2]}"] + parts[3:]
            )  # Adjust parts list
        elif parts[0] == "agent" and len(parts) > 1:
            root_val = self.agents.get(parts[1], "")
        elif parts[0] == "runtime" and len(parts) > 1:
            root_val = self.runtime.get(parts[1], "")
        else:
            return expr

        # Now traverse into nested fields if they exist
        current = root_val
        for part in parts[2:]:  # Skip the type and name parts we already handled
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return ""
            else:
                return ""

        return current

    def _try_convert_primitive(self, val: str) -> Any:
        """
        After we've expanded references in a string, try to parse bool/int/float.
        If it fails, keep it as string.
        """
        if not isinstance(val, str):
            return val

        lval = val.lower()
        if lval == "true":
            return True
        if lval == "false":
            return False

        # attempt numeric
        try:
            if "." in val:
                return float(val)
            else:
                return int(val)
        except ValueError:
            pass

        return val


##############################################################################
# 5) MAIN LOADER CLASS
##############################################################################


class HCLConfigLoader:
    """
    1) Load all *.hcl in directory
    2) Validate them (stub)
    3) Merge into top-level dicts (runtime, variables_def, models, plugins, agents)
    4) Compute final var overrides => self.variables
    5) Single multi-pass interpolation + type conversion across everything
    6) Return final config
    """

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        logger.debug(f"Initializing HCLConfigLoader with config_dir: {config_dir}")
        self.validator = SchemaValidator()
        self.merger = BlockMerger()
        # final data
        self.runtime: Dict[str, Any] = {}
        self.variables: Dict[str, Any] = {}
        self.models: Dict[str, Any] = {}
        self.plugins: Dict[str, Any] = {}
        self.agents: Dict[str, Any] = {}

    def load_config(
        self,
        var_loader: Optional["VarLoader"] = None,
        external_var_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Load and process configuration.

        Args:
            var_loader: Optional VarLoader instance for handling variables
            external_var_values: Legacy support for external values (deprecated)
        """
        all_raw_configs = self._load_and_validate_files()

        # Merge them all
        for rc in all_raw_configs:
            self.merger.merge_hcl_config(rc)

        # Now compute final variables
        if var_loader:
            final_vars = var_loader.get_final_values(self.merger.variables_def)
        else:
            # Legacy support
            final_vars = compute_final_variables(
                self.merger.variables_def, external_var_values
            )

        # Put them in self
        self.runtime = self.merger.runtime
        self.variables = final_vars
        self.models = self.merger.models
        self.plugins = self.merger.plugins
        self.agents = self.merger.agents

        # Single pass interpolation
        interp = Interpolator(
            runtime=self.runtime,
            variables=self.variables,
            models=self.models,
            plugins=self.plugins,
            agents=self.agents,
            max_passes=5,
        )
        interp.interpolate_all()

        # Return final data
        return {
            "runtime": self.runtime,
            "variable": self.variables,
            "model": self.models,
            "plugin": self.plugins,
            "agent": self.agents,
        }

    def _load_and_validate_files(self) -> List[Dict[str, Any]]:
        """
        Find all *.hcl files, parse them with hcl2, merge them, then validate the merged config.
        Returns list of raw configs if no errors. Otherwise raise an error.
        """
        hcl_files = list(self.config_dir.glob("*.hcl"))
        logger.debug(f"Found HCL files: {[f.name for f in hcl_files]}")

        # First load all files without validation
        raw_configs: List[Dict[str, Any]] = []
        parse_errors: List[str] = []

        for f in hcl_files:
            try:
                with open(f, "r") as fp:
                    logger.debug(f"Loading HCL file: {f.name}")
                    rc = hcl2.load(fp)
                    logger.debug(
                        f"Loaded content from {f.name}: {json.dumps(rc, indent=2)}"
                    )
                    raw_configs.append(rc)
            except Exception as e:
                error_msg = f"Error parsing {f.name}: {str(e)}"
                parse_errors.append(error_msg)

        if parse_errors:
            msg = "HCL parsing failed:\n" + "\n".join(parse_errors)
            raise RuntimeError(msg)

        # Merge all configs into one
        merged_config: Dict[str, Any] = {}
        for key in ["runtime", "variable", "model", "plugin", "agent"]:
            merged_config[key] = []

        for rc in raw_configs:
            for key in merged_config:
                if key in rc:
                    logger.debug(f"Merging {len(rc[key])} {key} blocks from config")
                    merged_config[key].extend(rc[key])

        logger.debug("Merged configuration complete, starting validation")
        logger.debug(f"Merged config: {json.dumps(merged_config, indent=2)}")

        # Now validate the merged config
        validation_errors = self.validator.validate(merged_config)
        if validation_errors:
            raise RuntimeError(
                "Configuration validation failed:\n" + "\n".join(validation_errors)
            )

        logger.debug("Configuration validation successful")
        return [merged_config]  # Return merged config as single item


##############################################################################
# EXAMPLE USAGE
##############################################################################

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    loader = HCLConfigLoader(Path("."))

    # Suppose we want to override var.signature => "Signed by CFO"
    overrides = {
        # "signature": "Signed by CFO"
    }

    final_config = loader.load_config(external_var_values=overrides)

    print("Final config =>")
    print(json.dumps(final_config, indent=2))
