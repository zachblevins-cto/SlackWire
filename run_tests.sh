#!/bin/bash
# Test runner script for SlackWire

echo "Running SlackWire Tests..."
echo "========================="

# Run tests with coverage
echo "Running unit tests with coverage..."
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html --cov-config=.coveragerc -m "unit"

# Run integration tests if requested
if [ "$1" == "all" ]; then
    echo ""
    echo "Running integration tests..."
    pytest tests/ -v -m "integration"
fi

# Check if tests passed
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
    echo ""
    echo "Coverage report generated in htmlcov/index.html"
else
    echo ""
    echo "❌ Tests failed!"
    exit 1
fi