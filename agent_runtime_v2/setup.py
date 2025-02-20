from setuptools import setup, find_packages

setup(
    name="agent_runtime_v2",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "semantic-kernel>=0.9.0",
        "openai>=1.0.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "test": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
        ]
    },
)
