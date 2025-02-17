import os
import pytest
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Generator, Dict

# Use explicit relative import for local plugin code
from project.local_plugins.code_editor_v2 import (
    CodeEditorV2Plugin,
    CodeSnippet,
    CodeChange,
    ChangeType,
    ProcessResult,
)

pytestmark = pytest.mark.code_editor_v2  # Mark all tests in this module

# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Resolve the temporary directory path to handle macOS /var -> /private/var symlink
        temp_path = Path(temp_dir).resolve()
        # Initialize Git repository in the temp directory
        subprocess.run(
            ["git", "init"], cwd=str(temp_path), check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(temp_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(temp_path),
            check=True,
            capture_output=True,
        )
        yield temp_path


@pytest.fixture
def plugin(temp_workspace: Path) -> CodeEditorV2Plugin:
    """Create a plugin instance with a temporary workspace."""
    return CodeEditorV2Plugin(workspace_root=temp_workspace)


@pytest.fixture
def sample_files(temp_workspace: Path) -> Dict[str, Path]:
    """Create sample files for testing."""
    files = {}

    # Sample Python file
    py_content = """
def hello_world():
    print("Hello, World!")

def add(a, b):
    return a + b

class TestClass:
    def __init__(self):
        self.value = 42

    def get_value(self):
        return self.value

    def process_data(self):
        with self.context() as ctx:
            try:
                if self.data:
                    for item in self.data:
                        yield item
            except Exception as e:
                self.handle_error(e)
""".strip()

    py_file = temp_workspace / "sample.py"
    py_file.write_text(py_content)
    files["python"] = py_file

    # Sample text file
    txt_content = """
Line 1
Line 2
Line 3
Line 4
Line 5
""".strip()

    txt_file = temp_workspace / "sample.txt"
    txt_file.write_text(txt_content)
    files["text"] = txt_file

    # Stage files in Git
    subprocess.run(
        ["git", "add", "."], cwd=temp_workspace, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_workspace,
        check=True,
        capture_output=True,
    )

    return files


# -------------------------------------------------------------------------
# Core Functionality Tests
# -------------------------------------------------------------------------


class TestFileOperations:
    """Test basic file operations."""

    def test_read_file(self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]):
        """Test reading entire files and specific line ranges."""
        # Test reading entire file
        content = plugin.read_file(
            str(sample_files["python"].relative_to(plugin.workspace_root))
        )
        assert "hello_world" in content
        assert "TestClass" in content

        # Test reading specific lines
        partial = plugin.read_file(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            start_line=1,
            end_line=3,
        )
        assert "hello_world" in partial
        assert "TestClass" not in partial

        # Test reading non-existent file
        result = plugin.read_file("nonexistent.txt")
        assert "Error" in result

    def test_write_file(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test writing content to files."""
        content = "Test content"
        result = plugin.write_file("new_file.txt", content)
        assert "Successfully" in result

        # Verify file was created and content written
        file_path = temp_workspace / "new_file.txt"
        assert file_path.exists()
        assert file_path.read_text() == content

    def test_delete_file(
        self,
        plugin: CodeEditorV2Plugin,
        sample_files: Dict[str, Path],
        temp_workspace: Path,
    ):
        """Test file and directory deletion."""
        # Test file deletion
        result = plugin.delete_file(
            str(sample_files["text"].relative_to(plugin.workspace_root))
        )
        assert "Successfully" in result
        assert not sample_files["text"].exists()

        # Test directory deletion
        test_dir = temp_workspace / "test_dir"
        test_dir.mkdir()
        (test_dir / "test_file.txt").write_text("test")

        # Should fail without recursive flag
        result = plugin.delete_file("test_dir")
        assert "Error" in result
        assert test_dir.exists()

        # Should succeed with recursive flag
        result = plugin.delete_file("test_dir", recursive=True)
        assert "Successfully" in result
        assert not test_dir.exists()


class TestSnippetMatching:
    """Test code snippet matching functionality."""

    def test_exact_matching(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test exact snippet matching."""
        snippet = """def hello_world():
    print("Hello, World!")"""

        # Create snippet object
        target = CodeSnippet(
            content=snippet,
            start_line=1,
            end_line=2,
            context_before=[],
            context_after=[],
        )

        # Test matching
        match_result = plugin._find_snippet_match(
            sample_files["python"].read_text(), target, fuzzy=False
        )

        assert match_result.matched
        assert match_result.match_type == "exact"
        assert match_result.start_line == 1

    def test_fuzzy_matching(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test fuzzy snippet matching."""
        # Same content but different whitespace
        snippet = """def hello_world():
        print("Hello, World!")"""  # Extra indentation

        target = CodeSnippet(
            content=snippet,
            start_line=1,
            end_line=2,
            context_before=[],
            context_after=[],
        )

        match_result = plugin._find_snippet_match(
            sample_files["python"].read_text(), target, fuzzy=True
        )

        assert match_result.matched
        assert match_result.match_type == "fuzzy"

    def test_context_matching(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test matching with context verification."""
        snippet = """def add(a, b):
    return a + b"""

        target = CodeSnippet(
            content=snippet,
            start_line=4,
            end_line=5,
            context_before=["def hello_world():", '    print("Hello, World!")'],
            context_after=["", "class TestClass:"],
        )

        match_result = plugin._find_snippet_match(
            sample_files["python"].read_text(), target, fuzzy=False, context_lines=2
        )

        assert match_result.matched
        assert match_result.context_matches


class TestCodeModification:
    """Test code modification operations."""

    def test_update_code(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test updating code snippets."""
        old_snippet = """def add(a, b):
    return a + b"""

        new_content = """def add(a, b):
    # Add two numbers
    return a + b"""

        result = plugin.update_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            old_snippet,
            new_content,
        )

        assert "Successfully queued update" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change
        updated_content = sample_files["python"].read_text()
        assert "# Add two numbers" in updated_content

    def test_delete_code(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test deleting code snippets."""
        snippet_to_delete = """def add(a, b):
    return a + b"""

        result = plugin.delete_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            snippet_to_delete,
        )

        assert "Successfully queued deletion" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the deletion
        updated_content = sample_files["python"].read_text()
        assert "def add(a, b):" not in updated_content

    def test_insert_code(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test inserting code snippets."""
        target_snippet = "def hello_world():"
        new_content = "# This is a greeting function"

        result = plugin.insert_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            new_content=new_content,
            position="before",
            target_snippet=target_snippet,
        )

        assert "Successfully queued insertion" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the insertion
        updated_content = sample_files["python"].read_text()
        assert "# This is a greeting function" in updated_content

    def test_nested_structure_updates(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test updating code within nested structures (classes, functions, etc)."""
        # Update a method inside a class
        old_snippet = """    def get_value(self):
        return self.value"""

        new_content = """    def get_value(self):
        # Add validation
        if not hasattr(self, 'value'):
            raise AttributeError("value not set")
        return self.value"""

        result = plugin.update_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            old_snippet,
            new_content,
        )

        assert "Successfully queued update" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change
        updated_content = sample_files["python"].read_text()
        assert "if not hasattr(self, 'value'):" in updated_content
        assert "raise AttributeError" in updated_content

    def test_multiline_pattern_matching(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test matching and updating patterns that span multiple lines with varying indentation."""
        old_snippet = """class TestClass:
    def __init__(self):
        self.value = 42"""

        new_content = """class TestClass:
    def __init__(self, initial_value=42):
        self.value = initial_value"""

        result = plugin.update_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            old_snippet,
            new_content,
        )

        assert "Successfully queued update" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change
        updated_content = sample_files["python"].read_text()
        assert "def __init__(self, initial_value=42):" in updated_content
        assert "self.value = initial_value" in updated_content

    def test_concurrent_modifications(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test applying multiple changes to the same file in one operation."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # Queue multiple changes
        result1 = plugin.update_code(file_path, "def hello_world():", "def greet():")
        assert "Successfully queued update" in result1

        result2 = plugin.insert_code(
            file_path, "# New function", "before", "def add(a, b):"
        )
        assert "Successfully queued insertion" in result2

        result3 = plugin.delete_code(
            file_path,
            """    def get_value(self):
        return self.value""",
        )
        assert "Successfully queued deletion" in result3

        # Apply all changes at once
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify all changes
        updated_content = sample_files["python"].read_text()
        assert "def greet():" in updated_content
        assert "def hello_world():" not in updated_content
        assert "# New function" in updated_content
        assert "def get_value(self):" not in updated_content

    def test_code_block_dependencies(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test modifications that affect dependent code blocks."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # First rename the class
        old_class = """class TestClass:
    def __init__(self):
        self.value = 42"""

        new_class = """class ValueHolder:
    def __init__(self):
        self.value = 42"""

        result = plugin.update_code(file_path, old_class, new_class)
        assert "Successfully queued update" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change
        updated_content = sample_files["python"].read_text()
        assert "class ValueHolder:" in updated_content
        assert "class TestClass:" not in updated_content

    def test_complex_indentation(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test modifications with complex indentation patterns."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # Add a complex nested structure
        plugin.update_code(
            file_path,
            """    def get_value(self):
        return self.value""",
            """    @property
    def value(self):
        with context_manager():
            try:
                if self._value:
                    return self._value
            except AttributeError:
                return None""",
        )

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change
        updated_content = sample_files["python"].read_text()
        assert "@property" in updated_content
        assert "with context_manager():" in updated_content
        assert "try:" in updated_content
        assert "except AttributeError:" in updated_content

    def test_edge_cases(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test edge cases in code modifications."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # Test modifications at file boundaries
        result1 = plugin.insert_code(
            file_path, "# First line\n", "before", "def hello_world():"
        )
        assert "Successfully queued insertion" in result1

        # Test empty lines and whitespace
        result2 = plugin.update_code(
            file_path,
            """def add(a, b):
    return a + b""",
            """def add(a, b):
    # Added comment
    return a + b""",
        )
        assert "Successfully queued update" in result2

        # Test unicode characters
        result3 = plugin.update_code(
            file_path, '    print("Hello, World!")', '    print("Hello 🌍!")'
        )
        assert "Successfully queued update" in result3

        # Apply all changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the changes
        updated_content = sample_files["python"].read_text()
        assert "# First line" in updated_content
        assert "# Added comment" in updated_content
        assert 'print("Hello 🌍!")' in updated_content

    def test_complex_indentation_preservation(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test that complex indentation patterns are preserved during updates."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # Test nested structure with mixed indentation
        old_snippet = """    def process_data(self):
        with self.context() as ctx:
            try:
                if self.data:
                    for item in self.data:
                        yield item
            except Exception as e:
                self.handle_error(e)"""

        new_content = """    def process_data(self):
        with self.context() as ctx:
            try:
                if self.validated_data:
                    for item in self.validated_data:
                        if item.is_valid():
                            yield item.process()
                        else:
                            self.log_invalid(item)
            except Exception as e:
                self.handle_error(e)
                self.cleanup()"""

        # Update the code
        result = plugin.update_code(file_path, old_snippet, new_content)
        assert "Successfully queued update" in result

        # Apply the changes
        apply_result = plugin.apply_changes()
        assert "Successfully applied changes" in apply_result

        # Verify the change preserved indentation
        updated_content = sample_files["python"].read_text()

        # Check indentation of key lines
        assert "    def process_data(self):" in updated_content
        assert "        with self.context() as ctx:" in updated_content
        assert "            try:" in updated_content
        assert "                if self.validated_data:" in updated_content
        assert "                    for item in self.validated_data:" in updated_content
        assert "                        if item.is_valid():" in updated_content
        assert "                            yield item.process()" in updated_content
        assert "                        else:" in updated_content
        assert "                            self.log_invalid(item)" in updated_content
        assert "            except Exception as e:" in updated_content
        assert "                self.handle_error(e)" in updated_content
        assert "                self.cleanup()" in updated_content


class TestChangeManagement:
    """Test change management functionality."""

    def test_change_history(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test change history tracking."""
        # Make some changes
        plugin.update_code(
            str(sample_files["python"].relative_to(plugin.workspace_root)),
            "def hello_world():",
            "def greet():",
        )
        plugin.apply_changes()

        # Get history
        history = plugin.get_change_history(
            str(sample_files["python"].relative_to(plugin.workspace_root))
        )
        assert "Update" in history

    def test_revert_changes(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test change reversion."""
        file_path = str(sample_files["python"].relative_to(plugin.workspace_root))

        # Ensure initial state is committed in Git
        initial_content = sample_files["python"].read_text()
        assert "def hello_world():" in initial_content

        # Make a change
        plugin.update_code(file_path, "def hello_world():", "def greet():")
        plugin.apply_changes()

        # Verify change was made
        content_after_change = sample_files["python"].read_text()
        assert "def greet():" in content_after_change
        assert "def hello_world():" not in content_after_change

        # Revert the change
        revert_result = plugin.revert_changes(file_path)
        assert "Successfully reverted" in revert_result

        # Verify reversion
        content_after_revert = sample_files["python"].read_text()
        assert "def hello_world():" in content_after_revert
        assert "def greet():" not in content_after_revert


class TestProcessManagement:
    """Test process management functionality."""

    def test_run_command(self, plugin: CodeEditorV2Plugin):
        """Test basic command execution."""
        result = plugin.run_terminal_command("echo 'test'")
        assert "test" in result
        assert "Command:" in result
        assert "Duration:" in result

    def test_command_timeout(self, plugin: CodeEditorV2Plugin):
        """Test command timeout functionality."""
        result = plugin.run_terminal_command("sleep 2", timeout=1)
        assert "killed" in result.lower()

    def test_command_with_env(self, plugin: CodeEditorV2Plugin):
        """Test command execution with environment variables."""
        result = plugin.run_terminal_command(
            "echo $TEST_VAR", env={"TEST_VAR": "test_value"}
        )
        assert "test_value" in result


class TestSearchAndDiscovery:
    """Test search and discovery functionality."""

    def test_search_across_files(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test searching across multiple files."""
        result = plugin.search_across_files("hello_world", file_pattern="*.py")
        assert str(sample_files["python"].name) in result

    def test_find_references(
        self, plugin: CodeEditorV2Plugin, sample_files: Dict[str, Path]
    ):
        """Test finding symbol references."""
        result = plugin.find_references("hello_world", file_pattern="*.py")
        assert str(sample_files["python"].name) in result
        assert "def hello_world()" in result


class TestPathHandling:
    """Test path handling and validation."""

    def test_symlink_handling(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test handling of symlinked directories and files."""
        # Create a subdirectory with a file
        subdir = temp_workspace / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("test content")

        # Create a symlink to the subdirectory
        symlink_dir = temp_workspace / "symlink_dir"
        os.symlink(subdir, symlink_dir)

        try:
            # Test reading through symlink
            result = plugin.read_file("symlink_dir/test.txt")
            assert "test content" in result

            # Test writing through symlink
            plugin.write_file("symlink_dir/new_file.txt", "new content")
            assert (subdir / "new_file.txt").read_text() == "new content"

        finally:
            # Cleanup
            symlink_dir.unlink()

    def test_relative_absolute_paths(
        self, plugin: CodeEditorV2Plugin, temp_workspace: Path
    ):
        """Test handling of relative and absolute paths."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test content")

        # Test relative path
        rel_result = plugin.read_file("test.txt")
        assert "test content" in rel_result

        # Test absolute path
        abs_result = plugin.read_file(str(test_file))
        assert "test content" in abs_result

        # Test path outside workspace
        with pytest.raises(ValueError, match="outside workspace root"):
            plugin.read_file("/etc/passwd")

    def test_path_edge_cases(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test path validation edge cases."""
        # Test empty path
        with pytest.raises(ValueError):
            plugin.read_file("")

        # Test path with only dots
        with pytest.raises(ValueError):
            plugin.read_file("...")

        # Test path with parent directory traversal
        with pytest.raises(ValueError):
            plugin.read_file("../test.txt")


class TestGitOperations:
    """Test Git-based operations."""

    def test_git_subdirectory_operations(
        self, plugin: CodeEditorV2Plugin, temp_workspace: Path
    ):
        """Test Git operations in subdirectories."""
        # Create nested directory structure
        subdir = temp_workspace / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("initial content")

        # Make changes through the plugin
        plugin.update_code(
            str(test_file.relative_to(temp_workspace)),
            "initial content",
            "updated content",
        )
        plugin.apply_changes()

        # Verify Git history
        history = plugin.get_change_history(str(test_file.relative_to(temp_workspace)))
        assert "updated content" in history

    def test_binary_file_handling(
        self, plugin: CodeEditorV2Plugin, temp_workspace: Path
    ):
        """Test handling of binary files in Git."""
        # Create a binary file
        binary_file = temp_workspace / "test.bin"
        with open(binary_file, "wb") as f:
            f.write(bytes(range(256)))

        # Test operations on binary file
        with pytest.raises(UnicodeDecodeError):
            plugin.read_file("test.bin")


class TestAdvancedProcessManagement:
    """Test advanced process management features."""

    def test_output_streaming(self, plugin: CodeEditorV2Plugin):
        """Test real-time output streaming."""
        result = plugin.run_terminal_command(
            "for i in 1 2 3; do echo $i; sleep 0.1; done", stream_output=True
        )
        assert "1" in result
        assert "2" in result
        assert "3" in result

    def test_process_interruption(self, plugin: CodeEditorV2Plugin):
        """Test process interruption handling."""
        # Start a long-running process and interrupt it
        result = plugin.run_terminal_command(
            "sleep 10", timeout=1  # Force timeout/interruption
        )
        assert "killed" in result.lower()

    def test_shell_environment(self, plugin: CodeEditorV2Plugin):
        """Test handling different shell environments."""
        # Test with custom environment variables
        env = {"TEST_VAR": "test_value", "PATH": os.environ["PATH"]}
        result = plugin.run_terminal_command("echo $TEST_VAR", env=env, shell=True)
        assert "test_value" in result


class TestLintingAndFormatting:
    """Test linting and formatting functionality."""

    @pytest.mark.skip_missing_deps
    def test_lint_python(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test Python linting."""
        try:
            import black
        except ImportError:
            pytest.skip("black not installed")

        # Create a Python file with linting issues
        python_file = temp_workspace / "test.py"
        python_file.write_text(
            """
def bad_function( ):
    x=1+2
    y= x*3
    return  y
""".strip()
        )

        # Test linting without fixes
        result = plugin.lint_code(str(python_file.relative_to(plugin.workspace_root)))
        assert "issues found" in result.lower()
        assert "whitespace" in result.lower() or "spacing" in result.lower()

        # Test linting with fixes
        result = plugin.lint_code(
            str(python_file.relative_to(plugin.workspace_root)), fix=True
        )
        assert "fixed" in result.lower()

        # Verify fixes were applied
        content = python_file.read_text()
        assert "def bad_function():" in content  # Extra space removed
        assert "x = 1 + 2" in content  # Spaces added around operators

    @pytest.mark.skip_missing_deps
    def test_lint_javascript(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test JavaScript linting."""
        # Check if eslint is available
        result = subprocess.run(["which", "eslint"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("eslint not installed")

        # Check ESLint version
        version_result = subprocess.run(
            ["eslint", "--version"], capture_output=True, text=True
        )
        version = version_result.stdout.strip()
        if version.startswith("v9.") or version.startswith("9."):
            pytest.skip(
                "ESLint v9+ uses a new configuration format incompatible with this test"
            )

        # Create ESLint config file in the temp workspace
        eslint_config = temp_workspace / ".eslintrc.js"
        eslint_config.write_text(
            """
module.exports = {
    "env": {
        "browser": true,
        "es2021": true,
        "node": true
    },
    "extends": "eslint:recommended",
    "parserOptions": {
        "ecmaVersion": "latest",
        "sourceType": "module"
    },
    "rules": {
        "semi": ["error", "always"],
        "quotes": ["error", "single"],
        "no-unused-vars": "warn",
        "space-before-function-paren": ["error", "never"],
        "space-before-blocks": ["error", "always"],
        "keyword-spacing": ["error", { "before": true, "after": true }],
        "comma-spacing": ["error", { "before": false, "after": true }],
        "operator-spacing": ["error", { "before": true, "after": true }],
        "indent": ["error", 2]
    }
}
""".strip()
        )

        # Create a JavaScript file with linting issues
        js_file = temp_workspace / "test.js"
        js_file.write_text(
            """
function badFunction( ){
    var x=1+2;
    var y= x*3;
    return  y;
}
""".strip()
        )

        # Test linting without fixes
        result = plugin.lint_code(str(js_file.relative_to(plugin.workspace_root)))
        assert "issues found" in result.lower()

        # Test linting with fixes
        result = plugin.lint_code(
            str(js_file.relative_to(plugin.workspace_root)), fix=True
        )
        assert "fixed" in result.lower()

    @pytest.mark.skip_missing_deps
    def test_format_python(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test Python formatting."""
        try:
            import black
        except ImportError:
            pytest.skip("black not installed")

        # Create a Python file with formatting issues
        python_file = temp_workspace / "test.py"
        python_file.write_text(
            """
def poorly_formatted_function():
    x=[1,2,
    3,4]
    if True:
     return x
""".strip()
        )

        # Test formatting
        result = plugin.format_code(str(python_file.relative_to(plugin.workspace_root)))
        assert "formatted" in result.lower()

        # Verify formatting was applied
        content = python_file.read_text()
        assert "x = [1, 2, 3, 4]" in content  # List formatting fixed
        assert "    return x" in content  # Indentation fixed

    @pytest.mark.skip_missing_deps
    def test_format_javascript(self, plugin: CodeEditorV2Plugin, temp_workspace: Path):
        """Test JavaScript formatting."""
        # Check if prettier is available
        result = subprocess.run(["which", "prettier"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("prettier not installed")

        # Create a JavaScript file with formatting issues
        js_file = temp_workspace / "test.js"
        js_file.write_text(
            """
function poorlyFormattedFunction(){
    const x=[1,2,
    3,4];
    if(true){
     return x;
    }
}
""".strip()
        )

        # Test formatting
        result = plugin.format_code(str(js_file.relative_to(plugin.workspace_root)))
        assert "formatted" in result.lower()

    def test_lint_invalid_file(self, plugin: CodeEditorV2Plugin):
        """Test linting a non-existent file."""
        result = plugin.lint_code("nonexistent.py")
        assert "error" in result.lower()
        assert "does not exist" in result.lower()

    def test_format_invalid_file(self, plugin: CodeEditorV2Plugin):
        """Test formatting a non-existent file."""
        result = plugin.format_code("nonexistent.py")
        assert "error" in result.lower()
        assert "not found" in result.lower()

    def test_lint_unsupported_extension(
        self, plugin: CodeEditorV2Plugin, temp_workspace: Path
    ):
        """Test linting a file with unsupported extension."""
        # Create a file with unsupported extension
        test_file = temp_workspace / "test.xyz"
        test_file.write_text("test content")

        result = plugin.lint_code(str(test_file.relative_to(plugin.workspace_root)))
        assert "error" in result.lower()
        assert "no linter configured" in result.lower()

    def test_format_unsupported_extension(
        self, plugin: CodeEditorV2Plugin, temp_workspace: Path
    ):
        """Test formatting a file with unsupported extension."""
        # Create a file with unsupported extension
        test_file = temp_workspace / "test.xyz"
        test_file.write_text("test content")

        result = plugin.format_code(str(test_file.relative_to(plugin.workspace_root)))
        assert "error" in result.lower()
        assert "unsupported file type" in result.lower()
