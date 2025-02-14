import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

try:
    from semantic_kernel.functions.kernel_function_decorator import kernel_function
except ImportError:
    # Fallback if not running inside Semantic Kernel
    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


class CodeEditorPlugin:
    """
    A fully generic code editor plugin with:
      - Directory and file operations
      - Simple, all-files text searching (ripgrep or grep+find fallback)
      - Line-based and regex-based editing
      - Shell command execution

    No language-specific logic or heuristics—purely literal text searching
    and direct file operations, suitable for a variety of code/editing tasks.
    """

    PLUGIN_INSTRUCTIONS = r"""
    Recommended Code Editing Workflow
    =================================

    1) Inspect the Project
    - Use `list_dir()` or `tree_list()` to see how files and folders are organized.
    - Use `search("<keyword>")` to locate references to important terms or functions.

    2) Read and Plan
    - Once you identify relevant files, call `read_file()` to examine specific lines or the entire file.
    - Decide if you need line-based edits or regex-based transformations.

    3) Make Edits
    - For line-based changes (inserting, replacing, removing lines), use `edit_file()`.
    - For pattern-based changes (renaming a function, removing trailing whitespace, etc.), use `pattern_edit()`.
    - If you only need to drop a block of lines, `remove_lines()` is handy.

    4) Validate Your Work
    - Re-read the updated files with `read_file()` or run a quick `search()` to confirm your changes are present.
    - Run shell commands or tests with `run_terminal_command()` if you need to verify the build, lint the code, or run tests.

    5) Conclude and Clean Up
    - If any files or directories are no longer needed, remove them with `delete_file()`.
    - Provide a final summary of changes to the user, including any next steps or discovered issues.
    """

    def __init__(self, workspace: Optional[str] = None):
        """
        Initializes the CodeEditorPlugin with a specified workspace root directory.

        Args:
            workspace (str, optional): The path to the workspace root. If omitted,
                defaults to the current working directory.
        """
        self.workspace_root = Path(workspace or os.getcwd()).resolve()
        logger.info(
            f"CodeEditorPlugin initialized with workspace root: {self.workspace_root}"
        )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------
    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Resolve and verify that 'path' is inside the workspace root.

        Args:
            path (Union[str, Path]): A file or directory path (relative or absolute).

        Returns:
            Path: The fully resolved path within the workspace.

        Raises:
            ValueError: If the resolved path is outside the workspace root.
        """
        full_path = (self.workspace_root / path).resolve()
        logger.debug(
            f"Validating path: {path} -> {full_path} (workspace root: {self.workspace_root})"
        )
        if not str(full_path).startswith(str(self.workspace_root)):
            raise ValueError(f"Path '{full_path}' is outside the workspace root.")
        return full_path

    def _parse_ripgrep_output(
        self, output: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """
        Parse the text output from a ripgrep command into a structured list.

        Args:
            output (str): The raw stdout from ripgrep.
            max_results (int): Maximum number of matches to return.

        Returns:
            List[Dict[str, Any]]: Each dict has:
                "file" (str): the file path
                "line" (int): the matching line number
                "content" (str): the matching line text
                "context_before" (List[str]): lines of context before the match
                "context_after" (List[str]): lines of context after the match
        """
        matches = []
        current_file = None
        current_match = None

        for line in output.split("\n"):
            if not line:
                continue
            if line.startswith("--"):
                # This is a context separator in ripgrep output
                continue

            # Expected format: "file_path:line_num:content"
            # or optional context lines prefixed by ">"
            if not line.startswith(">") and not line.startswith("<"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    file_path, line_num_str, content = parts
                    try:
                        line_num = int(line_num_str)
                    except ValueError:
                        line_num = -1

                    if current_file != file_path:
                        current_file = file_path
                        if len(matches) >= max_results:
                            break

                    current_match = {
                        "file": file_path,
                        "line": line_num,
                        "content": content.strip(),
                        "context_before": [],
                        "context_after": [],
                    }
                    matches.append(current_match)
            else:
                # If it's a context line, e.g. "> some text"
                if current_match is not None:
                    current_match["context_after"].append(line[1:].strip())

        return matches

    def _grep_fallback(
        self,
        pattern: str,
        file_pattern: str,
        case_sensitive: bool,
        context_lines: int,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        Fallback mechanism using 'find' + 'grep' if ripgrep is unavailable or fails.

        Steps:
            1) Use find to gather candidate files.
            2) Run grep on each file to locate matches.

        Args:
            pattern (str): The text/regex pattern to search for.
            file_pattern (str): Glob pattern for files (e.g. "*.py").
            case_sensitive (bool): Whether to make the search case-sensitive.
            context_lines (int): Number of lines of context.
            max_results (int): Maximum total matches to return.

        Returns:
            List[Dict[str, Any]]: A list of match dictionaries (same format as ripgrep parser).
        """
        # 1) Gather files via find
        find_cmd = ["find", self.workspace_root.as_posix(), "-type", "f"]
        if file_pattern and file_pattern != "*":
            find_cmd.extend(["-name", file_pattern])

        try:
            find_res = subprocess.run(find_cmd, capture_output=True, text=True)
            if find_res.returncode != 0:
                logger.warning(f"Find error: {find_res.stderr}")
                return []
            files = [f for f in find_res.stdout.split("\n") if f.strip()]
            if not files:
                return []

            # 2) Grep them
            matches = []
            grep_cmd = ["grep", "-n"]  # -n => show line number
            if not case_sensitive:
                grep_cmd.append("-i")
            if context_lines > 0:
                grep_cmd.extend(["-C", str(context_lines)])

            count = 0
            for fpath in files:
                if count >= max_results:
                    break
                cmd = grep_cmd + [pattern, fpath]
                grep_res = subprocess.run(cmd, capture_output=True, text=True)
                # grep returns 0 if matches found, 1 if none found, >1 on error
                if grep_res.returncode not in (0, 1):
                    continue

                if grep_res.stdout:
                    for line in grep_res.stdout.strip().split("\n"):
                        # Handle both "filename:lineNum:content" and "lineNum:content" formats
                        parts = line.split(":", 2)
                        if len(parts) == 3:
                            # Format: filename:lineNum:content
                            _, ln_str, content = parts
                        elif len(parts) == 2:
                            # Format: lineNum:content
                            ln_str, content = parts
                        else:
                            continue

                        try:
                            ln_val = int(ln_str)
                        except ValueError:
                            ln_val = -1

                        matches.append(
                            {
                                "file": fpath,
                                "line": ln_val,
                                "content": content.strip(),
                                "context_before": [],
                                "context_after": [],
                            }
                        )
                        count += 1
                        if count >= max_results:
                            break
            return matches
        except Exception as e:
            logger.warning(f"Grep fallback error: {e}")
            return []

    def _run_search_command(
        self,
        pattern: str,
        file_pattern: str,
        case_sensitive: bool,
        context_lines: int,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        Attempts to run a search with ripgrep. If that fails or is not installed,
        falls back to grep + find.

        Args:
            pattern (str): The text pattern to search for.
            file_pattern (str): A glob for matching files (e.g. "*.py").
            case_sensitive (bool): True if search is case-sensitive.
            context_lines (int): Number of context lines to show.
            max_results (int): Maximum matches to return.

        Returns:
            List[Dict[str, Any]]: A list of matches in a structured format.
        """
        # Build the ripgrep command
        cmd = [
            "rg",
            "--line-number",
            "--with-filename",
            "--max-count",
            str(max_results),
        ]
        if not case_sensitive:
            cmd.append("--ignore-case")
        if context_lines > 0:
            cmd.extend(["--context", str(context_lines)])
        if file_pattern and file_pattern != "*":
            cmd.extend(["--glob", file_pattern])

        cmd.append(pattern)
        cmd.append(self.workspace_root.as_posix())

        try:
            rg_result = subprocess.run(cmd, capture_output=True, text=True)
            if rg_result.returncode in (0, 1):
                # 0 => found matches, 1 => no matches
                if rg_result.stdout.strip():
                    return self._parse_ripgrep_output(rg_result.stdout, max_results)
                else:
                    return []
            else:
                # Some other error code from ripgrep
                logger.warning(f"Ripgrep error: {rg_result.stderr}")
                # fallback
                return self._grep_fallback(
                    pattern, file_pattern, case_sensitive, context_lines, max_results
                )
        except FileNotFoundError:
            # rg not installed
            return self._grep_fallback(
                pattern, file_pattern, case_sensitive, context_lines, max_results
            )

    def _format_search_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Convert structured search results into a human-friendly output string.

        Args:
            results (List[Dict[str, Any]]): The matches from a search command.

        Returns:
            str: A formatted list of matches. If empty, returns "No matches found."
        """
        if not results:
            return "No matches found."

        output = []
        current_file = None
        for match in results:
            if match["file"] != current_file:
                current_file = match["file"]
                rel_path = str(Path(current_file).relative_to(self.workspace_root))
                output.append(f"\nFile: {rel_path}")
            output.append(f"  {match['line']}: {match['content']}")
            for ctx_line in match["context_after"]:
                output.append(f"    {ctx_line}")

        return "\n".join(output).strip()

    # -------------------------------------------------------------------------
    # Public Plugin Methods
    # -------------------------------------------------------------------------
    @kernel_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".") -> str:
        """
        Lists directories and files within 'path'.

        Args:
            path (str, optional): Directory to list. Defaults to "." (workspace root).

        Returns:
            str: Formatted string showing subdirectories and files.

        Examples:
            >>> list_dir(".")
            "Contents of /full/path:\nDirectories:\n  📁 folder/\nFiles:\n  📄 file.txt"
        """
        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            entries = sorted(target_path.iterdir(), key=lambda e: e.name)
            dirs = [e for e in entries if e.is_dir()]
            files = [e for e in entries if e.is_file()]

            out = [f"Contents of {str(target_path)}:"]
            out.append("\nDirectories:")
            for d in dirs:
                out.append(f"  📁 {d.name}/")
            out.append("\nFiles:")
            for f in files:
                out.append(f"  📄 {f.name}")
            return "\n".join(out)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    @kernel_function(
        description="Recursively list directory contents in a tree format."
    )
    def tree_list(self, path: str = ".", max_depth: int = 2) -> str:
        """
        Recursively shows a tree of directories/files up to 'max_depth' levels.

        Args:
            path (str, optional): Directory to start from. Defaults to ".".
            max_depth (int, optional): How many subdirectory levels to descend. Defaults to 2.

        Returns:
            str: A text-based tree view of directories and files.

        Examples:
            >>> tree_list(".", max_depth=1)
            "myproject/ (directory)\n  - setup.py (file)\n  - src/ (directory)"
        """
        try:
            base_path = self._validate_path(path)
            if not base_path.exists():
                return f"Error: Path '{path}' does not exist."
        except Exception as e:
            return f"Error validating path: {str(e)}"

        def _walk_tree(current_path: Path, depth: int) -> List[str]:
            lines = []
            entries = sorted(current_path.iterdir(), key=lambda e: e.name)
            for e in entries:
                indent = "  " * depth
                if e.is_dir():
                    lines.append(f"{indent}- {e.name}/ (directory)")
                    if depth < max_depth:
                        lines.extend(_walk_tree(e, depth + 1))
                else:
                    lines.append(f"{indent}- {e.name} (file)")
            return lines

        if base_path.is_file():
            # If user provided a file, just show that item
            return f"{base_path.name} (file)"
        else:
            output_lines = [f"{base_path.name}/ (directory)"]
            if max_depth > 0:
                output_lines.extend(_walk_tree(base_path, 1))
            return "\n".join(output_lines)

    @kernel_function(description="Read the contents of a file.")
    def read_file(
        self, path: str, start_line: int = 1, end_line: Optional[int] = None
    ) -> str:
        """
        Reads 'path' in full or a specified line range [start_line, end_line].

        Args:
            path (str): Path to the file to read.
            start_line (int, optional): The 1-based line number to start from. Defaults to 1.
            end_line (int, optional): The 1-based line to end at. If None or <1, read to the end.

        Returns:
            str: The file content (or the requested slice).

        Examples:
            >>> read_file("agent.hcl")
            # Returns the entire file
            >>> read_file("script.sh", 10, 15)
            # Returns lines 10-15
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if end_line is None or end_line < 1:
                end_line = len(lines)

            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            return "".join(lines[start_idx:end_idx])
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @kernel_function(description="Write content to a file (overwriting).")
    def write_file(self, path: str, content: str) -> str:
        """
        Overwrites the file at 'path' with 'content'.

        Args:
            path (str): The file path to write to.
            content (str): The new content.

        Returns:
            str: Success message or error.

        Examples:
            >>> write_file("notes.txt", "Hello world!")
            "Successfully wrote to file: notes.txt"
        """
        try:
            file_path = self._validate_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to file: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @kernel_function(description="Delete a file or directory.")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """
        Deletes a file or directory. For directories, 'recursive=True' is required.

        Args:
            path (str): The path to delete.
            recursive (bool, optional): Whether to delete directories recursively. Defaults to False.

        Returns:
            str: Success or error message.

        Examples:
            >>> delete_file("temp.log")
            "Successfully deleted file: temp.log"
            >>> delete_file("old_project", recursive=True)
            "Successfully deleted directory: old_project"
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
        Executes a shell command in the workspace. Optionally in subdirectory 'cwd'.

        Args:
            command (str): The shell command to run.
            cwd (str, optional): Subfolder in which to run the command. Defaults to "" (workspace root).

        Returns:
            str: Combined stdout/stderr plus an exit code message if non-zero.

        Examples:
            >>> run_terminal_command("ls -la", cwd="src")
            # Returns the output from listing the 'src' folder.
        """
        try:
            work_dir = self._validate_path(cwd) if cwd else self.workspace_root
            result = subprocess.run(
                command, shell=True, cwd=work_dir, capture_output=True, text=True
            )

            output_parts = []
            if result.stdout.strip():
                output_parts.append("Output:")
                output_parts.append(result.stdout.strip())
            if result.stderr.strip():
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

    @kernel_function(
        description="Search for text in files. By default searches all files. Use file_pattern parameter to narrow search to specific file types (e.g. '*.extension')."
    )
    def search(
        self,
        query: str,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        context_lines: int = 2,
        max_results: int = 25,
    ) -> str:
        """
        Searches for 'query' in files matching 'file_pattern', returning lines with context.
        If no matches are found with a specific file pattern, will suggest trying a broader search.

        Args:
            query (str): The text to search for.
            file_pattern (str, optional): Glob for files to include (e.g. "*.extension"). Defaults to "*" for all files.
            case_sensitive (bool, optional): Whether the search is case-sensitive. Defaults to False.
            context_lines (int, optional): Number of lines of context around each match. Defaults to 2.
            max_results (int, optional): Maximum matches to return. Defaults to 25.

        Returns:
            str: A formatted string with matching lines or a helpful message if no matches found.

        Examples:
            >>> search("model_temperature")
            # Searches all files for the string "model_temperature"
            >>> search("TODO", file_pattern="*.extension")
            # Search for "TODO" in files with specific extension
            >>> search("config")
            # Search for "config" in all files
        """
        try:
            results = self._run_search_command(
                pattern=query,
                file_pattern=file_pattern,
                case_sensitive=case_sensitive,
                context_lines=context_lines,
                max_results=max_results,
            )
            if not results and file_pattern != "*":
                # If no results found with specific file pattern, suggest trying all files
                return f"No matches found in files matching '{file_pattern}'. Try searching all files with: search(\"{query}\")"
            return self._format_search_results(results)
        except Exception as e:
            return f"Error during search: {str(e)}"

    @kernel_function(description="Line-based file editing.")
    def edit_file(self, path: str, content: str = "", mode: str = "replace") -> str:
        """
        Performs line-based edits on 'path' according to the specified mode.

        Args:
            path (str): The file to edit.
            content (str, optional): The new text to insert or replace. Defaults to "".
            mode (str, optional): One of:
                "replace"  -> overwrite entire file
                "append"   -> add content at the end
                "prepend"  -> add content at the start
                "insert:<line_num>" -> insert content at that line (1-based)
                "replace:<line_num>" -> replace exactly that line
                "replace:<start>-<end>" -> replace lines in [start, end]
                "smart" -> naive best-match insertion point (if uncertain, appends)

        Returns:
            str: A success or error message.

        Examples:
            >>> edit_file("config.hcl", content="variable \"debug_mode\" {...}", mode="append")
            # Appends content to config.hcl
            >>> edit_file("README.md", content="# My Project", mode="replace:1")
            # Replaces line 1 with "# My Project"
        """
        try:
            file_path = self._validate_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            else:
                existing_content = ""

            new_content = existing_content

            if mode == "replace":
                new_content = content

            elif mode == "append":
                if new_content and not new_content.endswith("\n"):
                    new_content += "\n"
                new_content += content

            elif mode == "prepend":
                insertion = content
                if insertion and not insertion.endswith("\n"):
                    insertion += "\n"
                new_content = insertion + new_content

            elif mode.startswith("insert:"):
                # insert:<line_num>
                _, line_str = mode.split(":")
                line_num = max(1, int(line_str))
                lines = existing_content.splitlines()
                if line_num > len(lines) + 1:
                    line_num = len(lines) + 1
                lines.insert(line_num - 1, content)
                new_content = "\n".join(lines)
                if existing_content.endswith("\n"):
                    new_content += "\n"

            elif mode.startswith("replace:"):
                # replace:<line_num> or replace:<start>-<end>
                _, spec = mode.split(":")
                lines = existing_content.splitlines()

                if "-" in spec:
                    start_str, end_str = spec.split("-")
                    start = max(1, int(start_str))
                    end = min(len(lines), int(end_str))
                    replacement_lines = content.splitlines()
                    lines[start - 1 : end] = replacement_lines
                else:
                    line_num = max(1, int(spec))
                    if line_num > len(lines):
                        line_num = len(lines)
                    lines[line_num - 1] = content

                new_content = "\n".join(lines)
                if existing_content.endswith("\n"):
                    new_content += "\n"

            elif mode == "smart":
                if not existing_content.strip():
                    new_content = content
                else:
                    lines = existing_content.splitlines()
                    content_lines = content.splitlines()
                    best_index = -1
                    best_score = 0
                    # Attempt to find the line with the largest word overlap
                    for i, line in enumerate(lines):
                        score = 0
                        for c_line in content_lines:
                            common = set(line.split()) & set(c_line.split())
                            score += len(common)
                        if score > best_score:
                            best_score = score
                            best_index = i
                    if best_index >= 0:
                        lines.insert(best_index + 1, content)
                        new_content = "\n".join(lines)
                        if existing_content.endswith("\n"):
                            new_content += "\n"
                    else:
                        # fallback to append
                        if new_content and not new_content.endswith("\n"):
                            new_content += "\n"
                        new_content += content
            else:
                return f"Invalid mode: '{mode}'."

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"Successfully edited file: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @kernel_function(description="Remove lines from a file by line number/count.")
    def remove_lines(self, path: str, start_line: int, num_lines: int = 1) -> str:
        """
        Removes a block of lines starting at 'start_line' (1-based), for 'num_lines' lines.

        Args:
            path (str): The file to edit.
            start_line (int): The first line to remove (1-based).
            num_lines (int, optional): How many lines to remove. Defaults to 1.

        Returns:
            str: A success or error message.

        Examples:
            >>> remove_lines("notes.txt", 5, 3)
            # Removes lines 5, 6, and 7 from notes.txt
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if start_line < 1 or start_line > len(lines):
                return f"Invalid start line: {start_line}"

            start_idx = start_line - 1
            end_idx = min(start_idx + num_lines, len(lines))
            del lines[start_idx:end_idx]

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            removed = end_idx - start_idx
            return f"Successfully removed {removed} line(s) from {path}"
        except Exception as e:
            return f"Error removing lines: {str(e)}"

    @kernel_function(description="Regex-based file editing.")
    def pattern_edit(
        self, path: str, pattern: str, new_content: str = "", mode: str = "replace"
    ) -> str:
        """
        Edits text in a file by matching a regex pattern and modifying those matches.

        Args:
            path (str): The file to edit.
            pattern (str): A regex pattern to match.
            new_content (str, optional): The text to use in "replace", "before", or "after". Defaults to "".
            mode (str, optional): One of:
                - "remove": delete matched text
                - "replace": replace matched text with new_content
                - "before": insert new_content before each match
                - "after": insert new_content after each match
              Defaults to "replace".

        Returns:
            str: Success message, including how many matches were changed.

        Examples:
            >>> pattern_edit("config.ini", r"(?i)username\s*=\s*\S+", "username = new_user")
            # Replaces any line with "username = something" (case-insensitive)
        """
        try:
            valid_modes = ["remove", "replace", "before", "after"]
            if mode not in valid_modes:
                return f"Invalid mode: '{mode}'. Must be one of {valid_modes}."

            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r", encoding="utf-8") as f:
                original = f.read()

            matches = list(re.finditer(pattern, original, flags=re.MULTILINE))
            if not matches:
                return "No matches found."

            new_text = original
            for m in reversed(matches):
                start_idx, end_idx = m.span()
                if mode == "remove":
                    new_text = new_text[:start_idx] + new_text[end_idx:]
                elif mode == "replace":
                    new_text = new_text[:start_idx] + new_content + new_text[end_idx:]
                elif mode == "before":
                    new_text = new_text[:start_idx] + new_content + new_text[start_idx:]
                elif mode == "after":
                    new_text = new_text[:end_idx] + new_content + new_text[end_idx:]

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return f"Successfully edited file: {path} ({len(matches)} match(es))"
        except re.error as re_err:
            return f"Regex error: {str(re_err)}"
        except Exception as e:
            return f"Error in pattern_edit: {str(e)}"

    @kernel_function(description="Get the plugin usage instructions.")
    def get_instructions(self) -> str:
        """
        Returns a high-level usage guide for this generic code editor plugin.

        Returns:
            str: The recommended workflow steps and usage details.
        """
        return self.PLUGIN_INSTRUCTIONS
