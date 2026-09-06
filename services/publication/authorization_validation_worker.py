"""Fixed -I bootstrap for the repository's sole authorization validator."""
from pathlib import Path
import runpy
import sys

# Only the services namespace is exposed, never the whole checkout or cwd.
sys.dont_write_bytecode = True  # Keep the verified checkout unchanged for recovery.
runpy.run_path(str(Path(__file__).resolve().with_name('authorization_imports.py')))
from services.publication.authorization_process import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
from services.publication.authorization_validation import authorization_validation_output


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if not 0 < len(raw) <= MAX_INPUT_BYTES:
            return 1
        output = authorization_validation_output(raw)
        if not 0 < len(output) <= MAX_OUTPUT_BYTES:
            return 1
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 1  # No private diagnostics or success-shaped fallback.


if __name__ == '__main__':
    raise SystemExit(main())
