"""Common utilities for Agent Runtime."""

import click


class Style:
    """Consistent styling for CLI output."""

    @staticmethod
    def header(text: str) -> str:
        """Style for section headers."""
        return click.style(text, bold=True)

    @staticmethod
    def success(text: str) -> str:
        """Style for success messages."""
        return click.style(text, fg="green")

    @staticmethod
    def error(text: str, bold: bool = True) -> str:
        """Style for error messages."""
        return click.style(text, fg="red", bold=bold)

    @staticmethod
    def info(text: str) -> str:
        """Style for informational messages."""
        return click.style(text, fg="blue")

    @staticmethod
    def plugin_status(name: str, status: str, color: str = "green") -> str:
        """Style for plugin status messages."""
        return f"  {click.style('•', fg=color)} {name}: {click.style(status, fg=color)}"
