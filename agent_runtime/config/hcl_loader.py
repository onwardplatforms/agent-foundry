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

        # First collect all defined blocks for reference validation
        self.defined_vars: Dict[str, Any] = {}
        self.defined_models: Dict[str, Any] = {}
        self.defined_plugins: Dict[str, Any] = {}
        self.defined_agents: Dict[str, Any] = {}
        self.runtime: Dict[str, Any] = {}

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

                # -------------------------------------------------------------------
                # STEP 1: Distinguish labeled vs. unlabeled block
                # -------------------------------------------------------------------
                #
                # If we have exactly one key in `block`, treat it as "labeled" block
                # (like `variable "signature" { ... }` => {"signature": {...}}).
                #
                # Otherwise, treat it as an unlabeled block
                # (like `runtime { ... }` => {required_version=..., random_var=...}).
                #
                # The existing logic for sub-labeled blocks (plugin.local, plugin.remote)
                # remains unchanged, but we skip that if it's unlabeled.
                #
                if len(block) == 1:
                    # Possibly sub-labeled or labeled
                    label, content = next(iter(block.items()))

                    # If the schema has sub-types (like plugin.local, plugin.remote)
                    if label in block_schema and "block" in block_schema[label]:
                        # This is a sub-typed block
                        if not isinstance(content, dict):
                            errors.append(
                                f"Expected dictionary for {block_type}.{label}, got {type(content)}"
                            )
                            continue

                        # Validate each labeled block within this subtype
                        for sub_label, sub_content in content.items():
                            logger.debug(
                                f"Validating {block_type}.{label}.{sub_label}: {json.dumps(sub_content, indent=2)}"
                            )

                            # Store for reference validation if needed
                            if block_type == "plugin":
                                self.defined_plugins[f"{label}:{sub_label}"] = (
                                    sub_content
                                )

                            block_errors = self._validate_block_content(
                                sub_content,
                                block_schema[label]["block"],
                                f"{block_type}.{label}.{sub_label}",
                            )
                            errors.extend(block_errors)

                    else:
                        # This is a regular labeled block
                        logger.debug(
                            f"Validating {block_type}.{label}: {json.dumps(content, indent=2)}"
                        )

                        # Store for reference validation
                        if block_type == "variable":
                            self.defined_vars[label] = content
                        elif block_type == "model":
                            self.defined_models[label] = content
                        elif block_type == "agent":
                            self.defined_agents[label] = content
                        elif block_type == "runtime":
                            # If we do "runtime \"something\" {}", we store it
                            self.runtime = content

                        block_errors = self._validate_block_content(
                            content, block_schema["block"], f"{block_type}.{label}"
                        )
                        errors.extend(block_errors)

                else:
                    # -----------------------------------------------------------------
                    # UNLABELED BLOCK:
                    # e.g. "runtime": [ { required_version=..., random_var=...} ]
                    # We treat the entire dictionary as the content to be validated
                    # and then store references if needed (like for runtime).
                    # -----------------------------------------------------------------
                    logger.debug(
                        f"Validating unlabeled {block_type} block: {json.dumps(block, indent=2)}"
                    )

                    # For references, if it's runtime, store it; if it's a variable,
                    # we can't store it by name, so it won't be referenceable by label.
                    # But we'll still do the schema validation below.
                    if block_type == "runtime":
                        self.runtime = block
                    elif block_type == "variable":
                        # We have no label, so can't store in self.defined_vars.
                        # The user won't be able to do var.someLabel references,
                        # but we still validate the block.
                        pass
                    elif block_type == "model":
                        # Same logic, no label => can't store in self.defined_models
                        pass
                    elif block_type == "agent":
                        pass
                    # If plugin => sub-labeled approach is used, so unlabeled plugin is unusual.

                    # Now just validate the entire block
                    block_errors = self._validate_block_content(
                        block, block_schema["block"], f"{block_type}"
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

        # Get all valid attribute names and block types from schema
        valid_attributes = set(schema.get("attributes", {}).keys())
        valid_block_types = set(schema.get("block_types", {}).keys())

        # Check for unknown attributes or blocks
        for key, value in content.items():
            # Skip map type attributes as they can have arbitrary keys
            attr_schema = schema.get("attributes", {}).get(key)
            if attr_schema and attr_schema.get("type") == "map":
                continue

            # Check if this is a valid attribute or block type
            if key not in valid_attributes and key not in valid_block_types:
                errors.append(f"In {path}: Unknown attribute or block '{key}'")
                continue

            # If it's an attribute, validate it
            if key in valid_attributes:
                attr_errors = self._validate_attribute(
                    value, schema["attributes"][key], f"{path}.{key}"
                )
                errors.extend(attr_errors)

            # If it's a block type, validate its content against the block schema
            if key in valid_block_types:
                block_schema = schema["block_types"][key]
                nesting_mode = block_schema.get("nesting_mode", "single")

                # HCL parser gives us a list for nested blocks
                if not isinstance(value, list):
                    errors.append(
                        f"In {path}.{key}: Expected list for nested block, got {type(value).__name__}"
                    )
                    continue

                block_count = len(value)

                # For "single" nesting mode, we should only have one item
                if nesting_mode == "single" and block_count > 1:
                    errors.append(
                        f"In {path}.{key}: Multiple nested blocks not allowed (nesting_mode=single)"
                    )
                    continue

                # Apply all validation rules if present
                if "validation" in block_schema:
                    for rule in block_schema["validation"]:
                        if "range" in rule:
                            range_spec = rule["range"]

                            # Check minimum if specified
                            if "min" in range_spec:
                                min_val = int(range_spec["min"])
                                if block_count < min_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Expected at least {min_val} blocks, got {block_count}",
                                    )
                                    errors.append(f"In {path}.{key}: {error_msg}")

                            # Check maximum if specified
                            if "max" in range_spec:
                                max_val = int(range_spec["max"])
                                if block_count > max_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Expected at most {max_val} blocks, got {block_count}",
                                    )
                                    errors.append(f"In {path}.{key}: {error_msg}")
                                    continue

                            # Check maximum exclusive if specified
                            if "maxe" in range_spec:
                                maxe_val = int(range_spec["maxe"])
                                if block_count >= maxe_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Expected fewer than {maxe_val} blocks, got {block_count}",
                                    )
                                    errors.append(f"In {path}.{key}: {error_msg}")
                                    continue

                # Validate each block in the list
                for i, block in enumerate(value):
                    if not isinstance(block, dict):
                        errors.append(
                            f"In {path}.{key}[{i}]: Expected dictionary, got {type(block).__name__}"
                        )
                        continue

                    block_errors = self._validate_block_content(
                        block, block_schema["block"], f"{path}.{key}[{i}]"
                    )
                    errors.extend(block_errors)

        # Validate required attributes
        if "attributes" in schema:
            for attr_name, attr_schema in schema["attributes"].items():
                if attr_schema.get("required", False) and attr_name not in content:
                    errors.append(
                        f"In {path}: Missing required attribute '{attr_name}'"
                    )

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

        # If the schema says "string"/"number"/"bool" but the user gave a dict,
        # we flag an error, etc.
        if isinstance(value, dict) and attr_type in ["string", "number", "bool"]:
            errors.append(f"In {path}: Expected {attr_type}, got dictionary")
            return errors

        # Check types
        if attr_type == "string":
            if not isinstance(value, str):
                errors.append(f"In {path}: Expected string, got {type(value).__name__}")
            else:
                # Apply all validation rules if present
                if "validation" in schema:
                    for rule in schema["validation"]:
                        # pattern validation
                        if "pattern" in rule:
                            pattern = re.compile(rule["pattern"])
                            if not pattern.match(value):
                                error_msg = rule.get(
                                    "error_message",
                                    f"Value '{value}' does not match pattern {rule['pattern']}",
                                )
                                errors.append(f"In {path}: {error_msg}")

                        # options validation
                        if "options" in rule:
                            if value not in rule["options"]:
                                error_msg = rule.get(
                                    "error_message",
                                    f"Value '{value}' must be one of: {', '.join(rule['options'])}",
                                )
                                errors.append(f"In {path}: {error_msg}")

        elif attr_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"In {path}: Expected number, got {type(value).__name__}")
            else:
                # Apply all validation rules if present
                if "validation" in schema:
                    value = float(value)  # Convert to float for comparison
                    for rule in schema["validation"]:
                        if "range" in rule:
                            range_spec = rule["range"]

                            # Check minimum if specified
                            if "min" in range_spec:
                                min_val = float(range_spec["min"])
                                if value < min_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Value {value} must be greater than or equal to {min_val}",
                                    )
                                    errors.append(f"In {path}: {error_msg}")

                            # Check maximum if specified
                            if "max" in range_spec:
                                max_val = float(range_spec["max"])
                                if value > max_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Value {value} must be less than or equal to {max_val}",
                                    )
                                    errors.append(f"In {path}: {error_msg}")

                            # Check maximum exclusive if specified
                            if "maxe" in range_spec:
                                maxe_val = float(range_spec["maxe"])
                                if value >= maxe_val:
                                    error_msg = rule.get(
                                        "error_message",
                                        f"Value {value} must be less than {maxe_val}",
                                    )
                                    errors.append(f"In {path}: {error_msg}")

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
        Merge a single block into our aggregator. Handles both labeled and unlabeled blocks:

        Labeled blocks (e.g. 'model "gpt4" { ... }') come in as:
            {"gpt4": {...}}

        Unlabeled blocks (e.g. 'runtime { ... }') come in as:
            {"required_version": "0.0.1", ...}

        Plugin blocks are special as they have two labels:
            {"local": {"echo": {...}}}
        """
        if not isinstance(block_def, dict):
            return

        # If the block has exactly one key and that key's value is a dict,
        # treat it as a labeled block
        if len(block_def) == 1 and isinstance(next(iter(block_def.values())), dict):
            # Get the label and content
            name, content = next(iter(block_def.items()))

            if block_type == "plugin":
                # Plugin blocks are special as they have two labels
                # e.g. {"local": {"echo": { ... }}}
                if isinstance(content, dict) and len(content) == 1:
                    (plugin_name, plugin_content) = next(iter(content.items()))
                    full_key = f"{name}:{plugin_name}"
                    merged = {"type": name, "name": plugin_name}
                    merged.update(self._convert_block_values(plugin_content))

                    # If remote plugin, ensure version
                    if name == "remote" and "version" not in merged:
                        raise ValueError(
                            f"Version is required for remote plugin 'plugin.{name}.{plugin_name}'"
                        )
                    self.plugins[full_key] = merged
            else:
                # Regular labeled block
                content_conv = self._convert_block_values(content)
                if block_type == "variable":
                    self.variables_def[name] = content_conv
                elif block_type == "model":
                    self.models[name] = content_conv
                elif block_type == "agent":
                    self.agents[name] = content_conv
                elif block_type == "runtime":
                    self.runtime[name] = content_conv
        else:
            # Unlabeled block - merge the entire dictionary directly
            content_conv = self._convert_block_values(block_def)
            if block_type == "runtime":
                self.runtime.update(content_conv)
            elif block_type == "variable":
                # For unlabeled variables, we can't store them by name
                # but we still validate the block
                pass
            elif block_type == "model":
                # Same for models - can't store without a label
                pass
            elif block_type == "agent":
                # Same for agents - can't store without a label
                pass
            elif block_type == "plugin":
                # Plugins must always have labels
                pass

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
    Recursively expands references (like ${var.something}, ${model.x},
    ${plugin.local.echo}, etc.) and also handles ternary expressions
    (like "some_expr ? valTrue : valFalse").
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
        If val is a dict or list, recurse. If it's a string, do reference + ternary
        expansion, then do best-effort numeric/boolean conversion.
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
            # 1) Try to parse ternary "expr ? x : y"
            ternary_result = self._try_ternary(val, path)
            if ternary_result is not None:
                val = self._interpolate_value(ternary_result, path)
                return self._try_convert_primitive(val)

            # 2) Expand ${...} references
            replaced = self._expand_references(val, path)
            # 3) Convert "true"/"false"/"123"/"0.7"
            return self._try_convert_primitive(replaced)

        return val

    def _try_ternary(self, val: str, path: List[str]) -> Optional[str]:
        if val.strip().startswith("${"):
            return None

        m = self.TERNARY_PATTERN.match(val.strip())
        if not m:
            return None

        condition_part = m.group(1).strip()
        true_part = m.group(2).strip()
        false_part = m.group(3).strip()

        cond_expanded = self._expand_references(condition_part, path)

        result_bool = False
        try:
            # Evaluate in a minimal safe environment
            result_bool = bool(eval(cond_expanded, {"__builtins__": None}, {}))
        except Exception as e:
            logger.debug(f"Failed ternary condition '{val}' => {e}")

        return true_part if result_bool else false_part

    def _expand_references(self, val: str, path: List[str]) -> str:
        replaced = val
        while True:
            m = self.REF_PATTERN.search(replaced)
            if not m:
                break
            expr = m.group(1).strip()
            sub_val = self._resolve_expr(expr, path)
            if m.start() == 0 and m.end() == len(replaced):
                return sub_val  # entire string was just ${...}

            if not isinstance(sub_val, str):
                sub_val = str(sub_val)
            start, end = m.span()
            replaced = replaced[:start] + sub_val + replaced[end:]
        return replaced

    def _resolve_expr(self, expr: str, path: List[str]) -> Any:
        parts = expr.split(".")
        if not parts:
            return expr

        root_val = None
        if parts[0] == "var" and len(parts) > 1:
            root_val = self.variables.get(parts[1], "")
        elif parts[0] == "model" and len(parts) > 1:
            root_val = self.models.get(parts[1], "")
        elif parts[0] == "plugin" and len(parts) > 2:
            plugin_key = f"{parts[1]}:{parts[2]}"
            root_val = self.plugins.get(plugin_key, "")
            parts = [parts[0]] + [plugin_key] + parts[3:]
        elif parts[0] == "agent" and len(parts) > 1:
            root_val = self.agents.get(parts[1], "")
        elif parts[0] == "runtime" and len(parts) > 1:
            root_val = self.runtime.get(parts[1], "")
        else:
            return expr

        current = root_val
        for part in parts[2:]:
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
        if not isinstance(val, str):
            return val

        lval = val.lower()
        if lval == "true":
            return True
        if lval == "false":
            return False

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
    2) Validate them
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
            final_vars = compute_final_variables(
                self.merger.variables_def, external_var_values
            )

        # Store
        self.runtime = self.merger.runtime
        self.variables = final_vars
        self.models = self.merger.models
        self.plugins = self.merger.plugins
        self.agents = self.merger.agents

        # Interpolate
        interp = Interpolator(
            runtime=self.runtime,
            variables=self.variables,
            models=self.models,
            plugins=self.plugins,
            agents=self.agents,
            max_passes=5,
        )
        interp.interpolate_all()

        return {
            "runtime": self.runtime,
            "variable": self.variables,
            "model": self.models,
            "plugin": self.plugins,
            "agent": self.agents,
        }

    def _load_and_validate_files(self) -> List[Dict[str, Any]]:
        """
        Find all *.hcl files, parse them, merge them, validate, and return the final merged config.
        """
        hcl_files = list(self.config_dir.glob("*.hcl"))
        logger.debug(f"Found HCL files: {[f.name for f in hcl_files]}")

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
                parse_errors.append(f"Error parsing {f.name}: {str(e)}")

        if parse_errors:
            raise RuntimeError("HCL parsing failed:\n" + "\n".join(parse_errors))

        # Merge them into a single config
        merged_config: Dict[str, Any] = {}
        for key in ["runtime", "variable", "model", "plugin", "agent"]:
            merged_config[key] = []

        for rc in raw_configs:
            for key in merged_config:
                if key in rc:
                    logger.debug(f"Merging {len(rc[key])} {key} blocks from {rc}")
                    merged_config[key].extend(rc[key])

        logger.debug("Merged config =>\n" + json.dumps(merged_config, indent=2))

        # Validate
        errors = self.validator.validate(merged_config)
        if errors:
            raise RuntimeError("Configuration validation failed:\n" + "\n".join(errors))

        logger.debug("Configuration validation successful")
        return [merged_config]
