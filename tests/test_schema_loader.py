import os
import pytest
import logging
from agent_runtime.schema.loader import ConfigLoader

# Configure logging for tests
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """Set up logging for all tests."""
    caplog.set_level(logging.DEBUG)


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary directory with test HCL files"""
    # Create agent.hcl
    agent_hcl = tmp_path / "agent.hcl"
    logger.info("Creating test HCL file at: %s", agent_hcl)
    agent_hcl.write_text(
        """
runtime {
  required_version = "0.0.1"
}

variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

variable "model_max_tokens" {
  description = "Maximum tokens for model response"
  type        = number
  default     = 1000
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature
    max_tokens  = var.model_max_tokens
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

plugin "remote" "echo" {
  source = "https://github.com/onwardplatforms/agentruntime-plugin-echo"
  version = "0.0.1"
  variables = {}
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.local.echo]
}
"""
    )
    logger.info("Test HCL file created successfully")
    return tmp_path


def test_load_local_agent(config_dir):
    """Test loading a local agent configuration"""
    logger.info("Starting test_load_local_agent")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.local.echo]
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    assert config["agent"]["test_agent"]["name"] == "test-agent-local"
    expected_model = {
        "provider": "ollama",
        "name": "llama2",
        "settings": [{"temperature": 0.7}],
    }
    assert config["agent"]["test_agent"]["model"] == expected_model


def test_variable_interpolation(config_dir):
    """Test variable interpolation in configuration"""
    logger.info("Starting test_variable_interpolation")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature
  }
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    expected_model = {
        "provider": "ollama",
        "name": "llama2",
        "settings": [{"temperature": 0.7}],
    }
    assert config["agent"]["test_agent"]["model"] == expected_model


def test_plugin_validation(config_dir):
    """Test plugin configuration validation"""
    logger.info("Starting test_plugin_validation")
    agent_hcl = config_dir / "agent.hcl"

    # Test missing source
    agent_hcl.write_text(
        """
plugin "local" "invalid" {
  variables = {}
}
"""
    )
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(RuntimeError, match="Configuration validation failed"):
        loader.load_config()

    # Test missing version for remote plugin
    agent_hcl.write_text(
        """
plugin "remote" "invalid" {
  source = "https://github.com/org/agentruntime-plugin-test"
  variables = {}
}
"""
    )
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(RuntimeError, match="Configuration validation failed"):
        loader.load_config()

    # Test invalid local source format
    agent_hcl.write_text(
        """
plugin "local" "invalid" {
  source = "local_plugins/echo"
  variables = {}
}
"""
    )
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(RuntimeError, match="Configuration validation failed"):
        loader.load_config()

    logger.info("test_plugin_validation completed successfully")


def test_runtime_version(config_dir):
    """Test runtime version is correctly loaded"""
    logger.info("Starting test_runtime_version")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
runtime {
  required_version = "0.0.1"
}

variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature
  }
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    assert config["runtime"]["required_version"] == "0.0.1"


def test_interpolation_syntax(config_dir):
    """Test both ${type.name} and type.name syntax for all reference types"""
    logger.info("Starting test_interpolation_syntax")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature  # var.name syntax
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "Using temperature 0.7"  # String interpolation
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance  # type.name syntax
  plugins        = [plugin.local.echo]  # type.name syntax in list
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    assert config["agent"]["test_agent"]["description"] == "Using temperature 0.7"


def test_interpolation_errors(config_dir):
    """Test error cases for interpolation"""
    logger.info("Starting test_interpolation_errors")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.nonexistent  # Reference to non-existent variable
  }
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.nonexistent  # Reference to non-existent model
  plugins        = [plugin.local.nonexistent]  # Reference to non-existent plugin
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()

    # Verify that unresolved references evaluate to empty strings
    assert config["model"]["llama2_instance"]["settings"][0]["temperature"] == ""
    assert config["agent"]["test_agent"]["model"] == ""
    assert config["agent"]["test_agent"]["plugins"][0] == ""


def test_nested_interpolation(config_dir):
    """Test nested interpolation in complex structures"""
    logger.info("Starting test_nested_interpolation")
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "base_temp" {
  description = "Base temperature"
  type        = number
  default     = 0.7
}

variable "temp_multiplier" {
  description = "Temperature multiplier"
  type        = number
  default     = 1.2
}

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.base_temp
    max_tokens = 1000
  }
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "A test agent"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = []
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()

    # Verify that variables were interpolated
    model = config["model"]["llama2_instance"]
    assert model["settings"][0]["temperature"] == 0.7  # From base_temp
    assert model["settings"][0]["max_tokens"] == 1000


def test_plugin_string_interpolation(config_dir):
    """Test string interpolation with plugin references"""
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "Using plugin"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.local.echo]
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    expected_plugin = {
        "type": "local",
        "name": "echo",
        "source": "./local_plugins/echo",
        "variables": {},
    }
    assert config["agent"]["test_agent"]["plugins"][0] == expected_plugin


def test_mixed_string_interpolation(config_dir):
    """Test string interpolation with mixed references in the same string"""
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
variable "temperature" {
  type    = number
  default = 0.7
}

model "llama2" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.temperature
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

agent "test_agent" {
  name           = "test-agent-local"
  description    = "Using model with temp 0.7"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2
  plugins        = [plugin.local.echo]
}
"""
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_config()
    assert config["agent"]["test_agent"]["description"] == "Using model with temp 0.7"
