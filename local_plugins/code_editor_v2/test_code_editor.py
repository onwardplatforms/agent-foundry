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


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize Git repository in the temp directory
        temp_path = Path(temp_dir).resolve()  # Resolve the path to handle symlinks
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
    return CodeEditorV2Plugin(
        workspace_root=temp_workspace.resolve()
    )  # Resolve the workspace root


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
""".strip()

    py_file = (temp_workspace / "sample.py").resolve()  # Resolve the path
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

    txt_file = (temp_workspace / "sample.txt").resolve()  # Resolve the path
    txt_file.write_text(txt_content)
    files["text"] = txt_file

    # Stage files in Git
    subprocess.run(
        ["git", "add", "."], cwd=str(temp_workspace), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(temp_workspace),
        check=True,
        capture_output=True,
    )

    return files
