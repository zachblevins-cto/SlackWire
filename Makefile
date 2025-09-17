.PHONY: help install install-dev update-deps compile-deps test lint format clean

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make update-deps   - Update and compile all dependencies"
	@echo "  make compile-deps  - Compile requirements files from .in files"
	@echo "  make test          - Run unit tests"
	@echo "  make test-all      - Run all tests including integration"
	@echo "  make lint          - Run linting checks"
	@echo "  make format        - Format code with black"
	@echo "  make clean         - Clean up generated files"

install:
	pip install --upgrade pip
	pip install pip-tools
	pip-sync requirements.txt

install-dev:
	pip install --upgrade pip
	pip install pip-tools
	pip-sync requirements.txt requirements-dev.txt

update-deps:
	pip install --upgrade pip-tools
	pip-compile --upgrade requirements.in
	pip-compile --upgrade requirements-dev.in

compile-deps:
	pip-compile requirements.in
	pip-compile requirements-dev.in

test:
	./run_tests.sh

test-all:
	./run_tests.sh all

lint:
	flake8 . --exclude=venv,__pycache__,htmlcov,.git --max-line-length=120
	mypy . --ignore-missing-imports

format:
	black . --exclude=venv

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/