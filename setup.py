"""Setup configuration for Agent Foundry."""

from setuptools import find_packages, setup

setup(
    name="agent_foundry",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click",
        "semantic-kernel",
        "python-dotenv",
        "uuid",
    ],
    entry_points={
        "console_scripts": [
            "foundry=agent_foundry.cli.commands:cli",
        ],
    },
)
