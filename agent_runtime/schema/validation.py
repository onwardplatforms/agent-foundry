"""Schema validation for HCL configurations."""

import json
import re
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# Global instance for the get_schema_validator() function
_SCHEMA_VALIDATOR = None


def get_schema_validator() -> "SchemaValidator":
    """Get or create the global schema validator instance."""
    global _SCHEMA_VALIDATOR
    if _SCHEMA_VALIDATOR is None:
        _SCHEMA_VALIDATOR = SchemaValidator()
    return _SCHEMA_VALIDATOR


@dataclass
class ValidationError:
    """A validation error with path information."""

    path: List[str]
    message: str

    def __str__(self) -> str:
        path_str = " -> ".join(self.path) if self.path else "root"
        return f"{path_str}: {self.message}"


@dataclass
class ValidationContext:
    """Context for validation operations, tracking errors and current path."""

    errors: List[ValidationError] = field(default_factory=list)
    _path: List[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error at the current path."""
        self.errors.append(ValidationError(self._path.copy(), message))

    @contextmanager
    def path(self, *elements: str):
        """Context manager to track the current validation path."""
        self._path.extend(elements)
        try:
            yield
        finally:
            for _ in elements:
                self._path.pop()

    @property
    def has_errors(self) -> bool:
        """Whether any errors have been accumulated."""
        return len(self.errors) > 0

    def format_errors(self) -> str:
        """Format all errors into a readable string."""
        return "\n".join(str(error) for error in self.errors)


class Validator(ABC):
    """Base class for all validators."""

    @abstractmethod
    def validate(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate a value against a schema component."""
        pass


class TypeValidator(Validator):
    """Validates type constraints."""

    def validate(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        if isinstance(value, str) and value.startswith("${"):
            return  # Skip reference validation

        expected_type = schema.get("type")
        if not expected_type:
            return

        if not self._check_type(value, expected_type):
            context.add_error(
                f"Expected type {expected_type}, got {type(value).__name__}"
            )
            return

        # Apply validation rules if present
        if "validation" in schema:
            for rule in schema["validation"]:
                # Pattern validation for strings
                if expected_type == "string" and "pattern" in rule:
                    pattern = re.compile(rule["pattern"])
                    if not pattern.match(str(value)):
                        error_msg = rule.get(
                            "error_message",
                            f"Value does not match pattern: {rule['pattern']}",
                        )
                        context.add_error(error_msg)

                # Range validation for numbers
                elif expected_type == "number" and "range" in rule:
                    range_spec = rule["range"]
                    if "min" in range_spec and value < range_spec["min"]:
                        error_msg = rule.get(
                            "error_message", f"Value must be >= {range_spec['min']}"
                        )
                        context.add_error(error_msg)
                    if "max" in range_spec and value > range_spec["max"]:
                        error_msg = rule.get(
                            "error_message", f"Value must be <= {range_spec['max']}"
                        )
                        context.add_error(error_msg)
                    if "maxe" in range_spec and value >= range_spec["maxe"]:
                        error_msg = rule.get(
                            "error_message", f"Value must be < {range_spec['maxe']}"
                        )
                        context.add_error(error_msg)

                # Options validation (enum-like)
                elif "options" in rule:
                    if value not in rule["options"]:
                        error_msg = rule.get(
                            "error_message",
                            f"Value must be one of: {', '.join(rule['options'])}",
                        )
                        context.add_error(error_msg)

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        if expected_type == "any":
            return True
        elif expected_type == "string":
            return isinstance(value, str)
        elif expected_type == "number":
            return isinstance(value, (int, float))
        elif expected_type == "bool":
            return isinstance(value, bool)
        elif expected_type == "map":
            return isinstance(value, dict)
        elif expected_type == "list":
            return isinstance(value, list)
        return False


class AttributeValidator(Validator):
    """Validates block attributes."""

    def __init__(self, type_validator: TypeValidator):
        self.type_validator = type_validator

    def validate(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        if not isinstance(value, dict):
            context.add_error(
                f"Expected object for attributes, got {type(value).__name__}"
            )
            return

        # Get valid attribute and block type names
        valid_attributes = set(schema.get("attributes", {}).keys())
        valid_block_types = set(schema.get("block_types", {}).keys())

        # First check for unknown attributes
        for attr_name, attr_value in value.items():
            # Skip if this is a valid block type
            if attr_name in valid_block_types:
                continue

            # Check if this is a valid attribute
            if attr_name not in valid_attributes:
                # Skip validation for map type attributes as they can have arbitrary keys
                attr_schema = schema.get("attributes", {}).get(attr_name)
                if attr_schema and attr_schema.get("type") == "map":
                    continue
                context.add_error(f"Unknown attribute: {attr_name}")

        # Then check required attributes and validate values
        for attr_name, attr_schema in schema.get("attributes", {}).items():
            if attr_schema.get("required", False) and attr_name not in value:
                context.add_error(f"Required attribute missing: {attr_name}")
                continue

            if attr_name in value:
                with context.path(attr_name):
                    # Special handling for map type
                    if attr_schema.get("type") == "map":
                        if not isinstance(value[attr_name], dict):
                            context.add_error(
                                f"Expected map for attribute {attr_name}, got {type(value[attr_name]).__name__}"
                            )
                            continue
                        # For maps, we validate each value against the element type if specified
                        if "element" in attr_schema:
                            for key, element in value[attr_name].items():
                                with context.path(key):
                                    self.type_validator.validate(
                                        element, attr_schema["element"], context
                                    )
                    else:
                        self.type_validator.validate(
                            value[attr_name], attr_schema, context
                        )


class BlockValidator(Validator):
    """Validates block structure and nested blocks."""

    def __init__(
        self, type_validator: TypeValidator, attribute_validator: AttributeValidator
    ):
        self.type_validator = type_validator
        self.attribute_validator = attribute_validator

    def validate(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate a block's structure and content."""
        if not isinstance(value, (dict, list)):
            context.add_error(
                f"Expected object or list for block, got {type(value).__name__}"
            )
            return

        # Handle HCL list format for blocks
        if isinstance(value, list):
            for i, block in enumerate(value):
                with context.path(str(i)):
                    if not isinstance(block, dict):
                        context.add_error(
                            f"Expected object for block content, got {type(block).__name__}"
                        )
                        continue

                    # Handle labeled vs unlabeled blocks
                    if len(block) == 1 and isinstance(next(iter(block.values())), dict):
                        # Labeled block - could be single or double labeled
                        label, content = next(iter(block.items()))

                        # Check if this is a double-labeled block (like plugin "local" "echo")
                        if label in schema and "block" in schema[label]:
                            # This is a double-labeled block
                            if not isinstance(content, dict) or len(content) != 1:
                                context.add_error(
                                    f"Invalid format for double-labeled block {label}"
                                )
                                continue

                            sub_label, sub_content = next(iter(content.items()))
                            with context.path(label, sub_label):
                                self._validate_block(
                                    sub_content, schema[label]["block"], context
                                )
                        else:
                            # Single-labeled block
                            with context.path(label):
                                self._validate_block(content, schema["block"], context)
                    else:
                        # Unlabeled block
                        self._validate_block(block, schema["block"], context)
            return

        # Handle single block
        self._validate_block(value, schema["block"], context)

    def _validate_block(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate a single block's content."""
        if not isinstance(value, dict):
            context.add_error(
                f"Expected object for block content, got {type(value).__name__}"
            )
            return

        # Validate both attributes and block types
        self.attribute_validator.validate(value, schema, context)

        # Validate nested blocks
        if "block_types" in schema:
            for block_name, bt_schema in schema["block_types"].items():
                if block_name in value:
                    with context.path(block_name):
                        self._validate_nested_block(
                            value[block_name], bt_schema, context
                        )

    def _validate_nested_block(
        self, value: Any, schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate a nested block against its schema."""
        nesting_mode = schema.get("nesting_mode", "single")

        # HCL parser gives us a list for nested blocks
        if not isinstance(value, list):
            context.add_error(
                f"Expected list for nested block, got {type(value).__name__}"
            )
            return

        # Check block count for single mode
        if nesting_mode == "single" and len(value) > 1:
            context.add_error("Multiple blocks not allowed (nesting_mode=single)")
            return

        # Validate each block in the list
        for i, block in enumerate(value):
            with context.path(str(i)):
                self._validate_block(block, schema["block"], context)

    def _validate_block_content(
        self, sub_block: Any, bt_schema: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate the content of a block, handling both direct and referenced schemas."""
        if isinstance(sub_block, str) and sub_block.startswith("${"):
            return  # Skip reference validation

        if "reference" in bt_schema["block"]:
            # This block references another schema type
            ref_type = bt_schema["block"]["reference"]
            schema_validator = get_schema_validator()
            schema_validator.validate_type(sub_block, ref_type, context)
        else:
            # This block has its own attributes/blocks
            self.validate(sub_block, {"block": bt_schema["block"]}, context)


class SchemaValidator:
    """Main schema validator that coordinates component validators."""

    REF_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, schema_path: Optional[Path] = None):
        if schema_path is None:
            schema_path = Path(__file__).parent / "agent_schema.json"

        with open(schema_path) as f:
            self.schema = json.load(f)

        # Initialize validators
        self.type_validator = TypeValidator()
        self.attribute_validator = AttributeValidator(self.type_validator)
        self.block_validator = BlockValidator(
            self.type_validator, self.attribute_validator
        )

    def validate_type(
        self, value: Any, schema_type: str, context: ValidationContext
    ) -> None:
        """Validate a value against a specific schema type."""
        schema = self.schema["schemas"].get(schema_type)
        if not schema:
            context.add_error(f"No schema found for type: {schema_type}")
            return

        self.block_validator.validate(value, schema, context)

    def validate_config(self, config: Any, schema_type: str) -> ValidationContext:
        """Validate a configuration value against a schema type, returning the validation context."""
        context = ValidationContext()
        self.validate_type(config, schema_type, context)
        return context

    def validate_references(
        self, config: Dict[str, Any], context: ValidationContext
    ) -> None:
        """Validate all references in the configuration."""
        for section, content in config.items():
            with context.path(section):
                self._validate_references_in_value(content, context)

    def _validate_references_in_value(
        self, value: Any, context: ValidationContext
    ) -> None:
        """Recursively validate references in any value."""
        if isinstance(value, dict):
            for k, v in value.items():
                with context.path(k):
                    self._validate_references_in_value(v, context)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                with context.path(str(i)):
                    self._validate_references_in_value(item, context)
        elif isinstance(value, str):
            self._validate_string_references(value, context)

    def _validate_string_references(
        self, value: str, context: ValidationContext
    ) -> None:
        """Validate references in a string value."""
        for m in self.REF_PATTERN.finditer(value):
            ref = m.group(1).strip()
            self._validate_reference(ref, context)

    def _validate_reference(self, ref: str, context: ValidationContext) -> None:
        """Validate a single reference."""
        parts = ref.split(".")
        if not parts:
            context.add_error(f"Invalid empty reference: ${{{ref}}}")
            return

        # Check reference type
        ref_type = parts[0]
        if ref_type not in ["var", "model", "plugin", "agent", "runtime"]:
            context.add_error(f"Invalid reference type '{ref_type}' in ${{{ref}}}")
            return

        # Check reference format
        if ref_type == "var" and len(parts) != 2:
            context.add_error(f"Invalid variable reference format: ${{{ref}}}")
        elif ref_type == "model" and len(parts) < 2:
            context.add_error(f"Invalid model reference format: ${{{ref}}}")
        elif ref_type == "plugin" and len(parts) < 3:
            context.add_error(f"Invalid plugin reference format: ${{{ref}}}")
        elif ref_type == "agent" and len(parts) < 2:
            context.add_error(f"Invalid agent reference format: ${{{ref}}}")
        elif ref_type == "runtime" and len(parts) < 2:
            context.add_error(f"Invalid runtime reference format: ${{{ref}}}")
