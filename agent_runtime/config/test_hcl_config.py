# import os
# import pytest
# from .hcl_loader import HCLConfigLoader


# def test_load_remote_agent():
#     loader = HCLConfigLoader("agentproject2")
#     config = loader.load_config("agent.hcl")

#     # Verify agent configuration
#     assert config["name"] == "test-agent"
#     assert config["system_prompt"] == "Always say Jeff"

#     # Verify model configuration
#     assert config["model"]["provider"] == "ollama"
#     assert config["model"]["name"] == "llama2"
#     assert config["model"]["settings"]["temperature"] == 0.7
#     assert config["model"]["settings"]["max_tokens"] == 1000

#     # Verify plugin configuration
#     assert len(config["plugins"]) == 1
#     plugin = config["plugins"][0]
#     assert plugin["source"] == "onwardplatforms.com/agentruntime-plugin-echo"
#     assert plugin["version"] == "v0.0.1"


# def test_load_local_agent():
#     loader = HCLConfigLoader("agentproject2")
#     config = loader.load_config("agent.hcl")  # We now have both in agent.hcl

#     # Get the local agent configuration
#     config = loader.agents["local"]

#     # Verify agent configuration
#     assert config["name"] == "test-agent-local"
#     assert config["system_prompt"] == "You are a helpful AI assistant."

#     # Verify plugin configuration
#     assert len(config["plugins"]) == 1
#     plugin = config["plugins"][0]
#     assert plugin["source"] == "local_plugins/echo"
#     assert "version" not in plugin  # Local plugins don't require version


# def test_plugin_validation():
#     # Test missing source
#     with pytest.raises(ValueError, match="missing required 'source' field"):
#         loader = HCLConfigLoader("tests/fixtures")
#         loader._process_plugins({"plugin": {"invalid_plugin": {"variables": {}}}})

#     # Test missing version for remote plugin
#     with pytest.raises(ValueError, match="missing required 'version' field"):
#         loader = HCLConfigLoader("tests/fixtures")
#         loader._process_plugins(
#             {
#                 "plugin": {
#                     "invalid_remote": {
#                         "source": "onwardplatforms.com/some-plugin",
#                         "variables": {},
#                     }
#                 }
#             }
#         )


# def test_variable_interpolation():
#     loader = HCLConfigLoader("agentproject2")
#     config = loader.load_config("agent.hcl")

#     # Verify that variables were interpolated in model settings
#     model = loader.models["llama2_instance"]
#     assert model["settings"]["temperature"] == 0.7  # From variable default
#     assert model["settings"]["max_tokens"] == 1000  # From variable default


# if __name__ == "__main__":
#     # Run tests
#     print("Running tests...")

#     try:
#         test_load_remote_agent()
#         print("✓ Remote agent configuration test passed")

#         test_load_local_agent()
#         print("✓ Local agent configuration test passed")

#         test_plugin_validation()
#         print("✓ Plugin validation test passed")

#         test_variable_interpolation()
#         print("✓ Variable interpolation test passed")

#         print("\nAll tests passed successfully!")
#     except AssertionError as e:
#         print(f"\n❌ Test failed: {str(e)}")
#     except Exception as e:
#         print(f"\n❌ Error: {str(e)}")
