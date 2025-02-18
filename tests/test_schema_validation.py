import pytest
from pathlib import Path
from agent_runtime.schema.validation import (
    SchemaValidator,
    ValidationContext,
    ValidationError,
)


@pytest.fixture
def validator():
    """Create a schema validator instance."""
    return SchemaValidator()


@pytest.fixture
def context():
    """Create a fresh validation context."""
    return ValidationContext()


# Block Validation Tests
def test_multiple_model_settings_blocks(validator, context):
    """Test that multiple settings blocks in a model are rejected."""
    config = [
        {
            "gpt4": {
                "provider": "openai",
                "name": "gpt-4",
                "settings": [
                    {"temperature": 0.7},
                    {"temperature": 0.5},  # Second settings block should fail
                ],
            }
        }
    ]

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any(
        "Multiple blocks not allowed (nesting_mode=single)" in str(err)
        for err in context.errors
    )


def test_nonexistent_block_type(validator, context):
    """Test that nonexistent block types are rejected."""
    config = [{"test": {"some_attr": "value"}}]

    validator.validate_type(config, "nonexistent", context)
    assert context.has_errors
    assert any(
        "No schema found for type: nonexistent" in str(err) for err in context.errors
    )


def test_nested_block_validation(validator, context):
    """Test validation of nested blocks."""
    config = [
        {
            "gpt4": {
                "provider": "openai",
                "name": "gpt-4",
                "settings": [
                    {"invalid_block": [{"some_value": "test"}]}  # Invalid nested block
                ],
            }
        }
    ]

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any("Unknown attribute: invalid_block" in str(err) for err in context.errors)


# Attribute Validation Tests
def test_nonexistent_attribute(validator, context):
    """Test that nonexistent attributes are rejected."""
    config = [
        {"gpt4": {"provider": "openai", "name": "gpt-4", "nonexistent_attr": "value"}}
    ]

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any(
        "Unknown attribute: nonexistent_attr" in str(err) for err in context.errors
    )


def test_wrong_attribute_type(validator, context):
    """Test that wrong attribute types are rejected."""
    config = [
        {
            "gpt4": {
                "provider": "openai",
                "name": "gpt-4",
                "settings": [{"temperature": "not_a_number"}],  # Should be number
            }
        }
    ]

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any("Expected type number" in str(err) for err in context.errors)


def test_missing_required_attribute(validator, context):
    """Test that missing required attributes are caught."""
    config = [{"gpt4": {"name": "gpt-4"}}]  # Missing required 'provider'

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any(
        "Required attribute missing: provider" in str(err) for err in context.errors
    )


# Range Validation Tests
def test_temperature_range_validation(validator, context):
    """Test temperature range validation (0-1)."""
    invalid_temps = [-0.1, 1.1, 2.0]
    for temp in invalid_temps:
        config = [
            {
                "gpt4": {
                    "provider": "openai",
                    "name": "gpt-4",
                    "settings": [{"temperature": temp}],
                }
            }
        ]
        validator.validate_type(config, "model", context)
        assert context.has_errors
        assert any(
            "Temperature must be between 0 and 1" in str(err) for err in context.errors
        )
        context = ValidationContext()  # Reset for next test


def test_max_tokens_range_validation(validator, context):
    """Test max_tokens range validation (must be positive)."""
    config = [
        {
            "gpt4": {
                "provider": "openai",
                "name": "gpt-4",
                "settings": [{"max_tokens": 0}],  # Should be at least 1
            }
        }
    ]

    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any(
        "Maximum tokens must be at least 1" in str(err) for err in context.errors
    )


# Options Validation Tests
def test_model_provider_options(validator, context):
    """Test model provider options validation."""
    # Valid provider
    config = [{"gpt4": {"provider": "openai", "name": "gpt-4"}}]
    validator.validate_type(config, "model", context)
    assert not context.has_errors

    # Invalid provider
    context = ValidationContext()
    config[0]["gpt4"]["provider"] = "invalid_provider"
    validator.validate_type(config, "model", context)
    assert context.has_errors
    assert any(
        "Model provider must be either 'openai' or 'ollama'" in str(err)
        for err in context.errors
    )


def test_variable_type_options(validator, context):
    """Test variable type options validation."""
    # Test all valid types
    valid_types = ["string", "number", "bool", "list", "map", "any"]
    for valid_type in valid_types:
        config = [{"test_var": {"type": valid_type, "description": "Test variable"}}]
        validator.validate_type(config, "variable", context)
        assert not context.has_errors
        context = ValidationContext()  # Reset for next test

    # Test invalid type
    config = [{"test_var": {"type": "invalid_type", "description": "Test variable"}}]
    validator.validate_type(config, "variable", context)
    assert context.has_errors
    assert any("Invalid variable type" in str(err) for err in context.errors)


