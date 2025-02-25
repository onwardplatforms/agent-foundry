"""Test script for the HelloPlugin with variables."""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from agent_runtime_v2.plugins.sources import LocalPluginSource
from agent_runtime_v2.plugins.manager import PluginManager

# Load environment variables
load_dotenv()


async def main():
    """Run a simple test of the HelloPlugin with variables."""
    # Create a plugin manager
    plugin_manager = PluginManager()

    # Get the path to the hello plugin
    plugin_path = os.path.join(os.path.dirname(__file__), "plugins/hello")
    print(f"Plugin path: {plugin_path}")

    # Load the plugin with a custom default_name
    plugin = await plugin_manager.load_plugin(
        LocalPluginSource(Path(plugin_path)), variables={"default_name": "Friend"}
    )

    print(f"Loaded plugin: {plugin.name}")
    print(f"Default name: {plugin.default_name}")

    # Test the greet function
    print("\nTesting greet with no name:")
    print(plugin.greet())

    print("\nTesting greet with a name:")
    print(plugin.greet("Alice"))


if __name__ == "__main__":
    # Run the test
    asyncio.run(main())
