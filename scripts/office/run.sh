#!/usr/bin/env bash
set -eu
OFFICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'BLOCKED: Python 3 not installed; office checks did not run' >&2; exit 1; }
module="${1:?module required}"
shift
case "$module" in bootstrap|adapter|state|privacy_gate|stage_check|update) ;; *) echo 'Unsupported office module' >&2; exit 1 ;; esac
exec python3 "$OFFICE_ROOT/scripts/office/$module.py" "$@"
