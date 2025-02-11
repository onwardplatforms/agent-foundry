"""Styled output formatting for the CLI."""

import click


class Style:
    """Terminal styling constants."""

    HEADER = click.style("»", fg="cyan", bold=True)
    SUCCESS = click.style("✓", fg="green", bold=True)
    ERROR = click.style("✗", fg="red", bold=True)
    WARNING = click.style("!", fg="yellow", bold=True)
    INFO = click.style("»", fg="blue", bold=True)

    @staticmethod
    def header(text: str) -> str:
        """Format a header message."""
        return f"\n{Style.HEADER} {click.style(text, bold=True)}\n"

    @staticmethod
    def success(text: str) -> str:
        """Format a success message."""
        return f"{Style.SUCCESS} {text}"

    @staticmethod
    def error(text: str) -> str:
        """Format an error message."""
        return f"{Style.ERROR} {text}"

    @staticmethod
    def warning(text: str) -> str:
        """Format a warning message."""
        return f"{Style.WARNING} {text}"

    @staticmethod
    def info(text: str) -> str:
        """Format an info message."""
        return f"{Style.INFO} {text}"

    @staticmethod
    def plugin_status(name: str, status: str, color: str = "green") -> str:
        """Format a plugin status message."""
        return f"  {click.style('•', fg=color)} {name}: {click.style(status, fg=color)}"
