# Utility Modules

## Logging Configuration

The logging configuration system provides a centralized way to manage logging levels and formats across the agent runtime.

### Basic Usage

```python
from agent_runtime_v2.utils import configure_logging, LogLevel

# Configure global logging with INFO level (default)
configure_logging(level=LogLevel.INFO)

# Configure with DEBUG level for more detailed logs
configure_logging(level=LogLevel.DEBUG)

# Configure with specific loggers at different levels
configure_logging(
    level=LogLevel.INFO,
    specific_loggers={
        "agent_runtime_v2.plugins": LogLevel.DEBUG,
        "semantic_kernel.kernel": LogLevel.WARNING,
    }
)

# Configure with log file output
configure_logging(
    level=LogLevel.INFO,
    log_file="agent_runtime.log"
)
```

### Available Modules

- `logging.py`: Core logging configuration utilities

### Quick Level Changes

You can easily toggle between verbose (DEBUG) and normal (INFO) logging using the `set_verbose_mode` function:

```python
from agent_runtime_v2.utils import set_verbose_mode

# Enable verbose logging (DEBUG level)
set_verbose_mode(True)

# Disable verbose logging (INFO level)
set_verbose_mode(False)
```

### Command Line Integration

The logging system is designed to integrate with command line arguments. Here's a typical pattern:

```python
import argparse
from agent_runtime_v2.utils import configure_logging, LogLevel

def parse_args():
    parser = argparse.ArgumentParser(description="Application Description")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    parser.add_argument(
        "--log-file",
        help="Log to a file in addition to console"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    # Configure logging based on command line arguments
    log_level = LogLevel.DEBUG if args.verbose else LogLevel.INFO
    configure_logging(
        level=log_level,
        log_file=args.log_file
    )

    # Rest of your application...
```

### Log Levels

The `LogLevel` class provides constants for standard log levels:

- `LogLevel.DEBUG`: Detailed information, typically useful only for diagnosing problems
- `LogLevel.INFO`: Confirmation that things are working as expected
- `LogLevel.WARNING`: Indication that something unexpected happened, but the application is still working
- `LogLevel.ERROR`: Due to a more serious problem, the application hasn't been able to perform some function
- `LogLevel.CRITICAL`: A very serious error, indicating that the application may be unable to continue running
