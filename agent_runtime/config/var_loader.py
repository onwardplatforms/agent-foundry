"""Variable loading and resolution for Agent Foundry."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
import hcl2

logger = logging.getLogger(__name__)


class VarLoader:
    """Handles loading and resolving variables from multiple sources."""

    def __init__(self):
        self.var_files: Dict[str, Dict[str, Any]] = {}
        self.cli_vars: Dict[str, Any] = {}
        self.env_vars: Dict[str, Any] = {}

    def load_var_file(self, file_path: Path) -> None:
        """Load variables from a .var.hcl file."""
        logger.debug("Loading variable file: %s", file_path)
        try:
            with open(file_path, "r") as f:
                vars = hcl2.load(f)
                # HCL2 returns a dict with a single key containing all vars
                if isinstance(vars, dict) and len(vars) == 1:
                    vars = next(iter(vars.values()))
                self.var_files[str(file_path)] = vars
        except Exception as e:
            logger.error("Failed to load variable file %s: %s", file_path, e)
            raise RuntimeError(f"Failed to load variable file {file_path}: {e}")

    def add_cli_var(self, var_str: str) -> None:
        """Add a variable from command line (format: name=value)."""
        try:
            name, value = var_str.split("=", 1)
            name = name.strip()
            value = value.strip()

            # Try to convert value to appropriate type
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            else:
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    # Keep as string if not a number
                    pass

            self.cli_vars[name] = value
        except ValueError:
            raise ValueError(
                f"Invalid variable format: {var_str}. Expected format: name=value"
            )

    def load_env_vars(self, prefix: str = "ODK_VAR_") -> None:
        """Load variables from environment with given prefix."""
        for key, value in os.environ.items():
            if key.startswith(prefix):
                var_name = key[len(prefix) :].lower()
                self.env_vars[var_name] = value

    def get_final_values(
        self, variables_def: Dict[str, Dict[str, Any]], prompt_missing: bool = True
    ) -> Dict[str, Any]:
        """
        Get final variable values following resolution order:
        1. CLI variables (--var)
        2. Variable files (--var-file)
        3. Environment variables (ODK_VAR_*)
        4. Default values from variable definitions
        5. Interactive prompt if prompt_missing=True
        """
        final_vars: Dict[str, Any] = {}

        # Track which variables still need values for potential prompting
        missing_vars = []

        for var_name, var_def in variables_def.items():
            # Resolution order
            if var_name in self.cli_vars:
                final_vars[var_name] = self.cli_vars[var_name]
            else:
                # Check all var files in order they were provided
                found = False
                for vars in self.var_files.values():
                    if var_name in vars:
                        final_vars[var_name] = vars[var_name]
                        found = True
                        break

                if not found:
                    if var_name in self.env_vars:
                        final_vars[var_name] = self.env_vars[var_name]
                    elif "default" in var_def:
                        final_vars[var_name] = var_def["default"]
                    else:
                        missing_vars.append((var_name, var_def))

        if missing_vars and prompt_missing:
            # We'll implement interactive prompting in the next step
            # For now, raise an error
            names = [name for name, _ in missing_vars]
            raise ValueError(f"Missing required variables: {', '.join(names)}")

        return final_vars
