"""
Refactored CodeEditor Plugin (No HCL-specific or on-disk backups).

Features:
  - File reading, listing, and searching
  - Line-based editing (append, replace lines, etc.)
  - Regex-driven editing for partial text manipulations
  - Simple linting/formatting for Python and JS-based files
  - No special block editing or backup logic

All paths are validated to stay within the configured workspace.
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

    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


class CodeEditorPlugin:
    """
    A simplified, file-type-agnostic code editor plugin supporting:
      - Basic file/directory operations
      - Line-based editing (insert, replace, append, etc.)
      - Regex-based editing for partial text matches
      - Linting and formatting (if tools are installed)
    """

    PLUGIN_INSTRUCTIONS = r"""
    CodeEditor Plugin Usage (Refactored):

    1. READING & SEARCHING
       - `read_file(path)` to view file contents (optionally a line range).
       - `grep_search(pattern, file_pattern="*.py")` or `codebase_search(query)` to find references.

    2. LINE-BASED EDITS
       - Use `edit_file(path, content, mode="...")` for direct line manipulation:
         * "replace": overwrite the entire file with `content`.
         * "append"/"prepend": add lines to end/start.
         * "insert:<line>": insert `content` at that 1-based line number.
         * "replace:<line>` or `replace:<start>-<end>`: replace those lines with `content`.
         * "smart": attempt to place `content` after a line with the most overlapping words (fallback=append).
       - `remove_lines(path, start_line, num_lines=1)`: remove lines by explicit count.

    3. REGEX/PATTERN-BASED EDITS
       - Use `pattern_edit(path, pattern, new_content="", mode="replace")`
         * `mode="remove"`: delete matched text
         * `mode="replace"`: replace matched text
         * `mode="before"/"after"`: insert `new_content` around matched text
       - This is ideal when you only want to modify specific text rather than entire lines.

    4. VERIFY CHANGES
       - Re-run `read_file(path)` after any edit to confirm success.
       - Note that line numbers *can change* after each edit, so always re-check before subsequent line-based edits.

    5. OTHER UTILITIES
       - `delete_file(path, recursive=False)` for removing files/directories.
       - `lint_code(path)` or `format_code(path)` to check/format code.
       - `run_terminal_command(command)` to execute shell tasks.
       - `get_instructions()` returns these guidelines.

    Remember: There's NO automatic backup or restore included now. If you need versioning, you must implement it yourself.
    """

    def __init__(self, workspace: Optional[str] = None):
        """
        :param workspace: Path to the workspace root directory. Defaults to the current working directory.
        """
        self.workspace_root = Path(workspace or os.getcwd()).resolve()

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

    def _find_line_numbers(
        self, content: str, pattern: str, context_lines: int = 0
    ) -> Dict[str, Any]:
        """
        Finds line numbers matching a regex pattern, returning a dict with 'matches' and 'total'.
        Optionally includes context lines around each match.
        """
        matches = []
        lines = content.splitlines()
        try:
            for match_obj in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
                matched_text = match_obj.group(0)
                start_index = match_obj.start()
                prefix = content[:start_index]
                start_line = prefix.count("\n") + 1
                matched_lines = matched_text.count("\n")
                end_line = start_line + matched_lines

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
        If 'new_content' is None, those lines are removed entirely.
        """
        lines = content.splitlines(keepends=True)
        start_idx = start_line - 1
        end_idx = end_line - 1

        if new_content is None:
            del lines[start_idx : end_idx + 1]
        else:
            replacement_lines = new_content.splitlines(keepends=True)
            if replacement_lines and not replacement_lines[-1].endswith("\n"):
                replacement_lines[-1] += "\n"
            lines[start_idx : end_idx + 1] = replacement_lines

        return "".join(lines)

    # -------------------------------------------------------------------------
    # File/Directory Operations
    # -------------------------------------------------------------------------
    @kernel_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".") -> str:
        """
        List contents of the specified directory (files and subdirectories).
        """
        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            entries = sorted(target_path.iterdir(), key=lambda e: e.name)
            dirs = [e for e in entries if e.is_dir()]
            files = [e for e in entries if e.is_file()]

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
            return "Error: 'rg' (ripgrep) not installed or not found in PATH."
        except Exception as e:
            return f"Error searching codebase: {str(e)}"

    @kernel_function(description="Read the contents of a file.")
    def read_file(
        self, path: str, start_line: int = 1, end_line: Optional[int] = None
    ) -> str:
        """
        Read the contents of 'path'. Optionally read lines [start_line, end_line] (1-based).
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

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
            with open(file_path, "w") as f:
                f.write(content)

            return f"Successfully wrote to file: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @kernel_function(description="Delete a file or directory.")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """
        Delete 'path'. If 'path' is a directory, 'recursive=True' must be set to remove it fully.
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
        Execute a shell command in the workspace, optionally under subdirectory 'cwd'.
        Returns combined stdout/stderr plus exit code message.
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

            combined = "\n".join(output_parts).strip()
            return combined if combined else "Command completed with no output."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    # -------------------------------------------------------------------------
    # Searching & Editing
    # -------------------------------------------------------------------------
    @kernel_function(description="Search for a regex pattern in files (like grep).")
    def grep_search(
        self, pattern: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """
        Search for 'pattern' in all files matching 'file_pattern', with optional case sensitivity.
        Tries ripgrep first, then falls back to standard grep.
        """
        try:
            cmd = ["rg", "--with-filename", "--line-number"]
            if not case_sensitive:
                cmd.append("--ignore-case")
            cmd.extend(["--glob", file_pattern, "--context", "2", pattern])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode not in (0, 1):
                # fallback
                if "not found" in result.stderr.lower():
                    return self._grep_fallback(pattern, file_pattern, case_sensitive)
                return f"Error during search: {result.stderr.strip()}"

            return result.stdout.strip() if result.stdout else "No matches found."
        except FileNotFoundError:
            # fallback
            return self._grep_fallback(pattern, file_pattern, case_sensitive)
        except Exception as e:
            return f"Error during search: {str(e)}"

    def _grep_fallback(
        self, pattern: str, file_pattern: str, case_sensitive: bool
    ) -> str:
        """
        Fallback to standard grep if rg is not available.
        """
        cmd = ["grep", "-rn"]
        if not case_sensitive:
            cmd.append("-i")
        cmd.append(pattern)

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

            matching_files = [m for m in find_proc.stdout.strip().split("\n") if m]
            if not matching_files:
                return "No matching files found."

            results = []
            for f in matching_files:
                grep_proc = subprocess.run(cmd + [f], capture_output=True, text=True)
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
        Find files by name (shell glob). Example: '*.py' or 'myfile*.txt'.
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

    @kernel_function(description="Edit a file's contents with line-based operations.")
    def edit_file(self, path: str, content: str = "", mode: str = "smart") -> str:
        """
        Perform line-based edits on 'path' using the following modes:
          - "replace": overwrite entire file
          - "append": add 'content' at the end
          - "prepend": add 'content' at the beginning
          - "insert:<line_num>": insert 'content' at 1-based line_num
          - "replace:<line_num>": replace a single line
          - "replace:<start>-<end>": replace all lines in [start, end]
          - "smart": try to insert 'content' after the line with the highest word overlap
        """
        try:
            file_path = self._validate_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if file_path.exists():
                with open(file_path, "r") as f:
                    existing_content = f.read()
            else:
                existing_content = ""

            new_content = existing_content

            if mode == "replace":
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
                        replacement_lines = content.splitlines()
                        lines[start - 1 : end] = replacement_lines
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
                    return f"Error parsing replace mode: {str(e)}"

            elif mode == "smart":
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
                            # fallback to append
                            if new_content and not new_content.endswith("\n"):
                                new_content += "\n"
                            new_content += content

                except Exception as e:
                    return f"Error in smart edit mode: {str(e)}"

            else:
                return f"Invalid mode: '{mode}'."

            # Write final content
            with open(file_path, "w") as f:
                f.write(new_content)

            return f"Successfully edited file: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(description="Remove lines from a file by line number/count.")
    def remove_lines(self, path: str, start_line: int, num_lines: int = 1) -> str:
        """
        Remove 'num_lines' lines starting at 1-based 'start_line' in 'path'.
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
            del lines[start_idx:end_idx]

            with open(file_path, "w") as f:
                f.writelines(lines)

            removed_count = end_idx - start_idx
            return f"Successfully removed {removed_count} line(s) from {path}"
        except Exception as e:
            return f"Error removing lines: {str(e)}"

    @kernel_function(
        description="Edit file content with regex-based text manipulation."
    )
    def pattern_edit(
        self,
        path: str,
        pattern: str,
        new_content: str = "",
        mode: str = "replace",
        match_type: str = "custom",
        match_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Regex-based editing of 'path'. If 'match_type' != 'custom', provide 'match_params'
        to auto-generate the pattern. The recognized 'mode' options:

         - "remove": Delete matched text
         - "replace": Replace matched text with 'new_content'
         - "before": Insert 'new_content' before each matched section
         - "after": Insert 'new_content' after each matched section
        """
        try:
            valid_modes = ["remove", "replace", "before", "after"]
            if mode not in valid_modes:
                return f"Invalid mode: '{mode}'. Must be one of {valid_modes}."

            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            # If user wants an auto-generated pattern
            if match_type != "custom":
                match_params = match_params or {}
                pattern = self._generate_pattern(match_type, **match_params)

            with open(file_path, "r") as f:
                original_content = f.read()

            match_data = self._find_line_numbers(original_content, pattern)
            if "error" in match_data:
                return f"Error in pattern: {match_data['error']}"
            if not match_data["matches"]:
                return "No matches found."

            lines = original_content.splitlines(keepends=True)
            changes_made = 0

            # Process in reverse order so line indexing doesn't shift
            for match in reversed(match_data["matches"]):
                start_idx = match["start_line"] - 1
                end_idx = match["end_line"] - 1

                if mode == "remove":
                    del lines[start_idx : end_idx + 1]
                elif mode == "replace":
                    inserted = new_content.splitlines(keepends=True)
                    lines[start_idx : end_idx + 1] = inserted
                elif mode == "before":
                    lines[start_idx:start_idx] = new_content.splitlines(keepends=True)
                elif mode == "after":
                    lines[end_idx + 1 : end_idx + 1] = new_content.splitlines(
                        keepends=True
                    )

                changes_made += 1

            with open(file_path, "w") as f:
                f.writelines(lines)

            return (
                f"Successfully edited file: {path} ({changes_made} match(es) updated)"
            )
        except Exception as e:
            return f"Error editing file with pattern: {str(e)}"

    # -------------------------------------------------------------------------
    # Linting / Formatting / Analysis
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
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            with open(file_path, "r") as f:
                content = f.read()

            import_pattern = r"^(?:from\s+[\w.]+\s+)?import\s+[\w.]+(?:\s+as\s+\w+)?"
            func_pattern = r"def\s+(\w+)\s*\([^)]*\):"
            class_pattern = r"class\s+(\w+)(?:\([^)]*\))?:"

            imports = re.findall(import_pattern, content, re.MULTILINE)
            functions = re.findall(func_pattern, content)
            classes = re.findall(class_pattern, content)

            results = ["Code Analysis:"]
            results.append("\nImports:")
            for imp in imports:
                results.append(f"  - {imp.strip()}")
            results.append("\nFunctions:")
            for func in functions:
                results.append(f"  - {func}()")
            results.append("\nClasses:")
            for cls in classes:
                results.append(f"  - {cls}")
            return "\n".join(results)
        except Exception as e:
            return f"Error analyzing code: {str(e)}"

    @kernel_function(description="Format code using a suitable formatter if available.")
    def format_code(self, path: str) -> str:
        """
        Attempt to format a code file:
          - 'black' for Python (.py)
          - 'prettier' for .js, .jsx, .ts, .tsx
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a file."

            # Determine correct formatter
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
            return "Formatter not found. Install 'black' or 'prettier' as needed."
        except Exception as e:
            return f"Error formatting code: {str(e)}"

    @kernel_function(description="Check code for issues using a linter.")
    def lint_code(self, path: str) -> str:
        """
        Run a linter on 'path':
          - 'flake8' for Python
          - 'eslint' for JavaScript/JSX
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a file."

            if file_path.suffix == ".py":
                cmd = ["flake8", str(file_path)]
            elif file_path.suffix in [".js", ".jsx"]:
                cmd = ["eslint", str(file_path)]
            else:
                return f"No linter available for '*{file_path.suffix}' files."

            result = subprocess.run(cmd, capture_output=True, text=True)
            return (
                result.stdout.strip() if result.stdout else "No linting issues found."
            )
        except FileNotFoundError:
            return "Linter not found. Install 'flake8' or 'eslint' as appropriate."
        except Exception as e:
            return f"Error linting code: {str(e)}"

    @kernel_function(
        description="Recursively list directory contents in a structured tree format."
    )
    def tree_list(self, path: str = ".", max_depth: int = 2) -> str:
        """
        Recursively list directories and files under 'path' in a more structured tree, up to 'max_depth' levels.
        Markdown-style example:
        .
        ├── .file
        ├── .folder/
        │   └── subfolder/
        └── .file/

        :param path: Base directory to list
        :param max_depth: How many levels of subdirectories to include
        :return: A string with a structured, markdown-friendly view of the directory contents
        """
        try:
            base_path = self._validate_path(path)
            if not base_path.exists():
                return f"Error: Path '{path}' does not exist."
        except Exception as e:
            return f"Error validating path: {str(e)}"

        def _walk_tree(current_path: Path, depth: int) -> List[str]:
            """
            Inner helper for recursively gathering directory contents up to 'max_depth'.
            Returns a list of lines in markdown-like structured format.
            """
            entries = sorted(current_path.iterdir(), key=lambda e: e.name)
            lines = []

            for entry in entries:
                # Indentation: 2 spaces per depth level
                indent = "  " * (depth - 1)
                # Mark directories vs. files
                if entry.is_dir():
                    line_text = f"{indent}- **{entry.name}/** (directory)"
                else:
                    line_text = f"{indent}- **{entry.name}** (file)"

                lines.append(line_text)

                if entry.is_dir() and depth < max_depth:
                    # Recurse into subdirectory
                    sub_lines = _walk_tree(entry, depth + 1)
                    lines.extend(sub_lines)

            return lines

        # Start building the output
        if base_path.is_file():
            # If the user specified a file, just show that item
            return f"**{base_path.name}** (file)"
        else:
            # It's a directory; show its name at the top
            lines_out = [f"**{base_path.name}/** (directory)"]
            if max_depth > 0:
                sub_lines = _walk_tree(base_path, 1)
                lines_out.extend(sub_lines)

            return "\n".join(lines_out)

    # -------------------------------------------------------------------------
    # Instructions
    # -------------------------------------------------------------------------
    @kernel_function(description="Get the plugin usage instructions.")
    def get_instructions(self) -> str:
        """
        Return the plugin usage guidelines, including how to do line-based
        vs. pattern-based editing, and any recommended workflow steps.
        """
        return self.PLUGIN_INSTRUCTIONS
