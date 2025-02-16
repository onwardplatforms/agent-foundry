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

    def __post_init__(self):
        """Validate and normalize the snippet after creation."""
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.hash is None:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of normalized content."""
        normalized = self._normalize_content(self.content)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def matches(
        self, other: "CodeSnippet", fuzzy: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Check if this snippet matches another.

        Args:
            other: Another CodeSnippet to compare with
            fuzzy: If True, use fuzzy matching (ignoring whitespace differences)

        Returns:
            tuple[bool, Optional[str]]: (matched, match_type) where match_type is 'exact', 'fuzzy', or None
        """
        # Try exact match first
        if self.hash == other.hash:
            return True, "exact"

        # Try fuzzy match if enabled
        if fuzzy:
            # Remove all whitespace for comparison
            this_stripped = "".join(self.content.split())
            other_stripped = "".join(other.content.split())

            if this_stripped == other_stripped:
                return True, "fuzzy"

        return False, None

    def _normalize_content(self, content: str) -> str:
        """
        Normalize content for comparison by preserving indentation and empty lines.

        Args:
            content (str): The content to normalize

        Returns:
            str: Normalized content
        """
        lines = []
        for line in content.splitlines():
            # Remove trailing whitespace but preserve leading whitespace
            line = line.rstrip()
            # Normalize indentation to use spaces
            if line:
                indent = len(line) - len(line.lstrip())
                normalized_line = " " * indent + line.lstrip()
                lines.append(normalized_line)
            else:
                lines.append("")  # Preserve empty lines

        return "\n".join(lines)


@dataclass
class CodeChange:
    """Represents a change to be made to a file."""

    file_path: str
    change_type: ChangeType
    target_snippet: CodeSnippet
    new_content: Optional[str] = None
    position: Optional[Literal["before", "after"]] = None

    def __post_init__(self):
        """Validate the change after creation."""
        if self.change_type == ChangeType.UPDATE and self.new_content is None:
            raise ValueError("new_content required for UPDATE changes")
        if self.change_type == ChangeType.INSERT:
            if self.new_content is None:
                raise ValueError("new_content required for INSERT changes")
            if self.position not in ["before", "after"]:
                raise ValueError(
                    "position must be 'before' or 'after' for INSERT changes"
                )


@dataclass
class MatchResult:
    """Result of attempting to match a snippet in a file."""

    matched: bool
    start_line: Optional[int] = None  # 1-based
    end_line: Optional[int] = None  # 1-based, inclusive
    match_type: Optional[Literal["exact", "fuzzy"]] = None
    context_matches: bool = False
    error_message: Optional[str] = None


@dataclass
class ProcessResult:
    """Result of a process execution."""

    command: str
    return_code: int
    stdout: str
    stderr: str
    duration: float
    killed: bool = False
    error: Optional[str] = None

    def format_output(self) -> str:
        """Format the process result for display."""
        parts = []
        parts.append(f"Command: {self.command}")

        if self.stdout:
            parts.extend(["", "Output:", self.stdout.strip()])
        if self.stderr:
            parts.extend(["", "Errors:", self.stderr.strip()])

        parts.append(f"Duration: {self.duration:.2f}s")

        if self.killed:
            parts.append("Status: Killed")
        elif self.error:
            parts.append(f"Status: Error - {self.error}")
        else:
            parts.append(f"Exit Code: {self.return_code}")

        return "\n".join(parts)


