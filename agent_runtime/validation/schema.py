# """Schema validation for HCL configurations."""

# import json
# from pathlib import Path
# from typing import Any, Dict, Optional

# from .context import ValidationContext
# from .validators import TypeValidator, AttributeValidator, BlockValidator

# # Global instance for the get_schema_validator() function
# _SCHEMA_VALIDATOR = None


# def get_schema_validator() -> "SchemaValidator":
#     """Get or create the global schema validator instance."""
#     global _SCHEMA_VALIDATOR
#     if _SCHEMA_VALIDATOR is None:
#         _SCHEMA_VALIDATOR = SchemaValidator()
#     return _SCHEMA_VALIDATOR


# class SchemaValidator:
#     """Main schema validator that coordinates component validators."""

#     def __init__(self, schema_path: Optional[Path] = None):
#         if schema_path is None:
#             schema_path = Path(__file__).parent.parent / "schema" / "agent_schema.json"

#         with open(schema_path) as f:
#             self.schema = json.load(f)

#         # Initialize validators
#         self.type_validator = TypeValidator()
#         self.attribute_validator = AttributeValidator(self.type_validator)
#         self.block_validator = BlockValidator(
#             self.type_validator, self.attribute_validator
#         )

#     def validate_type(
#         self, value: Any, schema_type: str, context: ValidationContext
#     ) -> None:
#         """Validate a value against a specific schema type."""
#         schema = self.schema["schemas"].get(schema_type)
#         if not schema:
#             context.add_error(f"No schema found for type: {schema_type}")
#             return

#         self.block_validator.validate(value, schema, context)

#     def validate_config(self, config: Any, schema_type: str) -> ValidationContext:
#         """Validate a configuration value against a schema type, returning the validation context."""
#         context = ValidationContext()
#         self.validate_type(config, schema_type, context)
#         return context
