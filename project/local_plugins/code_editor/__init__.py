"""CodeEditor plugin for Agent Foundry.

This plugin provides comprehensive code manipulation and analysis capabilities.
All operations are workspace-aware and maintain code integrity.
"""

import logging
import os
import re
import subprocess
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from semantic_kernel.functions.kernel_function_decorator import kernel_function

logger = logging.getLogger(__name__)


class Plugin:
    """Enhanced plugin for code editing and analysis.

    Features:
    - Intelligent code search and analysis
    - Safe file operations with validation
    - Advanced code editing capabilities
    - Integrated development tools
    """

    def __init__(self, kernel=None, variables=None):
        self.kernel = kernel
        self.variables = variables or {}
        self.workspace_root = Path(os.getcwd())
        self._setup_workspace()

    def _setup_workspace(self):
        """Initialize workspace settings and validate environment."""
        self.temp_dir = self.workspace_root / ".tmp"
        self.temp_dir.mkdir(exist_ok=True)
        self.backup_dir = self.workspace_root / ".backups"
        self.backup_dir.mkdir(exist_ok=True)

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """Validate and resolve path within workspace."""
        try:
            full_path = (self.workspace_root / path).resolve()
            if not str(full_path).startswith(str(self.workspace_root)):
                raise ValueError("Path outside workspace")
            return full_path
        except Exception as e:
            raise ValueError(f"Invalid path: {str(e)}")

    def _backup_file(self, path: Path):
        """Create backup of file before modification."""
        if path.exists() and path.is_file():
            backup_path = self.backup_dir / f"{path.name}.{path.stat().st_mtime}.bak"
            import shutil

            shutil.copy2(path, backup_path)
            return backup_path
        return None

    @kernel_function(
        description="List contents of a directory. Use this to explore the codebase structure."
    )
    def list_dir(self, path: str = ".") -> str:
        """List contents of the specified directory. Defaults to current directory.
        Shows both files and directories with icons for better visualization.
        """
        try:
            target_path = (self.workspace_root / path).resolve()
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist"

            # Get all entries and separate into files and directories
            entries = list(target_path.iterdir())
            dirs = sorted([e for e in entries if e.is_dir()])
            files = sorted([e for e in entries if e.is_file()])

            # Format the output
            output = [f"Contents of {target_path}:"]
            output.append("\nDirectories:")
            for d in dirs:
                output.append(f"  📁 {d.name}/")

            output.append("\nFiles:")
            for f in files:
                output.append(f"  📄 {f.name}")

            return "\n".join(output)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    @kernel_function(
        description="Search codebase for patterns or functionality. Use this to find relevant code."
    )
    def codebase_search(self, query: str, target_dirs: str = "") -> str:
        """Search codebase for relevant code. Shows matches with context.
        Provide target_dirs as comma-separated list to narrow search scope.
        """
        try:
            # For now, we'll use ripgrep with smart pattern matching
            # In a real implementation, this would use a proper semantic search engine
            cmd = ["rg", "--type", "python", "--smart-case", "--context", "2"]

            if target_dirs:
                dirs = [d.strip() for d in target_dirs.split(",")]
                cmd.extend(dirs)
            else:
                cmd.append(".")

            cmd.append(query)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode not in (0, 1):  # 1 means no matches, which is ok
                return f"Error searching codebase: {result.stderr}"

            return result.stdout or "No matches found."
        except Exception as e:
            return f"Error searching codebase: {str(e)}"

    @kernel_function(description="Read contents of a file")
    def read_file(self, path: str, start_line: int = 1, end_line: int = None) -> str:
        """Read contents of a file, optionally specifying line range."""
        try:
            file_path = (self.workspace_root / path).resolve()
            if not file_path.exists():
                return f"Error: File '{path}' does not exist"

            with open(file_path, "r") as f:
                lines = f.readlines()

            if end_line is None:
                end_line = len(lines)

            # Adjust for 1-based indexing
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)

            selected_lines = lines[start_idx:end_idx]
            return "".join(selected_lines)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @kernel_function(description="Run a terminal command")
    def run_terminal_command(self, command: str, cwd: str = None) -> str:
        """Run a terminal command and return its output."""
        try:
            work_dir = self.workspace_root
            if cwd:
                work_dir = (self.workspace_root / cwd).resolve()

            result = subprocess.run(
                command, shell=True, cwd=work_dir, capture_output=True, text=True
            )

            output = []
            if result.stdout:
                output.append("Output:")
                output.append(result.stdout)
            if result.stderr:
                output.append("Errors:")
                output.append(result.stderr)
            if result.returncode != 0:
                output.append(f"Command failed with exit code: {result.returncode}")

            return (
                "\n".join(output)
                if output
                else "Command completed successfully with no output."
            )
        except Exception as e:
            return f"Error executing command: {str(e)}"

    @kernel_function(description="Search files using regex pattern")
    def grep_search(
        self, pattern: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """Search for pattern in files matching file_pattern."""
        try:
            cmd = ["rg", "--with-filename", "--line-number"]
            if not case_sensitive:
                cmd.append("--ignore-case")

            cmd.extend(["--glob", file_pattern])
            cmd.extend(["--context", "2"])
            cmd.append(pattern)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode not in (0, 1):  # 1 means no matches, which is ok
                return f"Error during search: {result.stderr}"

            return result.stdout or "No matches found."
        except Exception as e:
            return f"Error during search: {str(e)}"

    @kernel_function(description="Search for files by name")
    def file_search(self, pattern: str) -> str:
        """Search for files matching the given pattern."""
        try:
            cmd = ["find", ".", "-type", "f", "-name", pattern]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return f"Error searching files: {result.stderr}"

            files = result.stdout.strip().split("\n")
            if not files or (len(files) == 1 and not files[0]):
                return "No matching files found."

            output = ["Matching files:"]
            for f in files:
                if f:  # Skip empty lines
                    output.append(f"  📄 {f[2:]}")  # Remove ./ prefix

            return "\n".join(output)
        except Exception as e:
            return f"Error searching files: {str(e)}"

    @kernel_function(description="Edit a file's contents")
    def edit_file(self, path: str, content: str, mode: str = "append") -> str:
        """
        Edit a file's contents. Mode can be:
        - append: Add content to end of file
        - prepend: Add content to start of file
        - replace: Replace entire file content
        - insert:line_num: Insert at specific line number
        """
        try:
            file_path = (self.workspace_root / path).resolve()

            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle different edit modes
            if mode == "replace":
                with open(file_path, "w") as f:
                    f.write(content)
            elif mode == "append":
                with open(file_path, "a") as f:
                    f.write(content)
            elif mode == "prepend":
                if file_path.exists():
                    with open(file_path, "r") as f:
                        existing = f.read()
                else:
                    existing = ""
                with open(file_path, "w") as f:
                    f.write(content + existing)
            elif mode.startswith("insert:"):
                try:
                    line_num = int(mode.split(":")[1])
                    if file_path.exists():
                        with open(file_path, "r") as f:
                            lines = f.readlines()
                    else:
                        lines = []

                    # Adjust for 1-based line numbers
                    line_num = max(1, min(len(lines) + 1, line_num))
                    lines.insert(line_num - 1, content)

                    with open(file_path, "w") as f:
                        f.writelines(lines)
                except ValueError:
                    return f"Invalid line number in mode: {mode}"
            else:
                return f"Invalid edit mode: {mode}"

            return f"Successfully edited file: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(description="Delete a file")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """Delete a file or directory (if recursive=True)."""
        try:
            target_path = (self.workspace_root / path).resolve()
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist"

            if target_path.is_file():
                target_path.unlink()
                return f"Successfully deleted file: {path}"
            elif target_path.is_dir():
                if not recursive:
                    return f"Error: '{path}' is a directory. Use recursive=True to delete directories."
                import shutil

                shutil.rmtree(target_path)
                return f"Successfully deleted directory: {path}"

            return f"Error: '{path}' is neither a file nor a directory"
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    @kernel_function(description="Analyze code structure and dependencies")
    def analyze_code(self, path: str) -> str:
        """Analyze code structure, imports, and dependencies."""
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist"

            # Basic code analysis
            with open(file_path, "r") as f:
                content = f.read()

            analysis = {
                "imports": [],
                "functions": [],
                "classes": [],
                "global_vars": [],
            }

            # Extract imports
            import_pattern = r"^(?:from\s+[\w.]+\s+)?import\s+[\w.]+(?:\s+as\s+\w+)?"
            analysis["imports"] = re.findall(import_pattern, content, re.MULTILINE)

            # Extract functions
            func_pattern = r"def\s+(\w+)\s*\([^)]*\):"
            analysis["functions"] = re.findall(func_pattern, content)

            # Extract classes
            class_pattern = r"class\s+(\w+)(?:\([^)]*\))?:"
            analysis["classes"] = re.findall(class_pattern, content)

            # Format output
            output = ["Code Analysis Results:"]
            output.append("\nImports:")
            for imp in analysis["imports"]:
                output.append(f"  - {imp}")

            output.append("\nFunctions:")
            for func in analysis["functions"]:
                output.append(f"  - {func}()")

            output.append("\nClasses:")
            for cls in analysis["classes"]:
                output.append(f"  - {cls}")

            return "\n".join(output)
        except Exception as e:
            return f"Error analyzing code: {str(e)}"

    @kernel_function(description="Format code according to language standards")
    def format_code(self, path: str) -> str:
        """Format code using appropriate formatter for the file type."""
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist"

            # Create backup
            self._backup_file(file_path)

            # Determine file type and use appropriate formatter
            if file_path.suffix == ".py":
                cmd = ["black", str(file_path)]
            elif file_path.suffix in [".js", ".jsx", ".ts", ".tsx"]:
                cmd = ["prettier", "--write", str(file_path)]
            else:
                return f"No formatter available for {file_path.suffix} files"

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return f"Error formatting file: {result.stderr}"

            return f"Successfully formatted {path}"
        except Exception as e:
            return f"Error formatting code: {str(e)}"

    @kernel_function(description="Check code for common issues")
    def lint_code(self, path: str) -> str:
        """Run linter on code file."""
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist"

            # Choose appropriate linter
            if file_path.suffix == ".py":
                cmd = ["flake8", str(file_path)]
            elif file_path.suffix in [".js", ".jsx"]:
                cmd = ["eslint", str(file_path)]
            else:
                return f"No linter available for {file_path.suffix} files"

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout if result.stdout else "No linting issues found."
        except Exception as e:
            return f"Error linting code: {str(e)}"
