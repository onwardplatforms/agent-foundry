# """Base validators for different schema components."""

# from abc import ABC, abstractmethod
# from typing import Any, Dict, List, Optional, Type
# from .context import ValidationContext


# class Validator(ABC):
#     """Base class for all validators."""

#     @abstractmethod
#     def validate(
#         self, value: Any, schema: Dict[str, Any], context: ValidationContext
#     ) -> None:
#         """Validate a value against a schema component."""
#         pass


# class TypeValidator(Validator):
#     """Validates type constraints."""

#     def validate(
#         self, value: Any, schema: Dict[str, Any], context: ValidationContext
#     ) -> None:
#         if isinstance(value, str) and value.startswith("${"):
#             return  # Skip reference validation

#         expected_type = schema.get("type")
#         if not expected_type:
#             return

#         if not self._check_type(value, expected_type):
#             context.add_error(
#                 f"Expected type {expected_type}, got {type(value).__name__}"
#             )
#             return

#         # Additional type-specific validation
#         if expected_type == "string" and "pattern" in schema:
#             import re

#             pattern = re.compile(schema["pattern"])
#             if not pattern.match(str(value)):
#                 context.add_error(f"Value does not match pattern: {schema['pattern']}")

#         elif expected_type == "number" and "constraints" in schema:
#             cons = schema["constraints"]
#             if "min" in cons and value < cons["min"]:
#                 context.add_error(f"Value must be >= {cons['min']}")
#             if "max" in cons and value > cons["max"]:
#                 context.add_error(f"Value must be <= {cons['max']}")

#     def _check_type(self, value: Any, expected_type: str) -> bool:
#         """Check if value matches expected type."""
#         if expected_type == "any":
#             return True
#         elif expected_type == "string":
#             return isinstance(value, str)
#         elif expected_type == "number":
#             return isinstance(value, (int, float))
#         elif expected_type == "bool":
#             return isinstance(value, bool)
#         elif expected_type == "map":
#             return isinstance(value, dict)
#         elif expected_type == "list":
#             return isinstance(value, list)
#         return False


# class AttributeValidator(Validator):
#     """Validates block attributes."""

#     def __init__(self, type_validator: TypeValidator):
#         self.type_validator = type_validator

#     def validate(
#         self, value: Any, schema: Dict[str, Any], context: ValidationContext
#     ) -> None:
#         if not isinstance(value, dict):
#             context.add_error(
#                 f"Expected object for attributes, got {type(value).__name__}"
#             )
#             return

#         attributes = schema.get("attributes", {})

#         # Check required attributes
#         for attr_name, attr_schema in attributes.items():
#             if attr_schema.get("required", False) and attr_name not in value:
#                 context.add_error(f"Required attribute missing: {attr_name}")
#                 continue

#             if attr_name in value:
#                 with context.path(attr_name):
#                     self.type_validator.validate(value[attr_name], attr_schema, context)

#         # We don't check for unknown attributes here - that's handled by BlockValidator


# class BlockValidator(Validator):
#     """Validates block structure and nested blocks."""

#     def __init__(
#         self, type_validator: TypeValidator, attribute_validator: AttributeValidator
#     ):
#         self.type_validator = type_validator
#         self.attribute_validator = attribute_validator

#     def validate(
#         self, value: Any, schema: Dict[str, Any], context: ValidationContext
#     ) -> None:
#         if isinstance(value, str) and value.startswith("${"):
#             return  # Skip reference validation

#         if not isinstance(value, dict):
#             context.add_error(f"Expected object for block, got {type(value).__name__}")
#             return

#         block = schema.get("block", {})

#         # Track known fields to detect unknown ones
#         known_fields = set()

#         # Validate attributes
#         if "attributes" in block:
#             self.attribute_validator.validate(value, block, context)
#             known_fields.update(block["attributes"].keys())

#         # Validate nested blocks
#         if "block_types" in block:
#             self._validate_block_types(value, block["block_types"], context)
#             known_fields.update(block["block_types"].keys())

#         # Check for unknown fields
#         unknown = set(value.keys()) - known_fields
#         if unknown:
#             unknown_list = ", ".join(sorted(unknown))
#             context.add_error(f"Unknown attributes: {unknown_list}")

#     def _validate_block_types(
#         self,
#         value: Dict[str, Any],
#         block_types: Dict[str, Any],
#         context: ValidationContext,
#     ) -> None:
#         """Validate nested block types."""
#         for block_name, bt_schema in block_types.items():
#             if block_name not in value:
#                 if bt_schema.get("min_items", 0) > 0:
#                     context.add_error(f"Required block missing: {block_name}")
#                 continue

#             with context.path(block_name):
#                 sub_block = value[block_name]
#                 nesting_mode = bt_schema["nesting_mode"]

#                 # Validate block syntax vs map syntax
#                 if nesting_mode == "single" and isinstance(sub_block, dict):
#                     if not sub_block.get("_is_block", False):
#                         context.add_error(
#                             "Expected block syntax (using { }) instead of map syntax (using =)"
#                         )
#                         continue

#                 # Handle HCL's list representation of single blocks
#                 if nesting_mode == "single" and isinstance(sub_block, list):
#                     if len(sub_block) != 1:
#                         context.add_error("Expected a single block")
#                         continue
#                     sub_block = sub_block[0]

#                 # Validate the block content
#                 self._validate_block_content(sub_block, bt_schema, context)

#     def _validate_block_content(
#         self, sub_block: Any, bt_schema: Dict[str, Any], context: ValidationContext
#     ) -> None:
#         """Validate the content of a block, handling both direct and referenced schemas."""
#         if isinstance(sub_block, str) and sub_block.startswith("${"):
#             return  # Skip reference validation

#         if "reference" in bt_schema["block"]:
#             # This block references another schema type
#             ref_type = bt_schema["block"]["reference"]
#             from .schema import get_schema_validator

#             schema_validator = get_schema_validator()
#             schema_validator.validate_type(sub_block, ref_type, context)
#         else:
#             # This block has its own attributes/blocks
#             self.validate(sub_block, {"block": bt_schema["block"]}, context)
