import os
import pytest
from agent_runtime.config.hcl_loader import HCLConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary directory with test HCL files"""
    # Create agent.hcl
    agent_hcl = tmp_path / "agent.hcl"
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
  source = "onwardplatforms.com/agentruntime-plugin-echo"
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

    return tmp_path


def test_load_local_agent(config_dir):
    """Test loading local agent configuration"""
    loader = HCLConfigLoader(str(config_dir))
    config = loader.load_config("agent.hcl")

    # Get the local agent configuration
    config = loader.agents["local"]

    # Verify agent configuration
    assert config["name"] == "test-agent-local"
    assert (
        config["description"]
        == "A test agent using Ollama provider (Local Development)"
    )
    assert config["system_prompt"] == "You are a helpful AI assistant."

    # Verify model configuration
    assert config["model"]["provider"] == "ollama"
    assert config["model"]["name"] == "llama2"
    assert config["model"]["settings"]["temperature"] == 0.7
    assert config["model"]["settings"]["max_tokens"] == 1000

    # Verify plugin configuration
    assert len(config["plugins"]) == 1
    plugin = config["plugins"][0]
    assert plugin["source"] == "local_plugins/echo"
    assert "version" not in plugin  # Local plugins don't require version


def test_variable_interpolation(config_dir):
    """Test variable interpolation in model settings"""
    loader = HCLConfigLoader(str(config_dir))
    loader.load_config("agent.hcl")

    # Verify that variables were interpolated in model settings
    model = loader.models["llama2_instance"]
    assert model["settings"]["temperature"] == 0.7  # From variable default
    assert model["settings"]["max_tokens"] == 1000  # From variable default


def test_plugin_validation():
    """Test plugin configuration validation"""
    loader = HCLConfigLoader("dummy_path")  # Path not used for this test

    # Test missing source
    with pytest.raises(ValueError, match="missing required 'source' field"):
        loader._process_plugins({"plugin": {"invalid_plugin": {"variables": {}}}})

    # Test missing version for remote plugin
    with pytest.raises(ValueError, match="missing required 'version' field"):
        loader._process_plugins(
            {
                "plugin": {
                    "invalid_remote": {
                        "source": "onwardplatforms.com/some-plugin",
                        "variables": {},
                    }
                }
            }
        )


def test_runtime_version(config_dir):
    """Test runtime version is correctly loaded"""
    loader = HCLConfigLoader(str(config_dir))
    loader.load_config("agent.hcl")

    assert loader.runtime["required_version"] == "0.0.1"
