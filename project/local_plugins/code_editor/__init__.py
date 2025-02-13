"""
Generic CodeEditor plugin.

This plugin provides comprehensive code manipulation and analysis capabilities for a wide variety
of code bases. All operations are workspace-aware to prevent accidental edits outside the workspace.
"""

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

try:
    from semantic_kernel.functions.kernel_function_decorator import kernel_function
except ImportError:
    # If you're not using Semantic Kernel, remove or replace these decorators with your own
    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


class CodeEditorPlugin:
    """
    A generic code editor/manager with advanced features:
      - Intelligent code search (using ripgrep, if available)
      - Directory listing and file manipulation
      - Read, write, and delete file operations
      - Terminal command execution
      - Simple linting/formatting (for Python/JS if tools are installed)
      - Basic code analysis (imports, functions, classes)
    """

    def __init__(self, workspace: Optional[str] = None):
        """
        :param workspace: Path to the workspace root directory. Defaults to current working directory.
        """
        self.workspace_root = Path(workspace or os.getcwd()).resolve()
        self.temp_dir = self.workspace_root / ".tmp"
        self.temp_dir.mkdir(exist_ok=True)
        self.backup_dir = self.workspace_root / ".backups"
        self.backup_dir.mkdir(exist_ok=True)

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """Resolve a path within the workspace, ensuring it does not escape the workspace."""
        try:
            full_path = (self.workspace_root / path).resolve()
            if not str(full_path).startswith(str(self.workspace_root)):
                raise ValueError(f"Path '{full_path}' is outside the workspace root.")
            return full_path
        except Exception as e:
            raise ValueError(f"Invalid path: {str(e)}")

    def _backup_file(self, path: Path) -> Optional[Path]:
        """Create a backup of the file before modifying, if it exists."""
        if path.exists() and path.is_file():
            backup_path = self.backup_dir / f"{path.name}.{path.stat().st_mtime}.bak"
            import shutil

            shutil.copy2(path, backup_path)
            return backup_path
        return None

    @kernel_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".") -> str:
        """
        List contents of the specified directory. Defaults to current directory.
        Shows both files and directories with icons for clarity.
        """
        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            entries = list(target_path.iterdir())
            dirs = sorted(e for e in entries if e.is_dir())
            files = sorted(e for e in entries if e.is_file())

            output = [f"Contents of {str(target_path)}:"]
            output.append("\nDirectories:")
            for d in dirs:
                output.append(f"  📁 {d.name}/")

            output.append("\nFiles:")
            for f in files:
                output.append(f"  📄 {f.name}")

            return "\n".join(output)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    @kernel_function(description="Search for a pattern in the codebase using ripgrep.")
    def codebase_search(self, query: str, target_dirs: str = "") -> str:
        """
        Search the codebase using ripgrep for the provided query.
        If target_dirs is provided (comma-separated), only those directories are searched.
        """
        try:
            cmd = ["rg", "--smart-case", "--context", "2"]
            if target_dirs.strip():
                # Add specified directories
                dirs = [
                    self._validate_path(d.strip()).as_posix()
                    for d in target_dirs.split(",")
                ]
                cmd.extend(dirs)
            else:
                cmd.append(self.workspace_root.as_posix())
            cmd.append(query)

            result = subprocess.run(cmd, capture_output=True, text=True)
            # Return codes: 0 => matches, 1 => no matches, >1 => error
            if result.returncode not in (0, 1):
                return f"Error searching codebase: {result.stderr.strip()}"

            return result.stdout.strip() if result.stdout else "No matches found."
        except FileNotFoundError:
            return "Error: 'rg' (ripgrep) is not installed or not found in PATH."
        except Exception as e:
            return f"Error searching codebase: {str(e)}"

    @kernel_function(description="Read the contents of a file.")
    def read_file(
        self, path: str, start_line: int = 1, end_line: Optional[int] = None
    ) -> str:
        """
        Read the contents of a file. Optionally specify a 1-based line range to read.
        If end_line is None, read until the end of the file.
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                lines = f.readlines()

            if end_line is None or end_line < 1:
                end_line = len(lines)

            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            return "".join(lines[start_idx:end_idx])
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @kernel_function(
        description="Write content to a file (overwriting existing content)."
    )
    def write_file(self, path: str, content: str) -> str:
        """
        Overwrite a file with the given content.
        Creates directories if necessary.
        """
        try:
            file_path = self._validate_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            self._backup_file(file_path)
            with open(file_path, "w") as f:
                f.write(content)
            return f"Successfully wrote to file: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @kernel_function(description="Delete a file or directory.")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """
        Delete a file. If the target is a directory, `recursive=True` must be set
        to delete the directory and all its contents.
        """
        import shutil

        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            if target_path.is_file():
                target_path.unlink()
                return f"Successfully deleted file: {path}"
            elif target_path.is_dir():
                if not recursive:
                    return f"Error: '{path}' is a directory. Use recursive=True to delete directories."
                shutil.rmtree(target_path)
                return f"Successfully deleted directory: {path}"
            else:
                return f"Error: '{path}' is neither a regular file nor a directory."
        except Exception as e:
            return f"Error deleting file or directory: {str(e)}"

    @kernel_function(description="Run a shell command in the workspace.")
    def run_terminal_command(self, command: str, cwd: str = "") -> str:
        """
        Run a shell command in the workspace, optionally specifying a subdirectory as `cwd`.
        Returns the combined stdout/stderr, along with exit codes if non-zero.
        """
        try:
            work_dir = self._validate_path(cwd) if cwd else self.workspace_root
            result = subprocess.run(
                command, shell=True, cwd=work_dir, capture_output=True, text=True
            )

            output_parts = []
            if result.stdout:
                output_parts.append("Output:")
                output_parts.append(result.stdout.strip())
            if result.stderr:
                output_parts.append("Errors:")
                output_parts.append(result.stderr.strip())
            if result.returncode != 0:
                output_parts.append(
                    f"Command failed with exit code: {result.returncode}"
                )

            combined_output = "\n".join(output_parts).strip()
            return (
                combined_output
                if combined_output
                else "Command completed successfully with no output."
            )
        except Exception as e:
            return f"Error executing command: {str(e)}"

    @kernel_function(description="Search for a regex pattern in files (like grep).")
    def grep_search(
        self, pattern: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """
        Search for a regex pattern in all files matching `file_pattern`.
        Returns context around each match if ripgrep is available, falling back to standard grep if necessary.
        """
        try:
            # Try ripgrep first
            cmd = ["rg", "--with-filename", "--line-number"]
            if not case_sensitive:
                cmd.append("--ignore-case")
            cmd.extend(["--glob", file_pattern, "--context", "2", pattern])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode not in (0, 1):
                # If ripgrep fails or isn't installed, try standard grep
                if "not found" in result.stderr.lower():
                    return self._grep_fallback(pattern, file_pattern, case_sensitive)
                return f"Error during search: {result.stderr.strip()}"

            return result.stdout.strip() if result.stdout else "No matches found."
        except FileNotFoundError:
            # If rg is not installed, fallback
            return self._grep_fallback(pattern, file_pattern, case_sensitive)
        except Exception as e:
            return f"Error during search: {str(e)}"

    def _grep_fallback(
        self, pattern: str, file_pattern: str, case_sensitive: bool
    ) -> str:
        """
        Fallback to standard grep if ripgrep isn't available.
        """
        cmd = ["grep", "-rn"]
        if not case_sensitive:
            cmd.append("-i")
        cmd.append(pattern)
        cmd.append(self.workspace_root.as_posix())

        # Find to filter by file pattern
        find_cmd = [
            "find",
            self.workspace_root.as_posix(),
            "-type",
            "f",
            "-name",
            file_pattern,
        ]
        try:
            find_proc = subprocess.run(find_cmd, capture_output=True, text=True)
            if find_proc.returncode != 0:
                return f"Error finding files for grep: {find_proc.stderr.strip()}"

            matching_files = find_proc.stdout.strip().split("\n")
            if not matching_files or (
                len(matching_files) == 1 and matching_files[0] == ""
            ):
                return "No matching files found."

            results = []
            for f in matching_files:
                grep_proc = subprocess.run(cmd + [f], capture_output=True, text=True)
                # 0 => match, 1 => no match, >1 => error
                if grep_proc.returncode not in (0, 1):
                    continue
                if grep_proc.stdout:
                    results.append(grep_proc.stdout.strip())

            return "\n".join(results) if results else "No matches found."
        except Exception as e:
            return f"Error during grep fallback: {str(e)}"

    @kernel_function(description="Search for files by name.")
    def file_search(self, pattern: str) -> str:
        """
        Find files by name pattern (shell glob). Example: '*.py' or 'myfile*.txt'.
        """
        try:
            # Use the built-in 'find' command
            cmd = [
                "find",
                self.workspace_root.as_posix(),
                "-type",
                "f",
                "-name",
                pattern,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return f"Error searching files: {result.stderr.strip()}"

            files = [f for f in result.stdout.strip().split("\n") if f]
            if not files:
                return "No matching files found."

            output = ["Matching files:"]
            for f in files:
                # Make path relative to workspace
                rel_path = str(Path(f).relative_to(self.workspace_root))
                output.append(f"  📄 {rel_path}")

            return "\n".join(output)
        except Exception as e:
            return f"Error searching files: {str(e)}"

    # -------------------------------------------------------------------------
    # Editing Helpers
    # -------------------------------------------------------------------------
    def _find_line_numbers(
        self, content: str, pattern: str, context_lines: int = 0
    ) -> Dict[str, Any]:
        """
        Find line numbers matching a regex pattern with optional context.
        Returns a dict with a 'matches' list and 'total' count.
        """
        matches = []
        lines = content.splitlines()

        # Attempt multiline match
        try:
            for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
                matched_text = match.group(0)
                start_pos = match.start()
                end_pos = match.end()

                # Convert character offsets to line numbers
                start_line = content.count("\n", 0, start_pos) + 1
                end_line = start_line + matched_text.count("\n")
                if not matched_text.endswith("\n"):
                    end_line += 1

                context_snippet = lines[
                    max(0, start_line - 1) : min(
                        len(lines), end_line + context_lines - 1
                    )
                ]
                matches.append(
                    {
                        "match_line": start_line,
                        "start_line": start_line,
                        "end_line": end_line,
                        "match": matched_text,
                        "context": context_snippet,
                    }
                )
        except re.error:
            # Fallback to line-by-line search if the pattern is invalid in multiline context
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    start = max(0, i - context_lines - 1)
                    end = min(len(lines), i + context_lines)
                    matches.append(
                        {
                            "match_line": i,
                            "start_line": i,
                            "end_line": i + 1,
                            "match": line,
                            "context": lines[start:end],
                        }
                    )

        return {"matches": matches, "total": len(matches)}

    def _modify_lines(
        self,
        content: str,
        start_line: int,
        end_line: int,
        new_content: Optional[str] = None,
    ) -> str:
        """
        Modify lines in a given content, either replacing them with `new_content` or removing them.
        Returns the updated content string.
        """
        lines = content.splitlines(keepends=True)
        start_idx = start_line - 1
        end_idx = end_line - 1

        if new_content is None:
            # Remove lines
            del lines[start_idx : end_idx + 1]
            # Insert a blank line as a separator (or clean up, depending on preference).
            if start_idx < len(lines):
                lines.insert(start_idx, "\n")
        else:
            new_lines = new_content.splitlines(keepends=True)
            # Ensure trailing newline
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            lines[start_idx : end_idx + 1] = new_lines

        return "".join(lines)

    @kernel_function(description="Edit a file's contents with various modes.")
    def edit_file(self, path: str, content: str = "", mode: str = "smart") -> str:
        """
        Edit a file's contents. Supported modes:
          - smart: Insert content in an intelligent location (fallback: append to end).
          - append: Add content to the end of the file.
          - prepend: Add content to the beginning of the file.
          - replace: Replace the entire file content with the new content.
          - insert:<line_num>: Insert content at the specified 1-based line number.
          - replace:<line_num>: Replace a single line.
          - replace:<start>-<end>: Replace a range of lines, inclusive.
          - pattern: Use `content` as `pattern|||replacement` for regex-based replacement.
          - find_replace:<pattern>[:remove]: Find lines matching <pattern> and replace or remove them.
        """
        try:
            file_path = self._validate_path(path)
            # Create directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Backup before modification
            self._backup_file(file_path)

            # Read existing content if the file exists
            existing_content = ""
            if file_path.exists():
                with open(file_path, "r") as f:
                    existing_content = f.read()

            new_content = existing_content

            # Handle modes:
            if mode.startswith("find_replace:"):
                # Format: find_replace:<pattern>[:remove]
                parts = mode.split(":")
                if len(parts) < 2:
                    return "Invalid find_replace format. Use find_replace:pattern[:remove]."
                pattern = parts[1]
                remove_only = len(parts) > 2 and parts[2] == "remove"

                # If you want to ensure pattern matches an entire line, you can do:
                # pattern = f'^{pattern}.*$'
                matches = self._find_line_numbers(existing_content, pattern)
                if not matches["matches"]:
                    return f"No lines found matching pattern: {pattern}"

                for m in reversed(matches["matches"]):
                    if remove_only:
                        new_content = self._modify_lines(
                            new_content, m["start_line"], m["end_line"], None
                        )
                    else:
                        new_content = self._modify_lines(
                            new_content, m["start_line"], m["end_line"], content
                        )

            elif mode == "pattern":
                # Format content as "regex_pattern|||replacement"
                try:
                    pattern, replacement = content.split("|||", 1)
                    new_content = re.sub(
                        pattern,
                        replacement,
                        existing_content,
                        flags=re.MULTILINE | re.DOTALL,
                    )
                except ValueError:
                    return "Invalid pattern mode format. Use 'pattern|||replacement'."

            elif mode == "replace":
                new_content = content

            elif mode == "append":
                if not new_content.endswith("\n") and new_content:
                    new_content += "\n"
                new_content += content

            elif mode == "prepend":
                insertion = content
                if insertion and not insertion.endswith("\n"):
                    insertion += "\n"
                new_content = insertion + new_content

            elif mode.startswith("insert:"):
                # insert:<line_num>
                try:
                    _, line_str = mode.split(":")
                    line_num = int(line_str)
                    lines = existing_content.splitlines()
                    if line_num < 1:
                        line_num = 1
                    if line_num > len(lines) + 1:
                        line_num = len(lines) + 1

                    lines.insert(line_num - 1, content)
                    new_content = "\n".join(lines)
                    # If original content ended with a newline, maintain it
                    if existing_content.endswith("\n"):
                        new_content += "\n"
                except Exception as e:
                    return f"Invalid insert line number: {str(e)}"

            elif mode.startswith("replace:"):
                # replace:<line_num> or replace:<start>-<end>
                try:
                    _, spec = mode.split(":")
                    lines = existing_content.splitlines()

                    if "-" in spec:
                        start_str, end_str = spec.split("-")
                        start, end = int(start_str), int(end_str)
                        start = max(1, start)
                        end = min(len(lines), end)
                        new_lines = content.splitlines()
                        lines[start - 1 : end] = new_lines
                    else:
                        line_num = int(spec)
                        if line_num < 1:
                            line_num = 1
                        if line_num > len(lines):
                            line_num = len(lines)
                        lines[line_num - 1] = content

                    new_content = "\n".join(lines)
                    if existing_content.endswith("\n"):
                        new_content += "\n"
                except Exception as e:
                    return f"Error in replace mode: {str(e)}"

            elif mode == "smart":
                # Simple heuristic: look for best match line, insert after it
                try:
                    if not existing_content.strip():
                        # If empty file, just write content
                        new_content = content
                    else:
                        lines = existing_content.splitlines()
                        content_lines = content.splitlines()
                        best_match_index = -1
                        best_score = 0

                        for i, line in enumerate(lines):
                            score = 0
                            # Very naive similarity scoring
                            for new_line in content_lines:
                                common = set(line.split()) & set(new_line.split())
                                score += len(common)
                            if score > best_score:
                                best_score = score
                                best_match_index = i

                        if best_match_index >= 0:
                            lines.insert(best_match_index + 1, content)
                            new_content = "\n".join(lines)
                            if existing_content.endswith("\n"):
                                new_content += "\n"
                        else:
                            # fallback to append
                            if not new_content.endswith("\n") and new_content:
                                new_content += "\n"
                            new_content += content
                except Exception as e:
                    return f"Error in smart edit mode: {str(e)}"

            else:
                return f"Invalid mode: {mode}"

            # Write changes
            with open(file_path, "w") as f:
                f.write(new_content)

            return f"Successfully edited file: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(
        description="Analyze a Python file for imports, functions, and classes."
    )
    def analyze_code(self, path: str) -> str:
        """
        Basic analysis of Python code structure:
        - Extracts imports
        - Extracts function definitions
        - Extracts class definitions
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                content = f.read()

            analysis = {
                "imports": [],
                "functions": [],
                "classes": [],
            }

            # Regex patterns for Python
            import_pattern = r"^(?:from\s+[\w.]+\s+)?import\s+[\w.]+(?:\s+as\s+\w+)?"
            func_pattern = r"def\s+(\w+)\s*\([^)]*\):"
            class_pattern = r"class\s+(\w+)(?:\([^)]*\))?:"

            analysis["imports"] = re.findall(import_pattern, content, re.MULTILINE)
            analysis["functions"] = re.findall(func_pattern, content)
            analysis["classes"] = re.findall(class_pattern, content)

            output = ["Code Analysis:"]
            output.append("\nImports:")
            for imp in analysis["imports"]:
                output.append(f"  - {imp.strip()}")

            output.append("\nFunctions:")
            for func in analysis["functions"]:
                output.append(f"  - {func}()")

            output.append("\nClasses:")
            for cls in analysis["classes"]:
                output.append(f"  - {cls}")

            return "\n".join(output)
        except Exception as e:
            return f"Error analyzing code: {str(e)}"

    @kernel_function(description="Format code using a suitable formatter if available.")
    def format_code(self, path: str) -> str:
        """
        Automatically format code using:
        - black for .py files
        - prettier for .js/.jsx/.ts/.tsx files
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            # Backup
            self._backup_file(file_path)

            if file_path.suffix == ".py":
                cmd = ["black", str(file_path)]
            elif file_path.suffix in [".js", ".jsx", ".ts", ".tsx"]:
                cmd = ["prettier", "--write", str(file_path)]
            else:
                return f"No formatter available for '*{file_path.suffix}' files."

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return f"Error formatting file: {result.stderr.strip()}"

            return f"Successfully formatted '{path}'."
        except FileNotFoundError as fnf:
            return f"Formatter not found: {str(fnf)}"
        except Exception as e:
            return f"Error formatting code: {str(e)}"

    @kernel_function(description="Check code for common issues using a linter.")
    def lint_code(self, path: str) -> str:
        """
        Run a linter on the file if one is available for the file type:
          - flake8 for .py
          - eslint for .js/.jsx
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            if file_path.suffix == ".py":
                cmd = ["flake8", str(file_path)]
            elif file_path.suffix in [".js", ".jsx"]:
                cmd = ["eslint", str(file_path)]
            else:
                return f"No linter available for '*{file_path.suffix}' files."

            result = subprocess.run(cmd, capture_output=True, text=True)
            # If there's output, it indicates warnings/errors; otherwise it's clean
            return (
                result.stdout.strip() if result.stdout else "No linting issues found."
            )
        except FileNotFoundError:
            return "Linter not found. Ensure flake8/eslint is installed."
        except Exception as e:
            return f"Error linting code: {str(e)}"
