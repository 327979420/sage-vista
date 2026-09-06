"""Fixed isolated preparation checker, no runtime activation or dispatch."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
runpy.run_path(str(Path(__file__).resolve().with_name('authorization_imports.py')))
from services.contracts.validation import PREPARATION_INPUT_MAX_BYTES
from services.publication.preparation_validation import validate_preparation_input


def main():
    try:
        raw = sys.stdin.buffer.read(PREPARATION_INPUT_MAX_BYTES + 1)
        output = validate_preparation_input(raw)
        if not 0 < len(output) <= 65536:
            return 1
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 1  # Never echo private input, exception or success-shaped fallback.


if __name__ == '__main__':
    raise SystemExit(main())
