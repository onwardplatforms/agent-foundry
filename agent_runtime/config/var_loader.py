# """Variable loading and resolution for Agent Foundry."""

# import logging
# import os
# from pathlib import Path
# from typing import Any, Dict, Optional, Union, List
# import hcl2
# import click

# logger = logging.getLogger(__name__)


# class ValidationError(Exception):
#     """Raised when variable validation fails."""

#     pass


# class VarLoader:
#     """Handles loading and resolving variables from multiple sources."""

#     # Mapping of HCL types to Python types
#     TYPE_MAP = {
#         "string": str,
#         "number": (int, float),
#         "bool": bool,
#         "list": list,
#         "map": dict,
#     }

#     def __init__(self):
#         self.var_files: Dict[str, Dict[str, Any]] = {}
#         self.cli_vars: Dict[str, Any] = {}
#         self.env_vars: Dict[str, Any] = {}

#     def load_var_file(self, file_path: Path) -> None:
#         """Load variables from a .var.hcl file."""
#         logger.debug("Loading variable file: %s", file_path)
#         try:
#             with open(file_path, "r") as f:
#                 vars = hcl2.load(f)
#                 # HCL2 returns a dict with a single key containing all vars
#                 if isinstance(vars, dict) and len(vars) == 1:
#                     vars = next(iter(vars.values()))
#                 self.var_files[str(file_path)] = vars
#         except Exception as e:
#             logger.error("Failed to load variable file %s: %s", file_path, e)
#             raise RuntimeError(f"Failed to load variable file {file_path}: {e}")

#     def add_cli_var(self, var_str: str) -> None:
#         """Add a variable from command line (format: name=value)."""
#         try:
#             name, value = var_str.split("=", 1)
#             name = name.strip()
#             value = value.strip()

#             # Try to convert value to appropriate type
#             if value.lower() == "true":
#                 value = True
#             elif value.lower() == "false":
#                 value = False
#             else:
#                 try:
#                     if "." in value:
#                         value = float(value)
#                     else:
#                         value = int(value)
#                 except ValueError:
#                     # Keep as string if not a number
#                     pass

#             self.cli_vars[name] = value
#         except ValueError:
#             raise ValueError(
#                 f"Invalid variable format: {var_str}. Expected format: name=value"
#             )

#     def load_env_vars(self, prefix: str = "ODK_VAR_") -> None:
#         """Load variables from environment with given prefix."""
#         for key, value in os.environ.items():
#             if key.startswith(prefix):
#                 var_name = key[len(prefix) :].lower()
#                 self.env_vars[var_name] = value

#     def _validate_type(self, value: Any, expected_type: str, var_name: str) -> Any:
#         """Validate and convert a value to its expected type."""
#         if expected_type not in self.TYPE_MAP:
#             raise ValidationError(
#                 f"Unknown type '{expected_type}' for variable '{var_name}'"
#             )

#         expected_python_type = self.TYPE_MAP[expected_type]

#         # Handle special case for number type (can be int or float)
#         if expected_type == "number":
#             if not isinstance(value, (int, float)):
#                 try:
#                     # Try to convert string to number
#                     if isinstance(value, str):
#                         if "." in value:
#                             value = float(value)
#                         else:
#                             value = int(value)
#                 except ValueError:
#                     raise ValidationError(
#                         f"Variable '{var_name}' must be a number, got '{value}' ({type(value).__name__})"
#                     )
#         # Handle other types
#         elif not isinstance(value, expected_python_type):
#             try:
#                 if expected_type == "bool" and isinstance(value, str):
#                     if value.lower() == "true":
#                         value = True
#                     elif value.lower() == "false":
#                         value = False
#                     else:
#                         raise ValueError()
#                 else:
#                     value = expected_python_type(value)
#             except (ValueError, TypeError):
#                 raise ValidationError(
#                     f"Variable '{var_name}' must be type {expected_type}, got '{value}' ({type(value).__name__})"
#                 )

#         return value

#     def _prompt_for_value(self, var_name: str, var_def: Dict[str, Any]) -> Any:
#         """Prompt user for a variable value with proper type conversion."""
#         var_type = var_def.get("type", "string")
#         description = var_def.get("description", "")
#         prompt_text = f"\nVariable '{var_name}' is required"
#         if description:
#             prompt_text += f" - {description}"
#         prompt_text += f" (type: {var_type}): "

#         while True:
#             try:
#                 value = click.prompt(prompt_text, type=str)
#                 # Validate and convert the value
#                 return self._validate_type(value, var_type, var_name)
#             except ValidationError as e:
#                 click.echo(click.style(f"Error: {str(e)}", fg="red"))
#                 continue

#     def get_final_values(
#         self, variables_def: Dict[str, Dict[str, Any]], prompt_missing: bool = True
#     ) -> Dict[str, Any]:
#         """
#         Get final variable values following resolution order:
#         1. CLI variables (--var)
#         2. Variable files (--var-file)
#         3. Environment variables (ODK_VAR_*)
#         4. Default values from variable definitions
#         5. Interactive prompt if prompt_missing=True
#         """
#         final_vars: Dict[str, Any] = {}
#         validation_errors: List[str] = []

#         for var_name, var_def in variables_def.items():
#             var_type = var_def.get("type", "string")
#             value = None

#             # Resolution order
#             if var_name in self.cli_vars:
#                 value = self.cli_vars[var_name]
#             else:
#                 # Check all var files in order they were provided
#                 for vars in self.var_files.values():
#                     if var_name in vars:
#                         value = vars[var_name]
#                         break

#                 if value is None:
#                     if var_name in self.env_vars:
#                         value = self.env_vars[var_name]
#                     elif "default" in var_def:
#                         value = var_def["default"]

#             # If we have a value, validate its type
#             if value is not None:
#                 try:
#                     value = self._validate_type(value, var_type, var_name)
#                 except ValidationError as e:
#                     validation_errors.append(str(e))
#                     value = None

#             # If still no value and prompting is enabled
#             if value is None and prompt_missing:
#                 try:
#                     value = self._prompt_for_value(var_name, var_def)
#                 except click.Abort:
#                     raise RuntimeError("Variable input aborted by user")

#             # If we still have no value, it's an error
#             if value is None:
#                 validation_errors.append(
#                     f"No value provided for required variable '{var_name}'"
#                 )
#             else:
#                 final_vars[var_name] = value

#         if validation_errors:
#             raise ValidationError("\n".join(validation_errors))

#         return final_vars
