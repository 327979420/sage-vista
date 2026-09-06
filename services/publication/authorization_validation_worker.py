"""Fixed -I bootstrap for the repository's sole authorization validator."""
from pathlib import Path
import sys

# Fixed checkout-relative import root, never PYTHONPATH, cwd or request input.
sys.dont_write_bytecode = True  # Keep the verified checkout unchanged for recovery.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
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
