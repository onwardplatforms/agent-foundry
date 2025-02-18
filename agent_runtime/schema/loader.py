"""Configuration loading and processing for Agent Runtime."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import hcl2

from .validation import SchemaValidator, ValidationContext

logger = logging.getLogger(__name__)


class VarLoader:
    """
    Loads variables from multiple sources in order of precedence:
    1. CLI variables (--var key=value)
    2. Variable files (--var-file path)
    3. Environment variables (AGENT_VAR_*)
    4. Default values from variable blocks
    """

    def __init__(self):
        self.cli_vars: Dict[str, Any] = {}
        self.var_file_vars: Dict[str, Any] = {}
        self.env_vars: Dict[str, Any] = {}

    def add_cli_var(self, var_str: str) -> None:
        """Add a CLI variable in format 'name=value'."""
        if "=" not in var_str:
            raise ValueError(f"Invalid variable format: {var_str}")
        name, value = var_str.split("=", 1)
        self.cli_vars[name.strip()] = self._convert_value(value.strip())

    def load_var_file(self, var_file: Path) -> None:
        """Load variables from a file (HCL or JSON)."""
        if not var_file.exists():
            raise ValueError(f"Variable file not found: {var_file}")

        try:
            if var_file.suffix == ".json":
                with open(var_file) as f:
                    vars_dict = json.load(f)
            else:  # Assume HCL
                with open(var_file) as f:
                    vars_dict = hcl2.load(f)
        except Exception as e:
            raise ValueError(f"Error loading variable file {var_file}: {e}")

        # Merge with existing var file vars
        self.var_file_vars.update(vars_dict)

    def load_env_vars(self) -> None:
        """Load variables from environment (AGENT_VAR_*)."""
        prefix = "AGENT_VAR_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                var_name = key[len(prefix) :].lower()
                self.env_vars[var_name] = self._convert_value(value)

    def get_final_values(
        self, variables_def: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        For each variable definition, pick final value based on precedence:
        1. CLI vars
        2. Var file vars
        3. Environment vars
        4. Default from definition
        """
        final_vars = {}

        for var_name, var_def in variables_def.items():
            # Try sources in order of precedence
            if var_name in self.cli_vars:
                final_vars[var_name] = self.cli_vars[var_name]
            elif var_name in self.var_file_vars:
                final_vars[var_name] = self.var_file_vars[var_name]
            elif var_name in self.env_vars:
                final_vars[var_name] = self.env_vars[var_name]
            else:
                final_vars[var_name] = var_def.get("default", None)

        return final_vars

    def _convert_value(self, value: str) -> Any:
        """Convert string values to appropriate types."""
        # Try boolean
        lval = value.lower()
        if lval == "true":
            return True
        if lval == "false":
            return False

        # Try number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Keep as string
        return value


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


class ConfigLoader:
    """Main configuration loader that handles HCL files and variables."""

    def __init__(self, config_dir: str | Path):
        self.config_dir = (
            Path(config_dir) if isinstance(config_dir, str) else config_dir
        )
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
        var_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Load and process configuration.

        Args:
            var_loader: Optional VarLoader instance for handling variables
            var_values: Variable values to use (overrides defaults)
        """
        # Load and validate all HCL files
        raw_configs = self._load_and_validate_files()

        # Merge them all
        for rc in raw_configs:
            self.merger.merge_hcl_config(rc)

        # Compute final variables
        if var_loader:
            final_vars = var_loader.get_final_values(self.merger.variables_def)
        else:
            final_vars = self._compute_variables(self.merger.variables_def, var_values)

        # Store everything
        self.runtime = self.merger.runtime
        self.variables = final_vars
        self.models = self.merger.models
        self.plugins = self.merger.plugins
        self.agents = self.merger.agents

        # Interpolate references
        interp = Interpolator(
            runtime=self.runtime,
            variables=self.variables,
            models=self.models,
            plugins=self.plugins,
            agents=self.agents,
            max_passes=5,
        )
        interp.interpolate_all()

        # Validate references after interpolation
        context = ValidationContext()
        self.validator.validate_references(
            {
                "runtime": self.runtime,
                "variable": self.variables,
                "model": self.models,
                "plugin": self.plugins,
                "agent": self.agents,
            },
            context,
        )

        if context.has_errors:
            raise RuntimeError(
                "Reference validation failed:\n" + context.format_errors()
            )

        return {
            "runtime": self.runtime,
            "variable": self.variables,
            "model": self.models,
            "plugin": self.plugins,
            "agent": self.agents,
        }

    def _load_and_validate_files(self) -> List[Dict[str, Any]]:
        """Load all HCL files, validate them, and return the merged config."""
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
        context = ValidationContext()
        for block_type, blocks in merged_config.items():
            with context.path(block_type):
                self.validator.validate_type(blocks, block_type, context)

        if context.has_errors:
            raise RuntimeError(
                "Configuration validation failed:\n" + context.format_errors()
            )

        logger.debug("Configuration validation successful")
        return [merged_config]

    def _compute_variables(
        self,
        variables_def: Dict[str, Dict[str, Any]],
        var_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        For each variable definition in variables_def, pick final runtime value.
        Use var_values if provided, otherwise fallback to 'default' in def.
        """
        final_vars = {}
        overrides = var_values or {}

        for var_name, var_def in variables_def.items():
            if var_name in overrides:
                final_vars[var_name] = overrides[var_name]
            else:
                final_vars[var_name] = var_def.get("default", None)

        return final_vars
