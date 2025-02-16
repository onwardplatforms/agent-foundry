import logging
import os
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Literal, Tuple
import time
import shutil
from datetime import datetime
import subprocess
import tempfile

try:
    from semantic_kernel.functions.kernel_function_decorator import kernel_function
except ImportError:
    # Fallback if not running inside Semantic Kernel
    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)

# ANSI color codes
GRAY = "\033[90m"
RESET = "\033[0m"


def print_action(message: str) -> None:
    """Print an agent action message in gray."""
    print(f"{GRAY}» {message}...{RESET}")


class ChangeType(Enum):
    """Types of code changes that can be made."""

    UPDATE = "update"
    DELETE = "delete"
    INSERT = "insert"


@dataclass
class CodeSnippet:
    """Represents a snippet of code with context for reliable matching."""

    content: str
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    context_before: List[str]  # Lines before the snippet
    context_after: List[str]  # Lines after the snippet
    hash: Optional[str] = None  # Hash of normalized content


class CodeEditorV2Plugin:
    """
    CodeEditorV2Plugin: A more reliable and consistent code editing plugin
    built around snippet matching and Git-based change tracking.

    Groups of functionality:
    1. Core Code Modification - snippet-based code changes
    2. File Operations - basic file system operations
    3. Change Management - Git-based change tracking and control
    4. Search and Discovery - code searching capabilities
    5. System Operations - shell and system interaction
    """

    PLUGIN_INSTRUCTIONS = """
    Code Editor V2 Plugin - Usage Guide
    =================================

    WORKFLOW FOR CODE CHANGES:
    1. READ FIRST: Always read and understand the code before making changes
       - Use search_code to find relevant code
       - Read the complete content of files you plan to modify
       - Understand the structure and dependencies

    2. PLAN CHANGES:
       - Identify the exact snippets to modify
       - Consider how changes might affect other parts of the code
       - Plan your changes before executing them

    3. EXECUTE CHANGES:
       - Use update_code/delete_code/add_code with exact snippets
       - Make complete, coherent changes - not partial fixes
       - Verify changes match your intentions

    4. VERIFY CHANGES:
       - Review the changes before applying
       - Check for syntax errors or structural issues
       - Verify all issues were addressed

    5. COMMUNICATE CLEARLY:
       - Explain what you changed and why
       - If you're unsure about something, say so
       - If you need more information, ask for it

    Remember: Think like a human programmer. Don't rush to make changes without understanding the full context.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        """
        Initialize the code editor plugin.

        Args:
            workspace_root: Root directory of the workspace. Defaults to current directory.
        """
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()
        self._pending_changes: Dict[str, List[CodeChange]] = {}
        self.git_editor = GitBackedCodeEditor(self.workspace_root)

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Resolve and verify that 'path' is inside the workspace root.

        Args:
            path (Union[str, Path]): File or directory path (relative or absolute)

        Returns:
            Path: The fully resolved path within the workspace

        Raises:
            ValueError: If path is outside workspace root
        """
        try:
            # Convert to Path object if it's a string
            path_obj = Path(path)

            # For relative paths, join with workspace_root
            if not path_obj.is_absolute():
                full_path = (self.workspace_root / path_obj).resolve()
            else:
                # For absolute paths, resolve first then check if it's under workspace_root
                full_path = path_obj.resolve()

            # Resolve both paths to handle symlinks
            workspace_root_resolved = self.workspace_root.resolve()
            full_path_resolved = full_path.resolve()

            # Convert paths to strings for comparison to handle symlinks
            try:
                str(full_path_resolved).startswith(str(workspace_root_resolved))
            except ValueError:
                raise ValueError(f"Path {path} is outside workspace root")

            return full_path_resolved

        except Exception as e:
            raise ValueError(f"Invalid path {path}: {str(e)}")
