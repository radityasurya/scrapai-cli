#!/usr/bin/env bash
#
# Generate requirements.lock for production deployments
#
# This script creates a lockfile with exact versions of all dependencies
# for use in production deployments where reproducibility is critical.
#
# Usage:
#   ./scripts/generate-lockfile.sh
#
# Output:
#   requirements.lock - Exact versions of all installed packages
#

set -e

echo "🔒 Generating requirements.lock for production deployment..."
echo ""

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  WARNING: Not running in a virtual environment"
    echo "   Consider activating venv first: source .venv/bin/activate"
    echo ""
fi

# Install requirements to ensure all dependencies are present
echo "📦 Installing dependencies from requirements.txt..."
pip install -q -r requirements.txt

# Generate lockfile
echo "🔒 Generating lockfile..."
pip freeze > requirements.lock

# Validate lockfile
if [[ -s requirements.lock ]]; then
    PACKAGE_COUNT=$(wc -l < requirements.lock)
    echo "✅ Lockfile generated successfully"
    echo "   File: requirements.lock"
    echo "   Packages: $PACKAGE_COUNT"
    echo ""
    echo "📋 Top 10 packages:"
    head -10 requirements.lock
    echo ""
    echo "💡 Usage in production:"
    echo "   pip install -r requirements.lock"
    echo ""
    echo "⚠️  Note: Do not commit requirements.lock to git"
    echo "   Add to .gitignore if not already present"
else
    echo "❌ Error: Lockfile is empty"
    exit 1
fi
