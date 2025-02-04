.PHONY: help venv install install-dev clean test lint format check all

# Variables
PYTHON = python3
VENV = venv
VENV_BIN = $(VENV)/bin
PYTEST = $(VENV_BIN)/pytest
PIP = $(VENV_BIN)/pip
BLACK = $(VENV_BIN)/black
FLAKE8 = $(VENV_BIN)/flake8
ISORT = $(VENV_BIN)/isort
MYPY = $(VENV_BIN)/mypy

help:
	@echo "Available commands:"
	@echo "  make venv        - Create virtual environment"
	@echo "  make install     - Install production dependencies"
	@echo "  make install-dev - Install development dependencies"
	@echo "  make clean       - Remove virtual environment and cache files"
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run linters (flake8)"
	@echo "  make format      - Format code (black, isort)"
	@echo "  make check       - Run type checking (mypy)"
	@echo "  make all         - Run all checks (format, lint, type check, test)"

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

install-dev: install
	$(PIP) install -r requirements-dev.txt
	$(VENV_BIN)/pre-commit install

clean:
	rm -rf $(VENV)
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf .tox
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

test:
	$(PYTEST) tests/ -v --cov=. --cov-report=term-missing

lint:
	$(FLAKE8) .

format:
	$(BLACK) .
	$(ISORT) .

check:
	$(MYPY) .

all: format lint check test
