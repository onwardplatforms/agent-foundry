from setuptools import setup, find_packages

setup(
    name="foundry",
    version="0.1",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Click",
        "semantic-kernel",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "foundry=foundry.cli:cli",
        ],
    },
) 