import pytest


def pytest_configure(config):
    """Configure custom markers for the code editor tests."""
    config.addinivalue_line(
        "markers",
        "code_editor_v2: mark tests as belonging to the CodeEditorV2Plugin test suite",
    )
    config.addinivalue_line(
        "markers",
        "skip_missing_deps: mark tests that should be skipped if dependencies are missing",
    )
