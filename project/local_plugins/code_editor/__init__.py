import logging
import os
import re
import subprocess
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Literal

try:
    from semantic_kernel.functions.kernel_function_decorator import kernel_function
except ImportError:
    # Fallback if not running inside Semantic Kernel
    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


class ChangeType(Enum):
    DELETE = "delete"
    UPDATE = "update"
    INSERT = "insert"


@dataclass
class Change:
    """Represents a single change to a file"""

    file_path: str
    change_type: ChangeType
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    new_content: Optional[str] = None
    previous_content: Optional[str] = None

    def __post_init__(self):
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if (
            self.change_type in (ChangeType.UPDATE, ChangeType.INSERT)
            and not self.new_content
        ):
            raise ValueError("new_content required for UPDATE and INSERT changes")


@dataclass
class LineChange:
    """Represents a change in line numbers"""

    original_start: int  # 1-based
    original_end: int  # 1-based, inclusive
    new_start: int  # 1-based
    new_length: int  # number of lines in new content

    def affects_line(self, line_number: int) -> bool:
        """Check if this change affects a given line number"""
        return line_number > self.original_start

    def adjust_line(self, line_number: int) -> int:
        """Adjust a line number based on this change"""
        if not self.affects_line(line_number):
            return line_number
        delta = self.new_length - (self.original_end - self.original_start + 1)
        return line_number + delta


