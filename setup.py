"""Setup script for the agent_foundry package."""

import os
import re

from setuptools import find_packages, setup  # type: ignore


def get_version():
    """Get the version of the package."""
    init_path = os.path.join("agent_foundry", "__init__.py")
    with open(init_path) as f:
        content = f.read()
        match = re.search(r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content)
        if match:
            return match.group(1)
        raise RuntimeError("Unable to find version string.")


setup(
    name="agent_foundry",
    version=get_version(),
    packages=find_packages(),
    package_dir={"": "."},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "foundry=agent_foundry.cli.cli:cli",
        ],
    },
)
