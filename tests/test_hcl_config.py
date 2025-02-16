import os
import pytest
import logging
from agent_runtime.config.hcl_loader import HCLConfigLoader

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
  settings = {
    temperature = var.model_temperature
    max_tokens  = var.model_max_tokens
  }
}

plugin "echo_local" {
  source = "local_plugins/echo"
  variables = {}
}

plugin "echo_remote" {
  source = "github.com/onwardplatforms/agentruntime-plugin-echo"
  version = "v0.0.1"
  variables = {}
}

agent "local" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.echo_local]
}
"""
    )
    logger.info("Test HCL file created successfully")
    return tmp_path


def test_load_local_agent(config_dir):
    """Test loading local agent configuration"""
    logger.info("Starting test_load_local_agent")
    loader = HCLConfigLoader(str(config_dir))
    agents = loader.load_config()
    logger.debug("Loaded agents configuration: %s", agents)

    # Get the local agent configuration
    config = agents["local"]
    logger.debug("Local agent configuration: %s", config)

    # Verify agent configuration
    logger.info("Verifying agent configuration")
    assert config["name"] == "test-agent-local"
    assert (
        config["description"]
        == "A test agent using Ollama provider (Local Development)"
    )
    assert config["system_prompt"] == "You are a helpful AI assistant."

    # Verify model configuration
    logger.info("Verifying model configuration")
    logger.debug("Model configuration: %s", config["model"])
    assert config["model"]["provider"] == "ollama"
    assert config["model"]["name"] == "llama2"
    logger.debug("Model settings: %s", config["model"]["settings"])
    assert config["model"]["settings"]["temperature"] == 0.7
    assert config["model"]["settings"]["max_tokens"] == 1000

    # Verify plugin configuration
    logger.info("Verifying plugin configuration")
    assert len(config["plugins"]) == 1
    plugin = config["plugins"][0]
    logger.debug("Plugin configuration: %s", plugin)
    assert plugin["source"] == "local_plugins/echo"
    assert "version" not in plugin  # Local plugins don't require version
    logger.info("test_load_local_agent completed successfully")


def test_variable_interpolation(config_dir):
    """Test variable interpolation in model settings"""
    logger.info("Starting test_variable_interpolation")
    loader = HCLConfigLoader(str(config_dir))
    loader.load_config()

    # Log the state after loading
    logger.debug("Variables after loading: %s", loader.variables)
    logger.debug("Models after loading: %s", loader.models)

    # Verify that variables were interpolated in model settings
    model = loader.models["llama2_instance"]
    logger.debug("Model settings before assertion: %s", model["settings"])
    assert model["settings"]["temperature"] == 0.7  # From variable default
    assert model["settings"]["max_tokens"] == 1000  # From variable default
    logger.info("test_variable_interpolation completed successfully")


def test_plugin_validation():
    """Test plugin configuration validation"""
    logger.info("Starting test_plugin_validation")
    loader = HCLConfigLoader("dummy_path")  # Path not used for this test

    # Test missing source
    logger.info("Testing plugin with missing source")
    loader.plugins = {"invalid_plugin": {"variables": {}}}
    with pytest.raises(ValueError, match="missing required 'source' field"):
        loader._process_plugins()

    # Test missing version for remote plugin
    logger.info("Testing remote plugin with missing version")
    loader.plugins = {
        "invalid_remote": {
            "source": "onwardplatforms.com/some-plugin",
            "variables": {},
        }
    }
    with pytest.raises(ValueError, match="missing required 'version' field"):
        loader._process_plugins()
    logger.info("test_plugin_validation completed successfully")


def test_runtime_version(config_dir):
    """Test runtime version is correctly loaded"""
    logger.info("Starting test_runtime_version")
    loader = HCLConfigLoader(str(config_dir))
    loader.load_config()

    logger.debug("Runtime configuration: %s", loader.runtime)
    assert loader.runtime["required_version"] == "0.0.1"
    logger.info("test_runtime_version completed successfully")


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
  settings = {
    temperature = var.model_temperature  # var.name syntax
  }
}

plugin "echo_local" {
  source = "local_plugins/echo"
  variables = {}
}

agent "local" {
  name           = "test-agent-local"
  description    = "Using temperature ${var.model_temperature}"  # String interpolation
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance  # type.name syntax
  plugins        = [plugin.echo_local]  # type.name syntax in list
}
"""
    )

    loader = HCLConfigLoader(str(config_dir))
    agents = loader.load_config()
    config = agents["local"]

    # Test variable interpolation with var.name syntax
    assert config["description"] == "Using temperature 0.7"
    assert config["model"]["settings"]["temperature"] == 0.7

    # Test model interpolation with type.name syntax
    assert config["model"]["provider"] == "ollama"
    assert config["model"]["name"] == "llama2"

    # Test plugin interpolation with type.name syntax
    assert len(config["plugins"]) == 1
    assert config["plugins"][0]["source"] == "local_plugins/echo"


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
  settings = {
    temperature = var.nonexistent  # Reference to non-existent variable
  }
}

