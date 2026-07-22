#!/usr/bin/env bash
# Smoke tests runner for the Intelligence Engine + Platform Console.
#
# Usage:
#   ./run_smoke.sh                                  # against local backend (http://localhost:8001)
#   SMOKE_BASE_URL=https://… ./run_smoke.sh        # against any deployed env
#   ./run_smoke.sh -k engine_health                 # filter by test name
#
# Exit code 0 = green deploy. Non-zero = rollback / investigate.

set -e
cd "$(dirname "$0")/.."   # cd into /app/backend
exec python3 -m pytest tests/smoke -v --tb=short "$@"