@dataclass
class FileState:
    """Maintains the state of a file through multiple changes"""

    file_path: str
    original_content: str
    current_content: str
    pending_changes: List[Change]
    applied_changes: List[Change]
    line_changes: List[LineChange]  # Track all line number changes

    @classmethod
    def from_file(cls, file_path: str) -> "FileState":
        """Create a FileState from a file path"""
        with open(file_path, "r") as f:
            content = f.read()
        return cls(
            file_path=file_path,
            original_content=content,
            current_content=content,
            pending_changes=[],
            applied_changes=[],
            line_changes=[],
        )

    def add_change(self, change: Change) -> None:
        """Add a change to pending changes and adjust its line numbers"""
        adjusted_change = self._adjust_change_lines(change)
        self.pending_changes.append(adjusted_change)

    def _adjust_change_lines(self, change: Change) -> Change:
        """Adjust the line numbers of a change based on previous changes"""
        start_line = change.start_line
        end_line = change.end_line

        # Apply all previous line changes in order
        for line_change in self.line_changes:
            start_line = line_change.adjust_line(start_line)
            end_line = line_change.adjust_line(end_line)

        return Change(
            file_path=change.file_path,
            change_type=change.change_type,
            start_line=start_line,
            end_line=end_line,
            new_content=change.new_content,
        )

    def apply_pending_changes(self) -> None:
        """Apply all pending changes in order"""
        for change in self.pending_changes:
            self._apply_change(change)
            # Record the line number change
            new_length = (
                len(change.new_content.splitlines()) if change.new_content else 0
            )
            self.line_changes.append(
                LineChange(
                    original_start=change.start_line,
                    original_end=change.end_line,
                    new_start=change.start_line,
                    new_length=new_length,
                )
            )
        self.applied_changes.extend(self.pending_changes)
        self.pending_changes.clear()

    def revert_last_change(self) -> None:
        """Revert the most recently applied change"""
        if not self.applied_changes:
            return

        change = self.applied_changes.pop()
        if change.previous_content is not None:
            lines = self.current_content.splitlines()
            lines[change.start_line - 1 : change.end_line] = (
                change.previous_content.splitlines()
            )
            self.current_content = "\n".join(lines)
            if self.current_content and not self.current_content.endswith("\n"):
                self.current_content += "\n"

    def revert_all_changes(self) -> None:
        """Revert all changes and restore original content"""
        self.current_content = self.original_content
        self.applied_changes.clear()
        self.pending_changes.clear()

    def save(self) -> None:
        """Save current content back to file"""
        with open(self.file_path, "w") as f:
            f.write(self.current_content)

    def _apply_change(self, change: Change) -> None:
        """Apply a single change to current_content"""
        lines = self.current_content.splitlines()

        # Store previous content for potential revert
        change.previous_content = "\n".join(
            lines[change.start_line - 1 : change.end_line]
        )

        if change.change_type == ChangeType.DELETE:
            del lines[change.start_line - 1 : change.end_line]
        elif change.change_type == ChangeType.UPDATE:
            lines[change.start_line - 1 : change.end_line] = (
                change.new_content.splitlines()
            )
        elif change.change_type == ChangeType.INSERT:
            lines.insert(change.start_line - 1, change.new_content)

        self.current_content = "\n".join(lines)
        if self.current_content and not self.current_content.endswith("\n"):
            self.current_content += "\n"


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
    Code Editor Plugin - Usage Guide
    ==============================

    WORKFLOW FOR CODE CHANGES:
    1. READ FIRST: Always read and understand the entire file before making changes
       - Read the complete content of files you plan to modify
       - Understand the structure and dependencies
       - Consider the broader context of the codebase

    2. PLAN CHANGES:
       - Identify ALL issues that need fixing
       - Consider how changes might affect other parts of the code
       - Think about proper code organization
       - Plan your changes before executing them

    3. EXECUTE CHANGES:
       - For small, isolated changes: use targeted updates
       - For significant restructuring: rewrite the entire file
       - Make complete, coherent changes - not partial fixes
       - Ensure changes maintain code quality

    4. VERIFY CHANGES:
       - Read the updated file to verify changes
       - Check for syntax errors or structural issues
       - Ensure the code is clean and properly formatted
       - Verify that all issues were addressed

    5. COMMUNICATE CLEARLY:
       - Explain what you changed and why
       - If you're unsure about something, say so
       - If you need more information, ask for it

    Remember: Think like a human programmer. Don't rush to make changes without understanding the full context.

    Common Operations:
    1. Exploring Code:
       - List directory contents
       - Search for specific code elements
       - Find text across files

    2. Making Changes:
       - Read and update files
       - Insert or delete code
       - Modify specific ranges

    3. Managing Changes:
       - Verify changes before saving
       - Revert changes if needed
       - Execute shell commands when necessary
    """

    def __init__(self, workspace: Optional[str] = None):
        """Initialize with workspace root directory."""
        self.workspace_root = Path(workspace or os.getcwd()).resolve()
        self._file_states: Dict[str, FileState] = {}
        logger.info(
            f"CodeEditorPlugin initialized with workspace root: {self.workspace_root}"
        )

    def _get_file_state(self, path: str) -> FileState:
        """Get or create FileState for a file."""
        if path not in self._file_states:
            self._file_states[path] = FileState.from_file(path)
        return self._file_states[path]

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

    def _find_references(
        self, content: str, target: str, file_pattern: str = "*"
    ) -> List[Dict[str, Any]]:
        """
        Find references to a given target in the codebase.
        This is a more thorough search that looks for various ways a symbol might be referenced.

        Args:
            content (str): The content/symbol to search for
            target (str): Additional context about what we're looking for (e.g., "variable", "function")
            file_pattern (str): Optional file pattern to limit the search

        Returns:
            List[Dict[str, Any]]: List of matches with file and line information
        """
        # Create variations of how the target might be referenced
        variations = [
            content,  # exact match
            f"{content}\\s*=",  # assignments
            f"{content}\\.",  # property access
            f"\\.{content}\\b",  # method calls
            f"\\b{content}\\b",  # word boundaries
            f"['\"]{content}['\"]",  # string literals
        ]

        # Combine variations into a single regex pattern
        pattern = "|".join(f"({v})" for v in variations)

        # Use the existing search infrastructure
        return self._run_search_command(
            pattern=pattern,
            file_pattern=file_pattern,
            case_sensitive=True,
            context_lines=1,
            max_results=100,  # Higher limit for references
        )

    def _adjust_line_number(
        self, original_line: int, previous_changes: List[tuple[int, int]]
    ) -> int:
        """
        Adjusts a line number based on previous changes to the file.

        Args:
            original_line (int): The original 1-based line number
            previous_changes (List[tuple[int, int]]): List of (start_line, num_lines_removed) tuples
                                                    representing previous changes

        Returns:
            int: The adjusted line number accounting for previous changes
        """
        adjustment = 0
        for start, count in previous_changes:
            if start < original_line:  # If this change was before our target line
                adjustment += count  # Adjust by the number of lines removed
        return max(1, original_line - adjustment)

    def _find_block_boundaries(
        self, lines: List[str], start_line: int, language: Optional[str] = None
    ) -> tuple[int, int]:
        """
        Find the complete boundaries of a block starting from a given line.
        Handles nested blocks and proper brace/indentation matching.

        Args:
            lines (List[str]): All lines of the file
            start_line (int): 1-based line number where we found a match
            language (str, optional): Language hint for better block detection

        Returns:
            tuple[int, int]: Start and end line numbers (1-based, inclusive)
        """
        # Convert to 0-based index
        idx = start_line - 1

        # Detect indentation or block style
        if language == "python":
            # Python uses indentation
            base_line = lines[idx].rstrip()
            base_indent = len(base_line) - len(base_line.lstrip())

            # Look backwards for the block start (less indented line)
            while idx > 0:
                line = lines[idx - 1].rstrip()
                if line and len(line) - len(line.lstrip()) < base_indent:
                    break
                idx -= 1

            block_start = idx

            # Look forward for the block end (less indented line)
            idx = start_line
            while idx < len(lines):
                line = lines[idx].rstrip()
                if line and len(line) - len(line.lstrip()) < base_indent:
                    break
                idx += 1

            block_end = idx
        else:
            # Default to brace matching for other languages
            # Look backwards for the block start
            brace_count = 0
            while idx > 0:
                line = lines[idx].strip()
                brace_count += line.count("}") - line.count("{")
                if brace_count > 0 and "{" in line:
                    # Found the start
                    break
                idx -= 1

            block_start = idx

            # Look forward for the block end
            brace_count = 0
            idx = block_start
            while idx < len(lines):
                line = lines[idx].strip()
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "}" in line:
                    break
                idx += 1

            block_end = idx

        # Convert back to 1-based line numbers
        return (block_start + 1, block_end + 1)

    def _find_all_references(
        self, lines: List[str], symbol: str
    ) -> List[tuple[int, int]]:
        """
        Find all references to a symbol in the file, including its definition block.
        Returns ranges in reverse order (bottom to top) for safe removal.

        Args:
            lines (List[str]): All lines of the file
            symbol (str): The symbol to find references for

        Returns:
            List[tuple[int, int]]: List of (start_line, end_line) tuples in reverse order
        """
        ranges = []

        # First pass: find all lines containing the symbol
        for i, line in enumerate(lines, 1):
            if symbol in line:
                if "variable" in line and symbol in line:
                    # This is the variable definition block
                    start, end = self._find_block_boundaries(lines, i)
                    ranges.append((start, end))
                elif "=" in line and symbol in line:
                    # This is a reference/usage
                    ranges.append((i, i))

        # Sort in reverse order so we can remove from bottom to top
        return sorted(ranges, reverse=True)

    def _detect_language(self, file_path: str) -> str:
        """
        Detect the programming language based on file extension and content patterns.
        """
        ext = Path(file_path).suffix.lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".hcl": "hcl",
            ".tf": "hcl",
        }
        return language_map.get(ext, "unknown")

    def _get_language_patterns(self, language: str) -> Dict[str, str]:
        """
        Get regex patterns for different code elements based on language.
        """
        patterns = {
            "python": {
                "function": r"(?:async\s+)?def\s+([a-zA-Z_]\w*)\s*\([^)]*\)\s*(?:->.*?)?:",
                "class": r"class\s+([a-zA-Z_]\w*)\s*(?:\([^)]*\))?\s*:",
                "variable": r"([a-zA-Z_]\w*)\s*=\s*[^=]",
                "import": r"(?:from\s+[\w.]+\s+)?import\s+(?:[^#\n]+)",
                "decorator": r"@[\w.]+",
            },
            "javascript": {
                "function": r"(?:async\s+)?(?:function\s+([a-zA-Z_]\w*)|(?:const|let|var)\s+([a-zA-Z_]\w*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)",
                "class": r"class\s+([a-zA-Z_]\w*)",
                "variable": r"(?:const|let|var)\s+([a-zA-Z_]\w*)\s*=",
                "import": r"import\s+(?:[^;]+)",
                "export": r"export\s+(?:default\s+)?(?:class|function|const|let|var)",
            },
            "hcl": {
                "block": r'(\w+)\s+"[^"]+"\s*{',
                "variable": r'variable\s+"([^"]+)"\s*{',
                "attribute": r"([a-zA-Z_]\w*)\s*=\s*(?:[^=])",
                "reference": r"var\.([a-zA-Z_]\w*)",
            },
            # Add more languages as needed
        }
        return patterns.get(language, {})

    @kernel_function(description="Find code elements using pattern matching.")
    def find_code_elements(self, path: str, element_type: Optional[str] = None) -> str:
        """
        Find code elements (functions, classes, variables, etc.) using language-aware pattern matching.

        Args:
            path (str): Path to the file to analyze
            element_type (str, optional): Specific type of element to find (e.g., 'function', 'class', 'variable')
                                        If None, finds all supported element types.

        Returns:
            str: JSON-formatted results of found elements
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                content = f.read()

            language = self._detect_language(str(file_path))
            patterns = self._get_language_patterns(language)

            if not patterns:
                return json.dumps(
                    {
                        "error": f"Language detection failed or unsupported language for {path}"
                    }
                )

            results = {}
            if element_type:
                if element_type not in patterns:
                    return json.dumps(
                        {
                            "error": f"Element type '{element_type}' not supported for {language}"
                        }
                    )
                pattern_dict = {element_type: patterns[element_type]}
            else:
                pattern_dict = patterns

            for elem_type, pattern in pattern_dict.items():
                matches = []
                for match in re.finditer(pattern, content, re.MULTILINE):
                    # Get the line number for this match
                    line_no = content.count("\n", 0, match.start()) + 1

                    # Get some context around the match
                    lines = content.split("\n")
                    context_start = max(0, line_no - 2)
                    context_end = min(len(lines), line_no + 2)
                    context = "\n".join(lines[context_start:context_end])

                    # Get the actual matched groups, filtering out None values
                    matched_names = [g for g in match.groups() if g is not None]

                    matches.append(
                        {
                            "name": (
                                matched_names[0] if matched_names else match.group(0)
                            ),
                            "line": line_no,
                            "context": context,
                        }
                    )
                results[elem_type] = matches

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error finding code elements: {str(e)}"

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

    @kernel_function(description="Analyze code to determine required changes.")
    def analyze_changes(self, path: str, query: str) -> str:
        """
        Analyzes a file to determine what changes are needed based on a query.
        Uses LLM to understand code structure and dependencies.

        Args:
            path (str): The file to analyze
            query (str): Description of the changes needed

        Returns:
            str: JSON-formatted analysis of required changes
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                content = f.read()

            # TODO: Integrate with LLM for intelligent analysis
            analysis = {"changes": [], "dependencies": [], "warnings": []}

            return json.dumps(analysis, indent=2)

        except Exception as e:
            return f"Error analyzing changes: {str(e)}"

    @kernel_function(description="Delete a range of lines from a file.")
    def delete_range(self, path: str, start_line: int, end_line: int) -> str:
        """
        Deletes a range of lines from a file, maintaining proper spacing.
        Uses FileState to track changes and enable reverting.

        Args:
            path (str): The file to modify
            start_line (int): First line to delete (1-based)
            end_line (int): Last line to delete (1-based, inclusive)

        Returns:
            str: JSON-formatted result with deleted content
        """
        try:
            file_state = self._get_file_state(path)

            change = Change(
                file_path=path,
                change_type=ChangeType.DELETE,
                start_line=start_line,
                end_line=end_line,
            )

            file_state.add_change(change)
            file_state.apply_pending_changes()
            file_state.save()

            result = {
                "action": "delete",
                "start_line": start_line,
                "end_line": end_line,
                "deleted_content": change.previous_content,
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error deleting range: {str(e)}"

    @kernel_function(description="Update a range of lines in a file.")
    def update_range(
        self, path: str, start_line: int, end_line: int, new_content: str
    ) -> str:
        """
        Updates a range of lines in a file, tracking changes for possible revert.

        Args:
            path (str): The file to modify
            start_line (int): First line to update (1-based)
            end_line (int): Last line to update (1-based, inclusive)
            new_content (str): The new content to insert

        Returns:
            str: JSON-formatted result with before/after content
        """
        try:
            file_state = self._get_file_state(path)

            change = Change(
                file_path=path,
                change_type=ChangeType.UPDATE,
                start_line=start_line,
                end_line=end_line,
                new_content=new_content,
            )

            file_state.add_change(change)
            file_state.apply_pending_changes()
            file_state.save()

            result = {
                "action": "update",
                "start_line": start_line,
                "end_line": end_line,
                "original_content": change.previous_content,
                "new_content": new_content,
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error updating range: {str(e)}"

    @kernel_function(description="Insert code at a specific point in a file.")
    def insert_code(self, path: str, line_number: int, content: str) -> str:
        """
        Inserts code at a specific line number, handling spacing and tracking changes.

        Args:
            path (str): The file to modify
            line_number (int): Line number to insert at (1-based)
            content (str): The code to insert

        Returns:
            str: JSON-formatted result with inserted content
        """
        try:
            file_state = self._get_file_state(path)

            change = Change(
                file_path=path,
                change_type=ChangeType.INSERT,
                start_line=line_number,
                end_line=line_number,
                new_content=content,
            )

            file_state.add_change(change)
            file_state.apply_pending_changes()
            file_state.save()

            result = {
                "action": "insert",
                "line_number": line_number,
                "inserted_content": content,
                "num_lines_added": len(content.splitlines()),
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error inserting code: {str(e)}"

    @kernel_function(description="Verify changes made to a file.")
    def verify_changes(self, path: str) -> str:
        """
        Verifies changes made to a file by checking syntax and references.
        Uses FileState to access original content for comparison.

        Args:
            path (str): The file to verify

        Returns:
            str: JSON-formatted verification results
        """
        try:
            file_path = self._validate_path(path)
            if not file_path.exists():
                return f"Error: File '{path}' does not exist."

            with open(file_path, "r") as f:
                current_content = f.read()

            # Basic syntax validation
            syntax_valid = True
            syntax_errors = []
            try:
                if path.endswith(".py"):
                    compile(current_content, path, "exec")
            except Exception as e:
                syntax_valid = False
                syntax_errors.append(str(e))

            # Generate diff from original
            # TODO: Implement proper diff generation

            result = {
                "syntax_valid": syntax_valid,
                "syntax_errors": syntax_errors,
                "changes": [
                    {
                        "type": c.change_type.value,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "content_before": c.previous_content,
                        "content_after": c.new_content,
                    }
                    for c in self._get_file_state(path).applied_changes
                ],
                "warnings": [],
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error verifying changes: {str(e)}"

    @kernel_function(description="Revert changes made to a file.")
    def revert_changes(self, path: str, num_changes: int = 1) -> str:
        """
        Reverts the last N changes made to a file.

        Args:
            path (str): The file to revert changes in
            num_changes (int): Number of changes to revert (default: 1)

        Returns:
            str: JSON-formatted revert results
        """
        try:
            file_state = self._get_file_state(path)

            reverted = []
            for _ in range(num_changes):
                if not file_state.applied_changes:
                    break
                change = file_state.applied_changes[-1]
                reverted.append(
                    {
                        "type": change.change_type.value,
                        "start_line": change.start_line,
                        "end_line": change.end_line,
                        "content": change.previous_content,
                    }
                )
                file_state.revert_last_change()

            file_state.save()

            result = {
                "reverted_changes": reverted,
                "remaining_changes": len(file_state.applied_changes),
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error reverting changes: {str(e)}"

    @kernel_function(description="Get the plugin usage instructions.")
    def get_instructions(self) -> str:
        """Returns the recommended workflow steps and usage details."""
        return self.PLUGIN_INSTRUCTIONS

    @kernel_function(description="Remove a symbol and all its references from a file.")
    def remove_symbol(self, path: str, symbol: str) -> str:
        """
        Removes a symbol (like a variable) and all its references from a file.
        Handles complete blocks and maintains proper spacing.

        Args:
            path (str): The file to modify
            symbol (str): The symbol to remove

        Returns:
            str: JSON-formatted result with removed content
        """
        try:
            file_state = self._get_file_state(path)

            with open(path, "r") as f:
                lines = f.readlines()

            ranges = self._find_all_references(lines, symbol)
            if not ranges:
                return json.dumps(
                    {"message": f"No references to '{symbol}' found in {path}"}
                )

            changes = []
            for start, end in ranges:
                change = Change(
                    file_path=path,
                    change_type=ChangeType.DELETE,
                    start_line=start,
                    end_line=end,
                )
                file_state.add_change(change)
                changes.append(
                    {
                        "start_line": start,
                        "end_line": end,
                        "content": "\n".join(lines[start - 1 : end]),
                    }
                )

            file_state.apply_pending_changes()
            file_state.save()

            result = {"action": "remove_symbol", "symbol": symbol, "changes": changes}

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error removing symbol: {str(e)}"
