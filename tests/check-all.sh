#!/bin/bash
# Run all code quality checks and tests
# Usage: ./tests/check-all.sh (from project root)
#
# This script runs:
# 1. Pre-commit hooks (linting, formatting, type checking)
# 2. Full pytest test suite with coverage
#
# Recommended to run before pushing to ensure CI will pass.

set -e  # Exit on first error

# Change to project root directory
cd "$(dirname "$0")/.."

ERRORS=0

echo "========================================"
echo "Step 1/2: Running pre-commit checks"
echo "========================================"
echo ""

# Run pre-commit on all files
if pre-commit run --all-files; then
    echo "✅ Pre-commit checks passed"
else
    echo "❌ Pre-commit checks failed"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "========================================"
echo "Step 2/2: Running pytest test suite"
echo "========================================"
echo ""

# Run pytest with coverage
if pytest --cov; then
    echo "✅ Tests passed"
else
    echo "❌ Tests failed"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "========================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed! Safe to push."
else
    echo "❌ $ERRORS check(s) failed"
    echo ""
    echo "To fix formatting issues automatically:"
    echo "  pre-commit run --all-files"
    echo ""
    echo "To run specific checks:"
    echo "  pre-commit run --all-files  # Code quality only"
    echo "  pytest --cov                # Tests only"
fi
echo "========================================"

exit $ERRORS
