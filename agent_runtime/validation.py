# agent_runtime/validation.py

"""Validation utilities for agent configuration."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


class ValidationError:
    def __init__(self, path: List[str], message: str):
        self.path = path
        self.message = message

    def __str__(self) -> str:
        path_str = " -> ".join(self.path) if self.path else "root"
        return f"{path_str}: {self.message}"


class SchemaValidator:
    def __init__(self, schema_path: Optional[Path] = None):
        # If no explicit schema_path is provided, default to agent_schema.json
        if schema_path is None:
            schema_path = Path(__file__).parent / "schema" / "agent_schema.json"
        self.schema = self._load_schema(schema_path)

    def _load_schema(self, path: Path) -> Dict[str, Any]:
        """Load the JSON schema file that contains the structures for runtime, variable, etc."""
        with open(path, "r") as f:
            return cast(Dict[str, Any], json.load(f))

    def validate_config(
        self, config: Any, schema_type: str, path: List[str] = None
    ) -> List[ValidationError]:
        """
        Validate a chunk of parsed HCL config against the schema_type (e.g. "agent", "plugin", etc.).
        We return a list of ValidationError objects (one for each violation),
        so that the caller can continue checking more blocks and accumulate errors.
        """
        if path is None:
            path = []

        errors: List[ValidationError] = []
        schema = self.schema["schemas"].get(schema_type)
        if not schema:
            # If the schema doesn't exist, we can't validate further
            return [ValidationError(path, f"No schema found for type: {schema_type}")]

        # If config is just a string reference like "${var.something}", skip
        if isinstance(config, str) and config.startswith("${"):
            return []

        if not isinstance(config, dict):
            # If we expect a block/dict, but got something else
            return [
                ValidationError(path, f"Expected object, got {type(config).__name__}")
            ]

        block = schema["block"]
        errors.extend(self._validate_block(config, block, path))
        return errors

    def _validate_block(
        self, config: Dict[str, Any], block: Dict[str, Any], path: List[str]
    ) -> List[ValidationError]:
        """
        Validate that 'config' matches the schema block's 'attributes' and 'block_types'.
        Returns a list of ValidationError.
        """
        errors: List[ValidationError] = []

        # Track known fields to detect unknown ones
        known_fields = set()

        # Validate attributes
        if "attributes" in block:
            errors.extend(self._validate_attributes(config, block["attributes"], path))
            known_fields.update(block["attributes"].keys())

        # Validate nested block types
        if "block_types" in block:
            errors.extend(
                self._validate_block_types(config, block["block_types"], path)
            )
            known_fields.update(block["block_types"].keys())

        # Check for unknown fields
        unknown = set(config.keys()) - known_fields
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            errors.append(ValidationError(path, f"Unknown fields: {unknown_list}"))

        return errors

    def _validate_attributes(
        self, config: Dict[str, Any], attributes: Dict[str, Any], path: List[str]
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []

        # Check each attribute in the schema
        for attr_name, attr_schema in attributes.items():
            if attr_schema.get("required", False) and attr_name not in config:
                errors.append(
                    ValidationError(path + [attr_name], "Required attribute missing")
                )
                # Keep going; we still want to find other errors
                continue

            if attr_name in config:
                value = config[attr_name]
                attr_path = path + [attr_name]
                errors.extend(self._validate_value(value, attr_schema, attr_path))

        return errors

    def _validate_value(
        self, value: Any, schema: Dict[str, Any], path: List[str]
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []

        # If it's a reference, skip
        if isinstance(value, str) and value.startswith("${"):
            return errors

        expected_type = schema["type"]
        if not self._check_type(value, expected_type):
            errors.append(
                ValidationError(
                    path, f"Expected type {expected_type}, got {type(value).__name__}"
                )
            )
            # If type is wrong, we skip further checks for this attribute
            return errors

        # If we have an enum-like "options" check
        if "options" in schema:
            if value not in schema["options"]:
                opts_str = ", ".join(str(o) for o in schema["options"])
                errors.append(
                    ValidationError(path, f"Value must be one of: {opts_str}")
                )

        # Pattern check
        if "pattern" in schema and expected_type == "string":
            pattern = re.compile(schema["pattern"])
            if not pattern.match(str(value)):
                errors.append(
                    ValidationError(
                        path, f"Value does not match pattern: {schema['pattern']}"
                    )
                )

        # Numeric constraints
        if "constraints" in schema and expected_type == "number":
            cons = schema["constraints"]
            if "min" in cons and value < cons["min"]:
                errors.append(ValidationError(path, f"Value must be >= {cons['min']}"))
            if "max" in cons and value > cons["max"]:
                errors.append(ValidationError(path, f"Value must be <= {cons['max']}"))

        return errors

    def _validate_block_types(
        self, config: Dict[str, Any], block_types: Dict[str, Any], path: List[str]
    ) -> List[ValidationError]:
        """
        Handle nested blocks. For each named block type (e.g. "settings", "plugins"),
        check the nesting mode (single, list), min_items, etc.
        """
        errors: List[ValidationError] = []

        for block_name, bt_schema in block_types.items():
            if block_name not in config:
                # If there's a min_items > 0, we must have that block
                if "min_items" in bt_schema and bt_schema["min_items"] > 0:
                    errors.append(
                        ValidationError(path + [block_name], "Required block missing")
                    )
                continue

            sub_block = config[block_name]
            block_path = path + [block_name]
            nesting_mode = bt_schema["nesting_mode"]

            # Reject map syntax for blocks (when using = instead of block syntax)
            if (
                nesting_mode == "single"
                and isinstance(sub_block, dict)
                and not isinstance(sub_block, list)
            ):
                if not sub_block.get("_is_block", False):
                    errors.append(
                        ValidationError(
                            block_path,
                            "Expected block syntax (using { }) instead of map syntax (using =)",
                        )
                    )
                    continue

            # Handle HCL's list representation of single blocks
            if nesting_mode == "single" and isinstance(sub_block, list):
                if len(sub_block) != 1:
                    errors.append(
                        ValidationError(block_path, "Expected a single block")
                    )
                    continue
                sub_block = sub_block[0]  # Take the first (and should be only) block

            # If the block type is purely a reference to another schema
            if "reference" in bt_schema["block"]:
                # We still check if we have single vs list
                if nesting_mode == "single":
                    if not isinstance(sub_block, dict):
                        errors.append(
                            ValidationError(block_path, "Expected a single block")
                        )
                        continue
                    # Validate config against the referenced schema
                    ref_type = bt_schema["block"]["reference"]
                    errors.extend(self.validate_config(sub_block, ref_type, block_path))

                elif nesting_mode == "list":
                    if not isinstance(sub_block, list):
                        errors.append(
                            ValidationError(block_path, "Expected a list of blocks")
                        )
                        continue

                    # Check min_items, max_items
                    if (
                        "min_items" in bt_schema
                        and len(sub_block) < bt_schema["min_items"]
                    ):
                        errors.append(
                            ValidationError(
                                block_path,
                                f"Must have at least {bt_schema['min_items']} items",
                            )
                        )
                    if (
                        "max_items" in bt_schema
                        and len(sub_block) > bt_schema["max_items"]
                    ):
                        errors.append(
                            ValidationError(
                                block_path,
                                f"Must have at most {bt_schema['max_items']} items",
                            )
                        )

                    for i, item in enumerate(sub_block):
                        item_path = block_path + [str(i)]
                        if isinstance(item, str) and item.startswith("${"):
                            # It's a reference
                            continue
                        elif not isinstance(item, dict):
                            errors.append(
                                ValidationError(
                                    item_path,
                                    f"Expected object, got {type(item).__name__}",
                                )
                            )
                            continue
                        # Validate config against the referenced schema
                        ref_type = bt_schema["block"]["reference"]
                        errors.extend(self.validate_config(item, ref_type, item_path))

            else:
                # The block itself has embedded "attributes" or "block_types"
                if nesting_mode == "single":
                    if not isinstance(sub_block, dict):
                        errors.append(
                            ValidationError(block_path, "Expected a single block")
                        )
                        continue
                    errors.extend(
                        self._validate_block(sub_block, bt_schema["block"], block_path)
                    )

                elif nesting_mode == "list":
                    if not isinstance(sub_block, list):
                        errors.append(
                            ValidationError(block_path, "Expected a list of blocks")
                        )
                        continue
                    if (
                        "min_items" in bt_schema
                        and len(sub_block) < bt_schema["min_items"]
                    ):
                        errors.append(
                            ValidationError(
                                block_path,
                                f"Must have at least {bt_schema['min_items']} items",
                            )
                        )
                    if (
                        "max_items" in bt_schema
                        and len(sub_block) > bt_schema["max_items"]
                    ):
                        errors.append(
                            ValidationError(
                                block_path,
                                f"Must have at most {bt_schema['max_items']} items",
                            )
                        )
                    for i, item in enumerate(sub_block):
                        item_path = block_path + [str(i)]
                        if isinstance(item, str) and item.startswith("${"):
                            # It's a reference
                            continue
                        elif not isinstance(item, dict):
                            errors.append(
                                ValidationError(
                                    item_path,
                                    f"Expected object, got {type(item).__name__}",
                                )
                            )
                            continue
                        errors.extend(
                            self._validate_block(item, bt_schema["block"], item_path)
                        )

        return errors

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Return True if 'value' matches the 'expected_type' as defined in the schema."""
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
