"""Setup script for the agent-foundry package."""

from setuptools import setup  # type: ignore

setup(
    name="agent-foundry",
    packages=["agent_foundry"],
    package_dir={"": "."},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "foundry=agent_foundry.__main__:main",
        ],
    },
)
