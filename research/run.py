"""Non-interactive M10-E command entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from services.contracts.validation import ContractError
from services.evaluation import current_git_state, load_research_run_config
from services.evaluation.orchestration import execute_research_run


def _jsonable(value):
    if hasattr(value, "items"):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m research.run")
    parser.add_argument("--config", required=True)
    arguments = parser.parse_args(argv)
    try:
        config = load_research_run_config(arguments.config)
        execution = execute_research_run(
            config,
            repo_root=Path(__file__).resolve().parents[1],
            git_state_provider=current_git_state,
        )
        print(json.dumps(_jsonable(execution.summary), sort_keys=True, separators=(",", ":")))
        return execution.exit_code
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "error": "keyboard_interrupt"}, sort_keys=True), file=sys.stdout)
        return 130
    except (ContractError, OSError, ValueError) as exc:
        print(f"M10-E: {exc}", file=sys.stderr)
        print(json.dumps({"status": "failed", "error": type(exc).__name__}, sort_keys=True), file=sys.stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
