from setuptools import setup

setup(
    name="agent-foundry",
    version="0.1.0",
    py_modules=['cli'],
    install_requires=[
        "click",
        "openai",
        "python-dotenv",
        "uuid",
    ],
    entry_points={
        "console_scripts": [
            "foundry=cli:cli",
        ],
    },
) 