# Map and List Validation Tests
def test_plugin_variables_map_validation(validator, context):
    """Test validation of plugin variables map."""
    config = [
        {
            "local": {
                "test_plugin": {
                    "source": "./test",
                    "variables": "not_a_map",  # Should be a map
                }
            }
        }
    ]

    validator.validate_type(config, "plugin", context)
    assert context.has_errors
    assert any(
        "Expected map for attribute variables" in str(err) for err in context.errors
    )


def test_agent_plugins_list_validation(validator, context):
    """Test validation of agent plugins list."""
    config = [
        {
            "test_agent": {
                "name": "Test Agent",
                "description": "Test description",
                "system_prompt": "Test prompt",
                "model": "${model.gpt4}",
                "plugins": "not_a_list",  # Should be a list
            }
        }
    ]

    validator.validate_type(config, "agent", context)
    assert context.has_errors
    assert any("Expected type list" in str(err) for err in context.errors)


# Reference Validation Tests
def test_invalid_reference_format(validator, context):
    """Test that invalid reference formats are caught."""
    config = [
        {
            "test_agent": {
                "name": "Test Agent",
                "description": "Test description",
                "system_prompt": "Test prompt",
                "model": "${invalid.reference}",  # Invalid reference format
                "plugins": [],
            }
        }
    ]

    validator.validate_type(config, "agent", context)
    validator.validate_references({"agent": config}, context)
    assert context.has_errors
    assert any("Invalid reference type" in str(err) for err in context.errors)


def test_nested_reference_validation(validator, context):
    """Test validation of nested references in complex structures."""
    config = [
        {
            "gpt4": {
                "provider": "openai",
                "name": "gpt-4",
                "settings": [
                    {
                        "temperature": "${var.temp}",
                        "nested": {
                            "value": "${var.nested.value}"  # Invalid nested reference
                        },
                    }
                ],
            }
        }
    ]

    validator.validate_type(config, "model", context)
    validator.validate_references({"model": config}, context)
    assert context.has_errors
    assert any(
        "Invalid variable reference format" in str(err) for err in context.errors
    )


# Pattern Validation Tests
def test_version_pattern_validation(validator, context):
    """Test version pattern validation."""
    valid_versions = ["0.1.0", ">=0.1.0", ">=0.1.0,<2.0.0", "~>0.1.0"]
    invalid_versions = ["invalid", "0.1", ">=0.1", ">0.1.0,invalid"]

    for version in valid_versions:
        config = {"runtime": [{"required_version": version}]}
        validator.validate_type(config["runtime"], "runtime", context)
        assert not context.has_errors
        context = ValidationContext()  # Reset for next test

    for version in invalid_versions:
        config = {"runtime": [{"required_version": version}]}
        validator.validate_type(config["runtime"], "runtime", context)
        assert context.has_errors
        assert any(
            "Invalid version constraint format" in str(err) for err in context.errors
        )
        context = ValidationContext()  # Reset for next test


def test_plugin_source_pattern_validation(validator, context):
    """Test plugin source pattern validation."""
    # Test local plugin source
    valid_local_sources = ["./plugin", "../plugin", "./nested/plugin"]
    invalid_local_sources = ["/absolute/path", "relative/path", "invalid"]

    for source in valid_local_sources:
        config = [{"local": {"test_plugin": {"source": source, "variables": {}}}}]
        validator.validate_type(config, "plugin", context)
        assert not context.has_errors, f"Expected valid local source {source}"
        context = ValidationContext()

    for source in invalid_local_sources:
        config = [{"local": {"test_plugin": {"source": source, "variables": {}}}}]
        validator.validate_type(config, "plugin", context)
        assert context.has_errors, f"Expected invalid local source {source}"
        assert any(
            "Local plugin source must start with ./ or ../" in str(err)
            for err in context.errors
        )
        context = ValidationContext()

    # Test remote plugin source
    valid_remote_sources = [
        "github.com/org/agentruntime-plugin-test",
        "https://github.com/org/agentruntime-plugin-test",
        "org/test",
    ]
    invalid_remote_sources = [
        "github.com/org/invalid-plugin",  # Missing agentruntime-plugin- prefix
        "invalid/format/extra",  # Too many segments
        "https://gitlab.com/org/name",  # Not GitHub
    ]

    for source in valid_remote_sources:
        config = [
            {
                "remote": {
                    "test_plugin": {
                        "source": source,
                        "version": "0.1.0",
                        "variables": {},
                    }
                }
            }
        ]
        validator.validate_type(config, "plugin", context)
        assert not context.has_errors, f"Expected valid remote source {source}"
        context = ValidationContext()

    for source in invalid_remote_sources:
        config = [
            {
                "remote": {
                    "test_plugin": {
                        "source": source,
                        "version": "0.1.0",
                        "variables": {},
                    }
                }
            }
        ]
        validator.validate_type(config, "plugin", context)
        assert context.has_errors, f"Expected invalid remote source {source}"
        assert any(
            "Remote plugin source must be a GitHub URL" in str(err)
            for err in context.errors
        )
        context = ValidationContext()
