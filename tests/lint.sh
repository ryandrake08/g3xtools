#!/bin/bash
# Run all linting and type checking
# Usage: ./tests/lint.sh (from project root)

# Change to project root directory
cd "$(dirname "$0")/.."

ERRORS=0

echo "========================================"
echo "Running ruff (linting)..."
echo "========================================"
ruff check . || ERRORS=$((ERRORS + 1))

echo ""
echo "========================================"
echo "Running mypy (type checking)..."
echo "========================================"
# Check main modules with type hints
mypy *.py tests/*.py || ERRORS=$((ERRORS + 1))

echo ""
echo "========================================"
echo "Running vermin (Python 3.9+ compatibility)..."
echo "========================================"
vermin --target=3.9 --violations --eval-annotations --backport argparse --backport dataclasses --backport enum --backport typing --no-parse-comments *.py tests/*.py || ERRORS=$((ERRORS + 1))

echo ""
echo "========================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed!"
else
    echo "❌ $ERRORS check(s) failed"
    exit 1
fi
echo "========================================"