class GitBackedCodeEditor:
    """Git-based code editor for reliable change tracking."""

    def __init__(self, workspace_root: Path):
        """Initialize with workspace root directory."""
        self.workspace_root = workspace_root.resolve()
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()

        # Initialize Git repository
        subprocess.run(
            ["git", "init"], cwd=self.temp_dir, check=True, capture_output=True
        )

        # Configure Git
        subprocess.run(
            ["git", "config", "user.name", "Code Editor"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "code.editor@local"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

        # Create .gitignore to exclude temporary files
        (self.temp_dir / ".gitignore").write_text("*.pyc\n__pycache__\n.DS_Store\n")

        # Stage .gitignore
        subprocess.run(
            ["git", "add", ".gitignore"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

        # Initial commit
        subprocess.run(
            ["git", "commit", "-m", "Initial repository setup"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

    def _stage_file_for_edit(self, file_path: Union[str, Path]) -> Path:
        """
        Stage a file for editing by copying it to the temporary Git repository.

        Args:
            file_path: Path to the file to stage

        Returns:
            Path: Path to the staged file in the temporary repository
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Create parent directories if they don't exist
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy the file to the temp directory if it exists
            if file_path.exists():
                shutil.copy2(file_path, temp_path)
            else:
                # Create an empty file
                temp_path.touch()

            # Stage the file in Git
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Check if file is already tracked
            status = subprocess.run(
                ["git", "status", "--porcelain", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Only commit if the file is not already tracked
            if status.startswith("??") or status.startswith("A"):
                try:
                    subprocess.run(
                        ["git", "commit", "-m", f"Initial state for {rel_path}"],
                        cwd=self.temp_dir,
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    # If commit fails (e.g., no changes), that's okay
                    pass

            return temp_path
        except ValueError as e:
            raise ValueError(f"Invalid path {file_path}: {str(e)}")

    def apply_changes(self, file_path: Union[str, Path]):
        """
        Apply changes to a file by committing them in Git and copying back to workspace.

        Args:
            file_path: Path to the file to apply changes to
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Stage any changes
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Commit changes
            subprocess.run(
                ["git", "commit", "-m", f"Update {rel_path}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Copy the file back to the workspace
            shutil.copy2(temp_path, file_path)
        except ValueError as e:
            raise ValueError(f"Invalid path {file_path}: {str(e)}")

    def revert_changes(self, file_path: Union[str, Path], num_changes: int = 1) -> str:
        """
        Revert changes to a file using Git.

        Args:
            file_path: Path to the file to revert
            num_changes: Number of changes to revert

        Returns:
            str: Success message or error
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Get the current commit hash
            current = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Get the target commit hash
            target = subprocess.run(
                ["git", "rev-parse", f"HEAD~{num_changes}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Checkout the file from the target commit
            subprocess.run(
                ["git", "checkout", target, "--", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Stage and commit the revert
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Revert {rel_path} to {target[:7]}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Copy the file back to the workspace
            shutil.copy2(temp_path, file_path)

            return f"Successfully reverted {num_changes} change(s) to {rel_path}"
        except Exception as e:
            return f"Error reverting changes: {str(e)}"

    def get_change_history(self, file_path: Union[str, Path]) -> str:
        """
        Get the Git history for a file.

        Args:
            file_path: Path to the file to get history for

        Returns:
            str: Git log with patches
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)

            # Get the Git log with patches
            result = subprocess.run(
                ["git", "log", "-p", "--", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            return result.stdout
        except Exception as e:
            return f"Error getting change history: {str(e)}"

    def __del__(self):
        """Clean up temporary directory when the object is destroyed."""
        try:
            shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")


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

        # Create a file handler
        log_file = self.workspace_root / "code_editor.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Create a formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        self.logger.addHandler(file_handler)

        self.logger.debug(
            "CodeEditorV2Plugin initialized with Git-based version control"
        )

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Resolve and verify that 'path' is inside the workspace root.

        Args:
            path (Union[str, Path]): File or directory path (relative or absolute)

        Returns:
            Path: The fully resolved path within the workspace

        Raises:
            ValueError: If path is empty, invalid, or outside workspace root
        """
        try:
            # Check for empty path
            if not path:
                raise ValueError("Path cannot be empty")

            # Convert to Path object if it's a string
            path_obj = Path(path)

            # Check for parent directory traversal
            if ".." in str(path_obj):
                raise ValueError("Path cannot contain parent directory traversal (..)")

            # For relative paths, join with workspace_root
            if not path_obj.is_absolute():
                full_path = (self.workspace_root / path_obj).resolve()
            else:
                # For absolute paths, resolve first then check if it's under workspace_root
                full_path = path_obj.resolve()

            # Resolve both paths to handle symlinks (especially on macOS where /var -> /private/var)
            workspace_resolved = self.workspace_root.resolve()
            path_resolved = full_path.resolve()

            # Convert both to strings for prefix comparison to handle symlinks
            if not str(path_resolved).startswith(str(workspace_resolved)):
                raise ValueError(f"Path {path} is outside workspace root")

            return full_path

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Invalid path {path}: {str(e)}")

    # -------------------------------------------------------------------------
    # File Operations Group
    # -------------------------------------------------------------------------

    @kernel_function(description="Read the contents of a file.")
    def read_file(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Read entire file or specific line range.

        Args:
            path (str): Path to the file to read
            start_line (int, optional): First line to read (1-based)
            end_line (int, optional): Last line to read (1-based)

        Returns:
            str: File contents or specified line range

        Raises:
            ValueError: If path is invalid or outside workspace root
        """
        # Let ValueError propagate from _validate_path
        file_path = self._validate_path(path)
        if not file_path.is_file():
            return f"Error: File '{path}' does not exist or is not a regular file."

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if start_line is None and end_line is None:
                    return f.read()

                lines = f.readlines()
                start_idx = (start_line or 1) - 1
                end_idx = end_line if end_line is None else min(end_line, len(lines))
                return "".join(lines[start_idx:end_idx])

        except UnicodeDecodeError:
            raise  # Let UnicodeDecodeError propagate for binary files
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @kernel_function(description="Write content to a file (overwriting).")
    def write_file(self, path: str, content: str) -> str:
        """
        Write content to a file, creating directories if needed.

        Args:
            path (str): Path to write to
            content (str): Content to write

        Returns:
            str: Success message or error

        Raises:
            ValueError: If path is invalid or outside workspace root
        """
        # Let ValueError propagate from _validate_path
        file_path = self._validate_path(path)

        try:
            print_action(f"Writing content to {path}")
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to file: {path}"

        except Exception as e:
            return f"Error writing file: {str(e)}"

    @kernel_function(description="Delete a file or directory.")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """
        Delete a file or directory.

        Args:
            path (str): Path to delete
            recursive (bool): Whether to recursively delete directories

        Returns:
            str: Success message or error
        """
        import shutil

        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            if target_path.is_file():
                print_action(f"Deleting file {path}")
                logger.debug(f"Deleting file: {path}")
                target_path.unlink()
                return f"Successfully deleted file: {path}"
            elif target_path.is_dir():
                if not recursive:
                    return f"Error: '{path}' is a directory. Use recursive=True to delete directories."
                print_action(f"Recursively deleting directory {path}")
                logger.debug(f"Recursively deleting directory: {path}")
                shutil.rmtree(target_path)
                return f"Successfully deleted directory: {path}"
            else:
                return f"Error: '{path}' is neither a file nor a directory."

        except Exception as e:
            logger.error(f"Error deleting {path}: {str(e)}")
            return f"Error deleting file or directory: {str(e)}"

    @kernel_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".", max_depth: int = None) -> str:
        """
        List contents of a directory in a tree-like format.

        Args:
            path (str): Directory to list
            max_depth (int, optional): Maximum depth for recursive listing. None means no limit.

        Returns:
            str: Tree-formatted directory listing
        """
        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            print_action(f"Generating directory tree for {path}")
            logger.debug(f"Listing directory tree for: {path}")

            def format_size(size_bytes: int) -> str:
                """Format file size in human-readable format."""
                for unit in ["B", "KB", "MB", "GB"]:
                    if size_bytes < 1024:
                        return f"{size_bytes:.1f}{unit}"
                    size_bytes /= 1024
                return f"{size_bytes:.1f}TB"

            def generate_tree(
                directory: Path, prefix: str = "", is_last: bool = True, depth: int = 0
            ) -> List[str]:
                """Recursively generate tree structure."""
                if max_depth is not None and depth > max_depth:
                    return []

                entries = sorted(
                    directory.iterdir(), key=lambda e: (e.is_file(), e.name)
                )
                tree_lines = []

                for i, entry in enumerate(entries):
                    is_last_entry = i == len(entries) - 1

                    # Determine the correct prefix characters
                    if is_last_entry:
                        entry_prefix = prefix + "└── "
                        next_prefix = prefix + "    "
                    else:
                        entry_prefix = prefix + "├── "
                        next_prefix = prefix + "│   "

                    # Add entry with size for files
                    if entry.is_file():
                        size = format_size(entry.stat().st_size)
                        tree_lines.append(f"{entry_prefix}{entry.name} ({size})")
                    else:
                        tree_lines.append(f"{entry_prefix}{entry.name}/")
                        # Recursively process subdirectories
                        tree_lines.extend(
                            generate_tree(entry, next_prefix, is_last_entry, depth + 1)
                        )

                return tree_lines

            # Generate the tree starting from the root
            tree_lines = [str(target_path) + "/"]
            tree_lines.extend(generate_tree(target_path))

            logger.debug(f"Found {len(tree_lines)-1} entries in {path}")
            return "\n".join(tree_lines)

        except Exception as e:
            logger.error(f"Error listing directory {path}: {str(e)}")
            return f"Error listing directory: {str(e)}"

    def _find_snippet_match(
        self,
        file_content: str,
        target: CodeSnippet,
        fuzzy: bool = False,
        context_lines: int = 0,
    ) -> MatchResult:
        """
        Find a matching code snippet in the file content.

        Args:
            file_content: The content to search in
            target: The snippet to find
            fuzzy: Whether to use fuzzy matching
            context_lines: Number of context lines to verify

        Returns:
            MatchResult: The match result
        """
        # Split content into lines for line-by-line comparison
        file_lines = file_content.splitlines()
        if not file_lines:
            return MatchResult(matched=False, error_message="File is empty")

        target_lines = target.content.splitlines()
        if not target_lines:
            # Special case: if target is empty or just whitespace, match any empty line
            for i, line in enumerate(file_lines):
                if not line.strip():
                    return MatchResult(
                        matched=True,
                        start_line=i + 1,
                        end_line=i + 1,
                        match_type="exact",
                        context_matches=True,
                    )
            return MatchResult(matched=False, error_message="No empty lines found")

        # Try to find the snippet
        for i in range(len(file_lines) - len(target_lines) + 1):
            candidate_lines = file_lines[i : i + len(target_lines)]
            candidate = CodeSnippet(
                content="\n".join(candidate_lines),
                start_line=i + 1,
                end_line=i + len(target_lines),
                context_before=file_lines[max(0, i - context_lines) : i],
                context_after=file_lines[
                    i + len(target_lines) : i + len(target_lines) + context_lines
                ],
            )

            if self._matches(target, candidate, fuzzy):
                # Found a match, now verify context if needed
                context_matches = self._verify_context(target, candidate, context_lines)
                match_type = "exact" if target.content == candidate.content else "fuzzy"

                return MatchResult(
                    matched=True,
                    start_line=i + 1,
                    end_line=i + len(target_lines),
                    match_type=match_type,
                    context_matches=context_matches,
                )

        return MatchResult(matched=False, error_message="No matching code found")

    def _verify_context(
        self, target: CodeSnippet, candidate: CodeSnippet, context_lines: int
    ) -> bool:
        """
        Verify that the context lines around a match are similar enough.

        Args:
            target: The snippet we're looking for
            candidate: The snippet we found
            context_lines: Number of context lines to verify

        Returns:
            bool: True if context matches sufficiently
        """
        if context_lines <= 0:
            return True

        def normalize_line(line: str) -> str:
            """Normalize a single line for comparison by removing whitespace."""
            return "".join(line.split())

        # Get the context lines to compare
        target_before = [
            normalize_line(line) for line in target.context_before[-context_lines:]
        ]
        target_after = [
            normalize_line(line) for line in target.context_after[:context_lines]
        ]
        candidate_before = [
            normalize_line(line) for line in candidate.context_before[-context_lines:]
        ]
        candidate_after = [
            normalize_line(line) for line in candidate.context_after[:context_lines]
        ]

        # Pad shorter lists with empty strings to match lengths
        while len(target_before) < context_lines:
            target_before.insert(0, "")
        while len(target_after) < context_lines:
            target_after.append("")
        while len(candidate_before) < context_lines:
            candidate_before.insert(0, "")
        while len(candidate_after) < context_lines:
            candidate_after.append("")

        # Calculate similarity scores
        def similarity_score(list1: List[str], list2: List[str]) -> float:
            """Calculate similarity score between two lists of lines."""
            if not list1 and not list2:
                return 1.0
            matches = sum(1 for a, b in zip(list1, list2) if a == b or not a or not b)
            return matches / max(len(list1), len(list2))

        before_score = similarity_score(target_before, candidate_before)
        after_score = similarity_score(target_after, candidate_after)

        # Consider context matching if similarity is above threshold
        SIMILARITY_THRESHOLD = 0.5  # More lenient threshold
        return (
            before_score >= SIMILARITY_THRESHOLD and after_score >= SIMILARITY_THRESHOLD
        )

    def _similarity_ratio(self, lines1: List[str], lines2: List[str]) -> float:
        """
        Calculate similarity ratio between two lists of lines.

        Args:
            lines1: First list of lines
            lines2: Second list of lines

        Returns:
            float: Similarity ratio (0.0 to 1.0)
        """
        if not lines1 and not lines2:
            return 1.0
        if not lines1 or not lines2:
            return 0.0

        # Compare line by line
        matches = sum(1 for l1, l2 in zip(lines1, lines2) if l1 == l2)
        total = max(len(lines1), len(lines2))
        return matches / total

    def _create_snippet(
        self,
        content: str,
        file_content: Optional[str] = None,
        start_line: Optional[int] = None,
        context_lines: int = 2,
    ) -> CodeSnippet:
        """
        Create a CodeSnippet from content, optionally with context from file.

        Args:
            content: The snippet content
            file_content: Optional full file content for context
            start_line: Optional known start line (1-based)
            context_lines: Number of context lines to include

        Returns:
            CodeSnippet: The created snippet
        """
        snippet_lines = content.splitlines()
        end_line = (
            (start_line + len(snippet_lines) - 1) if start_line else len(snippet_lines)
        )

        context_before = []
        context_after = []

        if file_content and start_line:
            file_lines = file_content.splitlines()
            context_start = max(0, start_line - context_lines - 1)
            context_before = file_lines[context_start : start_line - 1]
            context_after = file_lines[end_line : end_line + context_lines]

        return CodeSnippet(
            content=content,
            start_line=start_line or 1,
            end_line=end_line,
            context_before=context_before,
            context_after=context_after,
        )

    # -------------------------------------------------------------------------
    # Core Code Modification Group
    # -------------------------------------------------------------------------

    @kernel_function(description="Update code that matches a target snippet.")
    def update_code(
        self,
        path: str,
        target_snippet: str,
        new_content: str,
        match_type: Literal["exact", "fuzzy"] = "fuzzy",
        context_lines: int = 2,
    ) -> str:
        """
        Update code that matches a target snippet.

        Args:
            path: Path to the file to update
            target_snippet: The code to find and replace
            new_content: The new code to insert
            match_type: Whether to use exact or fuzzy matching
            context_lines: Number of context lines to use for matching

        Returns:
            str: Result of the operation
        """
        try:
            print_action(f"Updating code in {path}")

            # Stage the file in our Git repo
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.workspace_root / file_path
            temp_path = self.git_editor._stage_file_for_edit(file_path)

            # Read current content
            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create target snippet object
            target = self._create_snippet(
                target_snippet,
                file_content,
                None,  # We don't know the line number yet
                context_lines,
            )

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                logger.warning("Found match but context differs significantly")

            # Get the matched lines and their indentation
            file_lines = file_content.splitlines()
            matched_lines = file_lines[
                match_result.start_line - 1 : match_result.end_line
            ]

            # Calculate base indentation level from the matched block
            base_indent = None
            for line in matched_lines:
                if line.strip():  # Skip empty lines
                    indent = len(line) - len(line.lstrip())
                    if base_indent is None or indent < base_indent:
                        base_indent = indent

            if base_indent is None:
                base_indent = 0

            # Process the new content
            new_lines = new_content.splitlines()

            # Calculate the minimum indentation in the new content
            new_base_indent = None
            for line in new_lines:
                if line.strip():  # Skip empty lines
                    indent = len(line) - len(line.lstrip())
                    if new_base_indent is None or indent < new_base_indent:
                        new_base_indent = indent

            if new_base_indent is None:
                new_base_indent = 0

            # Adjust indentation while preserving relative levels
            indented_lines = []
            for line in new_lines:
                if not line.strip():  # Preserve empty lines as is
                    indented_lines.append(line)
                else:
                    # Calculate relative indentation from base
                    relative_indent = len(line) - len(line.lstrip()) - new_base_indent
                    # Apply base indentation plus relative indentation
                    indented_lines.append(
                        " " * (base_indent + relative_indent) + line.lstrip()
                    )

            new_content = "\n".join(indented_lines)

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.UPDATE,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
                new_content=new_content,
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            start_idx = match_result.start_line - 1
            end_idx = match_result.end_line
            lines[start_idx:end_idx] = new_content.splitlines()
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_action(
                f"Added update change for lines {match_result.start_line}-{match_result.end_line}"
            )
            logger.debug(
                f"Queued update change in {path} "
                f"(lines {match_result.start_line}-{match_result.end_line}, "
                f"match_type={match_result.match_type})"
            )

            return (
                f"Successfully queued update:\n"
                f"- File: {path}\n"
                f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                f"- Match type: {match_result.match_type}\n"
                f"Use verify_changes() to review and apply_changes() to apply"
            )

        except Exception as e:
            logger.error(f"Error updating code in {path}: {str(e)}")
            return f"Error updating code: {str(e)}"

    @kernel_function(description="Delete code that matches a target snippet.")
    def delete_code(
        self,
        path: str,
        target_snippet: str,
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Delete code that matches the target snippet.

        Args:
            path (str): Path to the file to modify
            target_snippet (str): The code snippet to find and delete
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Success message or error
        """
        try:
            print_action(f"Preparing to delete code from {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            # Stage the file in our Git repo
            temp_path = self.git_editor._stage_file_for_edit(str(file_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(target_snippet)

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                logger.warning("Found match but context differs significantly")

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.DELETE,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            del lines[match_result.start_line - 1 : match_result.end_line]
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_action(
                f"Added delete change for lines {match_result.start_line}-{match_result.end_line}"
            )
            logger.debug(
                f"Queued delete change in {path} "
                f"(lines {match_result.start_line}-{match_result.end_line}, "
                f"match_type={match_result.match_type})"
            )

            return (
                f"Successfully queued deletion:\n"
                f"- File: {path}\n"
                f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                f"- Match type: {match_result.match_type}\n"
                f"Use verify_changes() to review and apply_changes() to apply"
            )

        except Exception as e:
            logger.error(f"Error deleting code from {path}: {str(e)}")
            return f"Error deleting code: {str(e)}"

    @kernel_function(description="Insert code at a specific position in a file.")
    def insert_code(
        self,
        path: str,
        new_content: str,
        position: Literal["before", "after"],
        target_snippet: str,
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Insert new code at a specific position in a file.

        Args:
            path (str): Path to the file to modify
            new_content (str): The new code to insert
            position (str): Position to insert the code ('before' or 'after')
            target_snippet (str): The code snippet to find for insertion
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Success message or error
        """
        try:
            print_action(f"Preparing to insert code into {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            # Stage the file in our Git repo
            temp_path = self.git_editor._stage_file_for_edit(str(file_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(target_snippet)

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                logger.warning("Found match but context differs significantly")

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.INSERT,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
                new_content=new_content,
                position=position,
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            insert_point = match_result.start_line - 1
            if position == "after":
                insert_point = match_result.end_line
            lines.insert(insert_point, new_content)
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_action(
                f"Added insert change for lines {match_result.start_line}-{match_result.end_line}"
            )
            logger.debug(
                f"Queued insert change in {path} "
                f"(lines {match_result.start_line}-{match_result.end_line}, "
                f"match_type={match_result.match_type})"
            )

            return (
                f"Successfully queued insertion:\n"
                f"- File: {path}\n"
                f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                f"- Match type: {match_result.match_type}\n"
                f"Use verify_changes() to review and apply_changes() to apply"
            )

        except Exception as e:
            logger.error(f"Error inserting code into {path}: {str(e)}")
            return f"Error inserting code: {str(e)}"

    @kernel_function(description="Search for code snippets in a file.")
    def search_code(
        self,
        path: str,
        query: str,
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Search for code snippets in a file.

        Args:
            path (str): Path to the file to search
            query (str): The search query
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Result of the search
        """
        try:
            print_action(f"Searching for code snippets in {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(query)

            # Find the matching snippets
            match_results = []
            for i in range(
                len(file_content.splitlines()) - len(target.content.splitlines()) + 1
            ):
                # Extract the candidate snippet
                candidate_lines = file_content.splitlines()[
                    i : i + len(target.content.splitlines())
                ]
                candidate_content = "\n".join(candidate_lines)

                # Create a CodeSnippet for comparison
                candidate = CodeSnippet(
                    content=candidate_content,
                    start_line=i + 1,  # Convert to 1-based
                    end_line=i + len(target.content.splitlines()),
                    context_before=file_content.splitlines()[
                        max(0, i - context_lines) : i
                    ],
                    context_after=file_content.splitlines()[
                        i
                        + len(target.content.splitlines()) : i
                        + len(target.content.splitlines())
                        + context_lines
                    ],
                )

                # Try exact match first
                if candidate.matches(target, fuzzy=False):
                    logger.debug(
                        f"Found exact match at lines {i+1}-{i+len(target.content.splitlines())}"
                    )
                    match_results.append(
                        MatchResult(
                            matched=True,
                            start_line=i + 1,
                            end_line=i + len(target.content.splitlines()),
                            match_type="exact",
                            context_matches=self._verify_context(
                                target, candidate, context_lines
                            ),
                        )
                    )

                # Try fuzzy match if exact match fails and fuzzy is enabled
                elif match_type == "fuzzy" and candidate.matches(target, fuzzy=True):
                    logger.debug(
                        f"Found fuzzy match at lines {i+1}-{i+len(target.content.splitlines())}"
                    )
                    match_results.append(
                        MatchResult(
                            matched=True,
                            start_line=i + 1,
                            end_line=i + len(target.content.splitlines()),
                            match_type="fuzzy",
                            context_matches=self._verify_context(
                                target, candidate, context_lines
                            ),
                        )
                    )

            if not match_results:
                return "No matching snippets found"

            result = "\n".join(
                f"{result.start_line}-{result.end_line}: {result.match_type} match"
                for result in match_results
            )
            return result

        except Exception as e:
            logger.error(f"Error searching for code in {path}: {str(e)}")
            return f"Error searching for code: {str(e)}"

    @kernel_function(description="Verify changes before applying them.")
    def verify_changes(self) -> str:
        """
        Verify changes before applying them.

        Returns:
            str: Result of the verification
        """
        try:
            print_action("Verifying changes before applying them")

            # Verify each change
            verification_results = []
            for file_path, changes in self._pending_changes.items():
                for change in changes:
                    verification_results.append(
                        f"Verifying change in {file_path}: {change.change_type} - {change.target_snippet.content}"
                    )
                    match_result = self._find_snippet_match(
                        self.read_file(file_path),
                        change.target_snippet,
                        fuzzy=(change.change_type == ChangeType.UPDATE),
                        context_lines=2,
                    )
                    verification_results.append(
                        f"Verification result: {match_result.matched} - {match_result.error_message}"
                    )

            if all(result.matched for result in verification_results):
                return "All changes verified successfully"
            else:
                return "Some changes failed verification"

        except Exception as e:
            logger.error("Error verifying changes: {str(e)}")
            return f"Error verifying changes: {str(e)}"

    def _matches(
        self, target: CodeSnippet, candidate: CodeSnippet, fuzzy: bool = False
    ) -> bool:
        """
        Check if two snippets match.

        Args:
            target: The snippet we're looking for
            candidate: The snippet we're checking
            fuzzy: Whether to use fuzzy matching

        Returns:
            bool: True if the snippets match
        """
        if not fuzzy:
            return target.content == candidate.content

        # For fuzzy matching, normalize both contents
        target_lines = target.content.splitlines()
        candidate_lines = candidate.content.splitlines()

        if len(target_lines) != len(candidate_lines):
            return False

        # Compare each line, ignoring whitespace differences
        for target_line, candidate_line in zip(target_lines, candidate_lines):
            target_norm = "".join(target_line.split())
            candidate_norm = "".join(candidate_line.split())
            if target_norm != candidate_norm:
                return False

        return True

    @kernel_function(description="Apply pending changes to files.")
    def apply_changes(self) -> str:
        """
        Apply pending changes to files.

        Returns:
            str: Result of the application
        """
        try:
            print_action("Applying changes to files")

            # Group changes by file for atomic application
            results = []
            for file_path, changes in self._pending_changes.items():
                try:
                    # Stage the file in our Git repo
                    temp_path = self.git_editor._stage_file_for_edit(file_path)

                    # Read current content
                    with open(temp_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Apply each change in sequence
                    for change in changes:
                        lines = content.splitlines()

                        if change.change_type == ChangeType.UPDATE:
                            start_idx = change.target_snippet.start_line - 1
                            end_idx = change.target_snippet.end_line
                            lines[start_idx:end_idx] = change.new_content.splitlines()
                        elif change.change_type == ChangeType.DELETE:
                            start_idx = change.target_snippet.start_line - 1
                            end_idx = change.target_snippet.end_line
                            del lines[start_idx:end_idx]
                        elif change.change_type == ChangeType.INSERT:
                            insert_point = change.target_snippet.start_line - 1
                            if change.position == "after":
                                insert_point = change.target_snippet.end_line
                            lines.insert(insert_point, change.new_content)

                        content = "\n".join(lines)
                        if content and not content.endswith("\n"):
                            content += "\n"

                    # Write updated content
                    with open(temp_path, "w", encoding="utf-8") as f:
                        f.write(content)

                    # Apply changes using Git
                    self.git_editor.apply_changes(file_path)

                    results.append(f"Successfully applied changes to {file_path}")

                except Exception as e:
                    results.append(
                        f"Error applying changes to {file_path}, "
                        f"Git-based application failed: {str(e)}"
                    )

            # Clear pending changes
            self._pending_changes.clear()

            if not results:
                return "No changes to apply."

            return "Successfully applied changes:\n" + "\n".join(
                f"- {msg}" for msg in results
            )

        except Exception as e:
            logger.error(f"Error applying changes: {str(e)}")
            return f"Error applying changes: {str(e)}"

    @kernel_function(description="Search for code across multiple files.")
    def search_across_files(
        self, query: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """
        Search for code across multiple files.

        Args:
            query: Text to search for
            file_pattern: Glob pattern for files to search (e.g. "*.py")
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            str: Search results with file paths and line numbers
        """
        try:
            print_action(f"Searching for code across files matching '{file_pattern}'")

            # Find all matching files
            matches = []
            for file_path in self.workspace_root.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                try:
                    content = file_path.read_text()
                    rel_path = file_path.relative_to(self.workspace_root)

                    # Perform search
                    for i, line in enumerate(content.splitlines(), 1):
                        if (
                            (query in line)
                            if case_sensitive
                            else (query.lower() in line.lower())
                        ):
                            matches.append(f"{rel_path}:{i}: {line.strip()}")
                except Exception as e:
                    self.logger.warning(f"Error reading {file_path}: {str(e)}")
                    continue

            if not matches:
                return "No matching code found."

            return "\n".join(matches)

        except Exception as e:
            return f"Error searching files: {str(e)}"

    @kernel_function(description="Find references to a symbol across files.")
    def find_references(
        self,
        symbol: str,
        file_pattern: str = "*.py",
        context_lines: int = 2,
        max_results: int = 50,
    ) -> str:
        """
        Find references to a symbol (function, variable, etc.) across files.

        Args:
            symbol (str): The symbol to find references for
            file_pattern (str): Glob pattern for files to search
            context_lines (int): Number of context lines to include
            max_results (int): Maximum number of results to return

        Returns:
            str: Formatted reference results
        """
        try:
            print_action(f"Finding references to '{symbol}'")

            # Build a regex pattern that matches common symbol usage patterns
            patterns = [
                rf"\b{re.escape(symbol)}\b",  # Word boundary matches
                rf"['\"]({re.escape(symbol)})['\"]",  # String literal matches
                rf"\.{re.escape(symbol)}\b",  # Method/attribute access
                rf"\b{re.escape(symbol)}\s*\(",  # Function calls
                rf"\b{re.escape(symbol)}\s*=",  # Assignments
            ]
            combined_pattern = "|".join(patterns)

            # Find all matching files
            matching_files = list(self.workspace_root.rglob(file_pattern))
            if not matching_files:
                return f"No files found matching pattern: {file_pattern}"

            # Search each file
            results = []
            for file_path in matching_files:
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # Find matches in this file
                    for i, line in enumerate(lines):
                        if re.search(combined_pattern, line):
                            # Get context lines
                            start_idx = max(0, i - context_lines)
                            end_idx = min(len(lines), i + context_lines + 1)

                            context = "\n".join(
                                f"{j+1}: {lines[j].rstrip()}"
                                for j in range(start_idx, end_idx)
                            )

                            results.append(
                                {
                                    "file": str(
                                        file_path.relative_to(self.workspace_root)
                                    ),
                                    "line": i + 1,
                                    "content": line.strip(),
                                    "context": context,
                                }
                            )

                            if len(results) >= max_results:
                                break

                except Exception as e:
                    self.logger.warning(f"Error searching file {file_path}: {str(e)}")
                    continue

            if not results:
                return f"No references found for '{symbol}'."

            # Format results
            output = []
            for result in results:
                output.extend(
                    [
                        f"\nFile: {result['file']}",
                        f"Line {result['line']}:",
                        result["context"],
                        "-" * 60,
                    ]
                )

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error finding references: {str(e)}")
            return f"Error finding references: {str(e)}"

    @kernel_function(
        description="Run a shell command with advanced process management."
    )
    def run_terminal_command(
        self,
        command: str,
        cwd: str = "",
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = True,
        stream_output: bool = False,
    ) -> str:
        """
        Execute a shell command with advanced process management.

        Args:
            command (str): The command to execute
            cwd (str, optional): Working directory for the command
            timeout (int, optional): Timeout in seconds
            env (Dict[str, str], optional): Additional environment variables
            shell (bool): Whether to run command through shell
            stream_output (bool): Whether to stream output in real-time

        Returns:
            str: Formatted command output and status
        """
        try:
            print_action(f"Executing command: {command}")

            # Validate working directory
            work_dir = self._validate_path(cwd) if cwd else self.workspace_root
            if not work_dir.exists():
                return f"Error: Working directory '{work_dir}' does not exist"

            # Prepare environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            # Record start time
            start_time = time.time()

            try:
                # Create and start the process
                process = subprocess.Popen(
                    command,
                    cwd=work_dir,
                    env=process_env,
                    shell=shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True,
                )

                stdout_lines = []
                stderr_lines = []
                killed = False

                def read_output():
                    """Read from stdout and stderr."""
                    while True:
                        stdout_line = process.stdout.readline()
                        if stdout_line:
                            stdout_lines.append(stdout_line)
                            if stream_output:
                                print(stdout_line, end="")

                        stderr_line = process.stderr.readline()
                        if stderr_line:
                            stderr_lines.append(stderr_line)
                            if stream_output:
                                print(GRAY + stderr_line + RESET, end="")

                        if (
                            not stdout_line
                            and not stderr_line
                            and process.poll() is not None
                        ):
                            break

                # Start output reading thread
                from threading import Thread

                output_thread = Thread(target=read_output)
                output_thread.daemon = True
                output_thread.start()

                # Wait for completion or timeout
                try:
                    output_thread.join(timeout=timeout)
                    if output_thread.is_alive():
                        # Timeout occurred
                        process.kill()
                        killed = True
                        output_thread.join()

                except KeyboardInterrupt:
                    # Handle user interrupt
                    process.kill()
                    killed = True
                    output_thread.join()

                # Get final output
                stdout = "".join(stdout_lines)
                stderr = "".join(stderr_lines)

                # Calculate duration
                duration = time.time() - start_time

                # Create result object
                result = ProcessResult(
                    command=command,
                    return_code=process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    killed=killed,
                    error="Process killed (timeout)" if killed else None,
                )

                return result.format_output()

            except subprocess.SubprocessError as e:
                return ProcessResult(
                    command=command,
                    return_code=-1,
                    stdout="",
                    stderr="",
                    duration=time.time() - start_time,
                    error=f"Subprocess error: {str(e)}",
                ).format_output()

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return f"Error executing command: {str(e)}"

    @kernel_function(description="Revert changes made to files.")
    def revert_changes(self, path: str, num_changes: int = 1) -> str:
        """
        Revert changes made to files.

        Args:
            path (str): Path to the file to revert changes for
            num_changes (int): Number of changes to revert (default: 1)

        Returns:
            str: Result of the revert operation
        """
        try:
            print_action(f"Reverting changes for {path}")

            # Use Git to revert changes
            self.git_editor.revert_changes(path, num_changes)

            return f"Successfully reverted {num_changes} change(s) to {path}"

        except Exception as e:
            logger.error(f"Error reverting changes: {str(e)}")
            return f"Error reverting changes: {str(e)}"

    @kernel_function(description="Get the history of changes made.")
    def get_change_history(self, path: str) -> str:
        """
        Get the history of changes made to a file.

        Args:
            path (str): Path to get history for

        Returns:
            str: Git log with patches
        """
        try:
            return self.git_editor.get_change_history(path)
        except Exception as e:
            return f"Error getting change history: {str(e)}"