agent "local" {
  name           = "test-agent-local"
  description    = "A test agent"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.nonexistent  # Reference to non-existent model
  plugins        = [plugin.nonexistent]  # Reference to non-existent plugin
}
"""
    )

    loader = HCLConfigLoader(str(config_dir))
    with pytest.raises(ValueError, match="Model referenced by agent 'local' not found"):
        agents = loader.load_config()


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
  settings = {
    temperature = var.base_temp
    nested = {
      deep = var.base_temp
      deeper = {
        deepest = var.temp_multiplier
      }
    }
  }
}

agent "local" {
  name           = "test-agent-local"
  description    = "A test agent"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  settings = {
    list_with_vars = [var.base_temp, var.temp_multiplier]
    dict_with_vars = {
      first = var.base_temp
      second = var.temp_multiplier
    }
  }
}
"""
    )

    loader = HCLConfigLoader(str(config_dir))
    agents = loader.load_config()
    config = agents["local"]

    # Test nested variable interpolation in model settings
    model = config["model"]
    assert model["settings"]["temperature"] == 0.7
    assert model["settings"]["nested"]["deep"] == 0.7
    assert model["settings"]["nested"]["deeper"]["deepest"] == 1.2

    # Test variable interpolation in lists and dicts
    assert config["settings"]["list_with_vars"] == [0.7, 1.2]
    assert config["settings"]["dict_with_vars"]["first"] == 0.7
    assert config["settings"]["dict_with_vars"]["second"] == 1.2


def test_plugin_string_interpolation(config_dir):
    """Test string interpolation with plugin references"""
    agent_hcl = config_dir / "agent.hcl"
    agent_hcl.write_text(
        """
plugin "echo_local" {
  source = "local_plugins/echo"
  variables = {}
}

agent "local" {
  name           = "test-agent-local"
  description    = "Using plugin ${plugin.echo_local}"
  system_prompt  = "You are a helpful AI assistant."
  plugins        = [plugin.echo_local]
}
"""
    )

    loader = HCLConfigLoader(str(config_dir))
    agents = loader.load_config()
    config = agents["local"]

    # Test plugin string interpolation
    assert "local_plugins/echo" in config["description"]


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
  settings = {
    temperature = var.temperature
  }
}

plugin "echo_local" {
  source = "local_plugins/echo"
  variables = {}
}

agent "local" {
  name           = "test-agent-local"
  description    = "Using model ${model.llama2} with temp ${var.temperature} and plugin ${plugin.echo_local}"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2
  plugins        = [plugin.echo_local]
}
"""
    )

    loader = HCLConfigLoader(str(config_dir))
    agents = loader.load_config()
    config = agents["local"]

    # Test mixed string interpolation
    assert "llama2" in config["description"]  # From model name
    assert "0.7" in config["description"]  # From variable
    assert "local_plugins/echo" in config["description"]  # From plugin source
