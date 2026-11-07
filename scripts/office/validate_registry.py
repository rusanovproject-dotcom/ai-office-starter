"""Read-only compatibility entry point for registry validation."""
from common import ROOT
from registry import validate_registry

if __name__ == '__main__':
    try:
        validate_registry(ROOT)
        print('registry=ok')
    except (ValueError, OSError) as exc:
        raise SystemExit('registry=fail: ' + str(exc))
