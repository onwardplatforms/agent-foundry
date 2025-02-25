import logging
import sys
from typing import Dict, Optional, Union, List


# Define log levels for easier reference
class LogLevel:
    # Standard log levels
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    # Custom NONE level (higher than CRITICAL) to disable all logging
    NONE = logging.CRITICAL + 10


# Register our custom NONE level with the logging system
logging.addLevelName(LogLevel.NONE, "NONE")


def configure_logging(
    level: int = LogLevel.NONE,  # Default to NONE (no logs)
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    specific_loggers: Optional[Dict[str, int]] = None,
    log_file: Optional[str] = None,
) -> None:
    """Configure global logging settings.

    Args:
        level: The global logging level (default: NONE - no logs)
        format_string: Format string for log messages
        specific_loggers: Dictionary mapping logger names to specific levels
        log_file: Optional file path to write logs to
    """
    # Set up handlers
    handlers = []

    # Always add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(format_string))
    handlers.append(console_handler)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_string))
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our handlers
    for handler in handlers:
        root_logger.addHandler(handler)

    # Configure specific loggers if provided
    if specific_loggers:
        for logger_name, logger_level in specific_loggers.items():
            logging.getLogger(logger_name).setLevel(logger_level)


def set_verbose_mode(enable: bool = True) -> None:
    """Enable or disable verbose logging (shortcut method).

    Args:
        enable: Whether to enable verbose logging
    """
    level = LogLevel.DEBUG if enable else LogLevel.INFO

    # Update root logger level
    logging.getLogger().setLevel(level)

    # Update all existing handlers
    for handler in logging.getLogger().handlers:
        handler.setLevel(level)


def set_logger_levels(logger_levels: Dict[str, int]) -> None:
    """Set specific logger levels.

    Args:
        logger_levels: Dictionary mapping logger names to levels
    """
    for logger_name, level in logger_levels.items():
        logging.getLogger(logger_name).setLevel(level)
