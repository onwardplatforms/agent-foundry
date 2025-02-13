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
    This plugin is designed to handle a wide range of code editing and file operations within a
    controlled workspace. It focuses on the most common tasks:
      - Searching, reading, writing, and deleting files/directories
      - Editing HCL files using block-based manipulations
      - Performing pattern-based (regex) edits on arbitrary files
      - Simple code analysis, linting, and formatting
    """

    PLUGIN_INSTRUCTIONS = r"""
    CodeEditor Plugin Usage Overview

    1. READING & SEARCHING
    - Use `read_file(path)` to see the file contents (optionally specifying a line range).
    - Use `grep_search(pattern, file_pattern="*.py")` or `codebase_search(query)` to find matches or references.

    2. REVIEW & CONFIRM
    - Always examine the output of your read/search to confirm the lines, patterns, or sections you wish to change.
    - If you need a different approach, refine your pattern or search.

    3. EDITING APPROACHES
    - LINE-BASED:
        * `edit_file(path, content, mode="...")` for single or multi-line changes.
        - Examples:
            - `mode="append"` or `mode="prepend"`
            - `mode="insert:<line>"`, `mode="replace:<start>-<end>"`
            - `mode="pattern"` or `mode="find_replace:<regex>[:remove]"`
        * `remove_lines(path, start_line, num_lines=1)` for removing a specific range of lines.

    - REGEX/PATTERN-BASED:
        * `smart_edit(path, pattern, new_content="", mode="replace", match_type="custom")`
        - "remove": delete matched text
        - "replace": replace matched text with `new_content`
        - "before"/"after": insert `new_content` around matched text

    4. VERIFY & ITERATE
    - Use `read_file(path)` again to confirm the final result.
    - If a function call fails or the result is unexpected:
        * Check for typos in your pattern or line numbers.
        * Ensure you are providing all required arguments.
        * Adjust your approach (e.g., refine your regex or specify different modes).

    5. ADDITIONAL UTILITIES
    - `delete_file(path, recursive=False)` for removing files/directories.
    - `lint_code(path)` or `format_code(path)` to check and format code.
    - `run_terminal_command(command)` for shell-based tasks within the workspace.
    - `get_instructions()` returns these guidelines.

    Always confirm your changes with a read or search before moving on. Accuracy is key!
    """

    def __init__(self, workspace: Optional[str] = None):
        """
        :param workspace: Path to the workspace root directory. Defaults to the current working directory.
        """
        self.workspace_root = Path(workspace or os.getcwd()).resolve()
        self.temp_dir = self.workspace_root / ".tmp"
        self.temp_dir.mkdir(exist_ok=True)
        self.backup_dir = self.workspace_root / ".backups"
        self.backup_dir.mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------
    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Resolve a path within the workspace, ensuring it does not escape the workspace root.
        """
        try:
            full_path = (self.workspace_root / path).resolve()
            if not str(full_path).startswith(str(self.workspace_root)):
                raise ValueError(f"Path '{full_path}' is outside the workspace root.")
            return full_path
        except Exception as e:
            raise ValueError(f"Invalid path: {str(e)}")

    def _backup_file(self, path: Path) -> Optional[Path]:
        """
        Create a backup of the file before modifying, if it exists.
        """
        if path.exists() and path.is_file():
            backup_path = self.backup_dir / f"{path.name}.{path.stat().st_mtime}.bak"
            import shutil

            shutil.copy2(path, backup_path)
            return backup_path
        return None

    def _find_line_numbers(
        self, content: str, pattern: str, context_lines: int = 0
    ) -> Dict[str, Any]:
        """
        Find line numbers matching a regex pattern with optional context lines.
        Returns a dict containing 'matches' (list) and 'total' (int).
        """
        matches = []
        lines = content.splitlines()

        try:
            # Use multiline and dotall to capture block-like patterns.
            for match_obj in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
                matched_text = match_obj.group(0)
                start_index = match_obj.start()
                prefix = content[:start_index]
                start_line = prefix.count("\n") + 1
                matched_lines = matched_text.count("\n")
                end_line = start_line + matched_lines

                # Create context snippet
                context_start = max(0, start_line - context_lines - 1)
                context_end = min(len(lines), end_line + context_lines)
                context_snippet = lines[context_start:context_end]

                matches.append(
                    {
                        "match_line": start_line,
                        "start_line": start_line,
                        "end_line": end_line,
                        "match": matched_text,
                        "context": context_snippet,
                    }
                )

            return {"matches": matches, "total": len(matches)}
        except re.error as e:
            return {"matches": [], "total": 0, "error": str(e)}

    def _modify_lines(
        self,
        content: str,
        start_line: int,
        end_line: int,
        new_content: Optional[str] = None,
    ) -> str:
        """
        Replace or remove the specified line range in 'content'.
        If 'new_content' is None, the lines are removed; otherwise replaced.
        """
        lines = content.splitlines(keepends=True)
        start_idx = start_line - 1
        end_idx = end_line - 1

        if new_content is None:
            # Remove lines
            del lines[start_idx : end_idx + 1]
        else:
            new_lines = new_content.splitlines(keepends=True)
            # Ensure trailing newline if needed
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            lines[start_idx : end_idx + 1] = new_lines

        return "".join(lines)

    def _modify_block_content(
        self, block_lines: List[str], modifications: str
    ) -> List[str]:
        """
        Naive approach to modify lines in a block by matching "key =" and replacing the entire line.
        Example usage: pass 'default = 0.3' to change the line with 'default = ...'.
        """
        try:
            result = block_lines.copy()
            mod_lines = modifications.strip().splitlines()

            for mod in mod_lines:
                # e.g. "default = 0.3"
                if "=" in mod:
                    key, val = [x.strip() for x in mod.split("=", 1)]
                    for i, line in enumerate(result):
                        # If line has that key, replace entire line
                        if line.strip().startswith(key):
                            indent = len(line) - len(line.lstrip())
                            result[i] = " " * indent + f"{key} = {val}\n"
                            break

            return result
        except Exception as e:
            logger.error(f"Error modifying block content: {e}")
            return block_lines

    # -------------------------------------------------------------------------
    # File/Directory Operations
    # -------------------------------------------------------------------------
    @kernel_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".") -> str:
        """
        List contents of the specified directory. Returns directories and files with basic info.
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
        Search the entire codebase for 'query' using ripgrep, optionally limited to 'target_dirs'.
        """
        try:
            cmd = ["rg", "--smart-case", "--context", "2"]
            if target_dirs.strip():
                dirs = [
                    self._validate_path(d.strip()).as_posix()
                    for d in target_dirs.split(",")
                ]
                cmd.extend(dirs)
            else:
                cmd.append(self.workspace_root.as_posix())

            cmd.append(query)
            result = subprocess.run(cmd, capture_output=True, text=True)

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
        Read the contents of a file. Optionally specify a 1-based line range [start_line, end_line].
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
        Overwrite the entire file at 'path' with 'content'. Creates parent dirs if necessary.
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
        Delete a file at 'path'. If 'path' is a directory, 'recursive=True' is required to remove it fully.
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
                return f"Error: '{path}' is neither a file nor a directory."
        except Exception as e:
            return f"Error deleting file or directory: {str(e)}"

    @kernel_function(description="Run a shell command in the workspace.")
    def run_terminal_command(self, command: str, cwd: str = "") -> str:
        """
        Execute a shell command in the workspace, optionally under the subdirectory 'cwd'.
        Returns combined stdout/stderr and any exit code messages.
        """
        try:
            import shlex

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
                else "Command completed with no output."
            )
        except Exception as e:
            return f"Error executing command: {str(e)}"

    # -------------------------------------------------------------------------
    # Search & Editing
    # -------------------------------------------------------------------------
    @kernel_function(description="Search for a regex pattern in files (like grep).")
    def grep_search(
        self, pattern: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """
        Like 'codebase_search' but specialized for a given 'file_pattern'. Provides context around each match if possible.
        Tries ripgrep first; falls back to standard grep if ripgrep not found.
        """
        try:
            cmd = ["rg", "--with-filename", "--line-number"]
            if not case_sensitive:
                cmd.append("--ignore-case")
            cmd.extend(["--glob", file_pattern, "--context", "2", pattern])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode not in (0, 1):
                # Fallback to standard grep if needed
                if "not found" in result.stderr.lower():
                    return self._grep_fallback(pattern, file_pattern, case_sensitive)
                return f"Error during search: {result.stderr.strip()}"

            return result.stdout.strip() if result.stdout else "No matches found."
        except FileNotFoundError:
            return self._grep_fallback(pattern, file_pattern, case_sensitive)
        except Exception as e:
            return f"Error during search: {str(e)}"

    def _grep_fallback(
        self, pattern: str, file_pattern: str, case_sensitive: bool
    ) -> str:
        """
        Fallback to standard grep if ripgrep isn't available or fails ungracefully.
        """
        import shutil

        cmd = ["grep", "-rn"]
        if not case_sensitive:
            cmd.append("-i")
        cmd.append(pattern)

        # Use 'find' to locate files matching 'file_pattern'
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
            matching_files = [m for m in matching_files if m]  # filter out empty lines

            if not matching_files:
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
        Find files by name (shell glob). e.g. '*.py' or 'myfile*.txt'.
        """
        try:
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
                rel_path = str(Path(f).relative_to(self.workspace_root))
                output.append(f"  📄 {rel_path}")

            return "\n".join(output)
        except Exception as e:
            return f"Error searching files: {str(e)}"

    @kernel_function(description="Edit a file's contents with various modes.")
    def edit_file(self, path: str, content: str = "", mode: str = "smart") -> str:
        """
        Perform basic line-based edits on 'path', such as appending, prepending, or replacing lines.

        Supported modes:
          - "smart": attempt to insert 'content' after the line that shares the most words with it (fallback=append).
          - "append": add 'content' to the end of the file.
          - "prepend": add 'content' to the start of the file.
          - "replace": replace the entire file with 'content'.
          - "insert:<line_num>": insert 'content' at that 1-based line.
          - "replace:<line_num>": replace a single line at that 1-based line.
          - "replace:<start>-<end>": replace all lines in that range (inclusive).
          - "pattern": interpret 'content' as "regex_pattern|||replacement" and do a re.sub.
          - "find_replace:<pattern>[:remove]": find lines matching <pattern> and replace or remove them.
        """
        try:
            file_path = self._validate_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            self._backup_file(file_path)

            existing_content = ""
            if file_path.exists():
                with open(file_path, "r") as f:
                    existing_content = f.read()

            new_content = existing_content

            # 1) parse the mode
            if mode.startswith("find_replace:"):
                parts = mode.split(":")
                if len(parts) < 2:
                    return "Invalid find_replace usage. Example: find_replace:pattern[:remove]."
                pattern = parts[1]
                remove_only = len(parts) > 2 and parts[2] == "remove"

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
                # content => "regex_pattern|||replacement"
                try:
                    regex_pattern, replacement = content.split("|||", 1)
                    new_content = re.sub(
                        regex_pattern,
                        replacement,
                        existing_content,
                        flags=re.MULTILINE | re.DOTALL,
                    )
                except ValueError:
                    return "Invalid 'pattern' mode format. Must be 'pattern|||replacement'."

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
                    if existing_content.endswith("\n"):
                        new_content += "\n"
                except Exception as e:
                    return f"Error inserting at line {line_str}: {str(e)}"

            elif mode.startswith("replace:"):
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
                # naive approach: tries to find a "best match" line to insert after
                try:
                    if not existing_content.strip():
                        new_content = content
                    else:
                        lines = existing_content.splitlines()
                        content_lines = content.splitlines()
                        best_match_index = -1
                        best_score = 0

                        for i, line in enumerate(lines):
                            score = 0
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
                            if new_content and not new_content.endswith("\n"):
                                new_content += "\n"
                            new_content += content
                except Exception as e:
                    return f"Error in smart edit mode: {str(e)}"

            else:
                return f"Invalid mode: '{mode}'."

            # 2) Write final content
            with open(file_path, "w") as f:
                f.write(new_content)

            return f"Successfully edited file: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(description="Edit file content with regex pattern matching.")
    def smart_edit(
        self,
        path: str,
        pattern: str = "",
        new_content: str = "",
        mode: str = "replace",
        match_type: str = "custom",
        match_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Perform a regex-based or custom-pattern edit on 'path'. If 'match_type' != "custom", pass
        'match_params' (e.g. {"name": "function_name"}). The recognized 'mode' options:
          - "remove": delete the matched text
          - "replace": replace the matched text with 'new_content'
          - "before": insert 'new_content' before each matched section
          - "after": insert 'new_content' after each matched section
        """
        try:
            mode = mode.lower().strip()
            valid_modes = ["remove", "replace", "before", "after"]
            if mode not in valid_modes:
                return (
                    f"Invalid mode: '{mode}'. Must be one of: {', '.join(valid_modes)}"
                )

            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            # Generate pattern if requested
            if match_type != "custom":
                match_params = match_params or {}
                pattern = self._generate_pattern(match_type, **match_params)

            with open(file_path, "r") as f:
                content = f.read()

            matches = self._find_line_numbers(content, pattern)
            if "error" in matches:
                return f"Error in pattern: {matches['error']}"
            if not matches["matches"]:
                return "No matches found."

            self._backup_file(file_path)
            lines = content.splitlines(keepends=True)
            changes_made = 0

            for match in reversed(matches["matches"]):
                start_line = match["start_line"] - 1
                end_line = match["end_line"] - 1

                if mode == "remove":
                    del lines[start_line : end_line + 1]
                elif mode == "replace":
                    lines[start_line : end_line + 1] = new_content.splitlines(
                        keepends=True
                    )
                elif mode == "before":
                    lines[start_line:start_line] = new_content.splitlines(keepends=True)
                elif mode == "after":
                    lines[end_line + 1 : end_line + 1] = new_content.splitlines(
                        keepends=True
                    )

                changes_made += 1

            with open(file_path, "w") as f:
                f.writelines(lines)

            return f"Successfully edited file: {path} ({changes_made} match section(s) modified)"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(description="Remove lines from a file.")
    def remove_lines(self, path: str, start_line: int, num_lines: int = 1) -> str:
        """
        Remove a specific count of lines starting at 1-based 'start_line' in 'path'.
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                lines = f.readlines()

            if start_line < 1 or start_line > len(lines):
                return f"Invalid start line: {start_line}"

            start_idx = start_line - 1
            end_idx = min(start_idx + num_lines, len(lines))

            self._backup_file(file_path)
            del lines[start_idx:end_idx]

            with open(file_path, "w") as f:
                f.writelines(lines)

            removed_count = end_idx - start_idx
            return f"Successfully removed {removed_count} line(s) from {path}"
        except Exception as e:
            return f"Error removing lines: {str(e)}"

    # -------------------------------------------------------------------------
    # HCL Block Editing
    # -------------------------------------------------------------------------
    @kernel_function(description="Edit a specific block in an HCL file.")
    def block_edit(
        self,
        path: str,
        block_identifier: str,
        block_name: Optional[str] = None,
        new_content: Optional[str] = None,
        mode: str = "replace",
    ) -> str:
        """
        For HCL-like files, remove or replace an entire block such as:
          variable "foo" { ... }
          model "llama2" { ... }
          plugin "local" "echo" { ... }

        Args:
          path: File path (typically *.hcl)
          block_identifier: e.g. "variable", "model", "plugin"
          block_name: Name in quotes (e.g. "model_temperature"). If None, the first block matching 'block_identifier { ... }' is used.
          new_content: Replacement text for the block if mode="replace" or partial updates if mode="modify"
          mode: "remove", "replace", or "modify"
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                content = f.read()

            # Build regex for e.g. variable "model_temperature" { ... }
            if block_name:
                pattern = rf'{block_identifier}\s*"{block_name}"\s*{{[^}}]*}}'
            else:
                # if user didn't specify block_name, match any block with block_identifier
                pattern = rf"{block_identifier}\s*{{[^}}]*}}"

            matches = self._find_line_numbers(content, pattern)
            if not matches["matches"]:
                return (
                    f"No matching block found for block_identifier='{block_identifier}'"
                )

            self._backup_file(file_path)
            lines = content.splitlines(keepends=True)

            # For simplicity, just handle the first match
            match = matches["matches"][0]
            start_line = match["start_line"] - 1
            end_line = match["end_line"] - 1

            if mode == "remove":
                del lines[start_line : end_line + 1]

            elif mode == "replace":
                if not new_content:
                    return "No new_content provided for replace mode."
                # Keep original indentation from the first line
                original_indent = len(lines[start_line]) - len(
                    lines[start_line].lstrip()
                )
                updated_lines = []
                for line in new_content.splitlines():
                    if line.strip():
                        updated_lines.append(" " * original_indent + line + "\n")
                    else:
                        updated_lines.append(line + "\n")

                lines[start_line : end_line + 1] = updated_lines

            elif mode == "modify":
                if not new_content:
                    return "No new_content provided for modify mode."
                block_lines = lines[start_line : end_line + 1]
                modified_lines = self._modify_block_content(block_lines, new_content)
                lines[start_line : end_line + 1] = modified_lines

            else:
                return (
                    f"Invalid mode: '{mode}'. Must be one of: remove | replace | modify"
                )

            with open(file_path, "w") as f:
                f.writelines(lines)

            return f"Successfully {mode}d block '{block_name}' in {path}"
        except Exception as e:
            return f"Error editing block: {str(e)}"

    # -------------------------------------------------------------------------
    # Simple Code Analysis, Linting, Formatting
    # -------------------------------------------------------------------------
    @kernel_function(
        description="Analyze a Python file for imports, functions, and classes."
    )
    def analyze_code(self, path: str) -> str:
        """
        Basic structural analysis of Python code:
          - Import statements
          - Function definitions
          - Class definitions
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                content = f.read()

            import_pattern = r"^(?:from\s+[\w.]+\s+)?import\s+[\w.]+(?:\s+as\s+\w+)?"
            func_pattern = r"def\s+(\w+)\s*\([^)]*\):"
            class_pattern = r"class\s+(\w+)(?:\([^)]*\))?:"

            imports = re.findall(import_pattern, content, re.MULTILINE)
            functions = re.findall(func_pattern, content)
            classes = re.findall(class_pattern, content)

            result_lines = []
            result_lines.append("Code Analysis:")
            result_lines.append("\nImports:")
            for imp in imports:
                result_lines.append(f"  - {imp.strip()}")

            result_lines.append("\nFunctions:")
            for func in functions:
                result_lines.append(f"  - {func}()")

            result_lines.append("\nClasses:")
            for cls in classes:
                result_lines.append(f"  - {cls}")

            return "\n".join(result_lines)
        except Exception as e:
            return f"Error analyzing code: {str(e)}"

    @kernel_function(description="Format code using a suitable formatter if available.")
    def format_code(self, path: str) -> str:
        """
        Attempt to format a code file:
          - uses 'black' for .py
          - uses 'prettier' for .js/.jsx/.ts/.tsx
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

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
        except FileNotFoundError:
            return "Formatter not found. Ensure 'black' or 'prettier' is installed."
        except Exception as e:
            return f"Error formatting code: {str(e)}"

    @kernel_function(description="Check code for common issues using a linter.")
    def lint_code(self, path: str) -> str:
        """
        Run a linter on the file if available:
          - 'flake8' for Python
          - 'eslint' for JavaScript/JSX
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
            return "Linter not found. Please install flake8 or eslint as appropriate."
        except Exception as e:
            return f"Error linting code: {str(e)}"

    # -------------------------------------------------------------------------
    # Instructions
    # -------------------------------------------------------------------------
    @kernel_function(description="Get the plugin usage instructions.")
    def get_instructions(self) -> str:
        """
        Return the plugin's usage instructions. Agents should incorporate these guidelines
        for deciding which function to call and how to structure the call.
        """
        return self.PLUGIN_INSTRUCTIONS
