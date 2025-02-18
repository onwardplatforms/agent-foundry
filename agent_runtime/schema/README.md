# Agent Runtime Schema Documentation

This directory contains the schema definition for Agent Runtime configuration files. The schema defines the structure and validation rules for HCL configuration files.

## Schema Structure

The schema is defined in `agent_schema.json` and follows this hierarchical structure:

```json
{
  "format_version": "0.1",
  "agent_runtime_version": "0.0.1",
  "schemas": {
    "block_name": {                    // e.g., "plugin"
      "version": 1,
      "local": {                       // Optional label key for labeled blocks
        "block": {                     // Block definition
          "attributes": {              // Attribute definitions
            "attribute_name": {
              "type": "string",
              "required": true,
              // ... other attribute properties
            }
          },
          "block_types": {            // Nested block definitions
            "nested_block_name": {
              "nesting_mode": "single",
              "block": {
                "attributes": {},
                "block_types": {}      // Can nest further
              }
            }
          }
        }
      },
      "remote": {                     // Another label for the same block type
        "block": {
          // ... similar structure
        }
      }
    },
    "unlabeled_or_single_labeled_block_name": {         // e.g., "runtime" or "model"
      "version": 1,
      "block": {                      // Direct block definition for unlabeled blocks
        "attributes": {},
        "block_types": {}
      }
    }
  }
}
```

### Block Labeling

The schema supports two types of block structures:

1. **Unlabeled Blocks**
   ```hcl
   runtime {
     required_version = "0.0.1"
   }
   ```
   These are defined directly under their block type with a `block` definition.

2. **Labeled Blocks**
   ```hcl
   plugin "local" "echo" {    # Double-labeled block
     source = "./plugins/echo"
   }

   model "gpt4" {            # Single-labeled block
     provider = "openai"
   }
   ```
   These use intermediate keys in the schema to define different variations of the same block type. The schema structure matches the HCL syntax:
   - Single-labeled blocks use one level of keys
   - Double-labeled blocks use two levels of keys

For example, the schema for a double-labeled plugin block might look like:
```json
{
  "schemas": {
    "plugin": {
      "version": 1,
      "local": {                    // First label ("local")
        "block": {                  // Defines structure for "plugin \"local\" \"name\""
          "attributes": {
            "source": {
              "type": "string",
              "required": true
            }
          }
        }
      },
      "remote": {                   // Alternative first label ("remote")
        "block": {                  // Defines structure for "plugin \"remote\" \"name\""
          "attributes": {
            "source": {
              "type": "string",
              "required": true
            },
            "version": {
              "type": "string",
              "required": true
            }
          }
        }
      }
    }
  }
}
```

## Defining Block Types

When adding a new block type to the schema, you need to define:

1. The block type name (e.g., "runtime", "model", etc.)
2. The block's attributes and nested blocks
3. Validation rules for the block and its contents

### Attribute Properties

Each attribute in a block can have these properties:

- `type`: Data type (`string`, `number`, `bool`, `list`, `map`, `any`)
- `required`: Whether the attribute is required (`true`/`false`)
- `description`: Human-readable description
- `default`: Default value if not specified
- `sensitive`: Whether the value should be treated as sensitive
- `validation`: Array of validation rules

Example attribute definition:
```json
{
  "api_key": {
    "type": "string",
    "required": true,
    "description": "API key for the service",
    "sensitive": true,
    "validation": [
      {
        "pattern": "^[A-Za-z0-9]+$",
        "error_message": "API key must be alphanumeric"
      }
    ]
  }
}
```

### Validation Rules

The schema supports three types of validation rules:

1. **Range Validation**
   ```json
   {
     "range": {
       "min": <number>,      // Minimum value (inclusive)
       "max": <number>       // Maximum value (inclusive)
     },
     "error_message": "Custom error message"
   }
   ```

2. **Pattern Validation**
   ```json
   {
     "pattern": "regex_pattern",
     "error_message": "Custom error message"
   }
   ```

3. **Options Validation**
   ```json
   {
     "options": ["value1", "value2", ...],
     "error_message": "Custom error message"
   }
   ```

### Nested Blocks

Blocks can contain other blocks using the `block_types` property. Each nested block type can specify:

- `nesting_mode`: Block nesting behavior
  - `single`: Only one block allowed
  - `list`: Multiple blocks allowed
- `validation`: Array of validation rules for block counts
  ```json
  {
    "range": {
      "min": <number>,     // Minimum number of blocks
      "max": <number>      // Maximum number of blocks
    },
    "error_message": "Custom error message"
  }
  ```

Example nested block definition:
```json
{
  "block_types": {
    "settings": {
      "nesting_mode": "single",
      "validation": [
        {
          "range": {
            "max": 1
          },
          "error_message": "Only one settings block allowed"
        }
      ],
      "block": {
        "attributes": {
          "timeout": {
            "type": "number",
            "required": false,
            "default": 30,
            "validation": [
              {
                "range": {
                  "min": 1,
                  "max": 300
                },
                "error_message": "Timeout must be between 1 and 300 seconds"
              }
            ]
          }
        }
      }
    }
  }
}
```

## Example: Adding a New Block Type

Here's an example of adding a new `database` block type to the schema:

```json
{
  "schemas": {
    "database": {
      "version": 1,
      "block": {
        "attributes": {
          "host": {
            "type": "string",
            "required": true,
            "description": "Database host address"
          },
          "port": {
            "type": "number",
            "required": false,
            "default": 5432,
            "validation": [
              {
                "range": {
                  "min": 1,
                  "max": 65535
                },
                "error_message": "Port must be between 1 and 65535"
              }
            ]
          },
          "password": {
            "type": "string",
            "required": true,
            "sensitive": true,
            "description": "Database password"
          }
        },
        "block_types": {
          "replica": {
            "nesting_mode": "list",
            "validation": [
              {
                "range": {
                  "min": 0,
                  "max": 5
                },
                "error_message": "Can have at most 5 replica configurations"
              }
            ],
            "block": {
              "attributes": {
                "host": {
                  "type": "string",
                  "required": true
                },
                "priority": {
                  "type": "number",
                  "default": 1
                }
              }
            }
          }
        }
      }
    }
  }
}
```

This would support HCL configuration like:

```hcl
database "main" {
  host     = "localhost"
  port     = 5432
  password = var.db_password

  replica "backup" {
    host     = "backup.example.com"
    priority = 2
  }
}
```
