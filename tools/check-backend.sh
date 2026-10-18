#!/bin/sh
set -eu
cd "$(dirname "$0")/../apps/backend"
uv sync --locked
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked ruff check ../../tools/backend-local-config.py ../../tools/auth-local-config.py ../../tools/export-backend-openapi.py ../../tools/export-database-diagram.py ../../tools/smoke-backend.py
uv run --locked ruff format --check ../../tools/backend-local-config.py ../../tools/auth-local-config.py ../../tools/export-backend-openapi.py ../../tools/export-database-diagram.py ../../tools/smoke-backend.py
uv run --locked mypy
uv run --locked python ../../tools/export-backend-openapi.py --check
uv run --locked python ../../tools/export-database-diagram.py --check
# Integration tests fail if an explicit disposable test URL is absent; they never silently skip.
uv run --locked pytest
