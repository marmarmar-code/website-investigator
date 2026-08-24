#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python scripts/check_public_boundary.py
python -m compileall -q src tests
python -m ruff check src tests scripts
python -m pytest --cov=website_investigator --cov-report=term-missing
python scripts/check_workflow_yaml.py .github/workflows
python scripts/check_dependency_licenses.py
python -m build
printf 'Website Investigator checks passed.\n'
