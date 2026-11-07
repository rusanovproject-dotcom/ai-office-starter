#!/usr/bin/env bash
set -eu
OFFICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$OFFICE_ROOT/scripts/office/run.sh" bootstrap
