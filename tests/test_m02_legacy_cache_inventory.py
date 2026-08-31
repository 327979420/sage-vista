"""Freeze every direct legacy market-cache entry until M12 migrates it."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "services/scanner", ROOT / "research/backtest")
LEGACY_PATH_MARKERS = (
    "work/eodhd-cache",
    "work/eodhd-bulk",
    "work/eodhd-active-common",
    "work/eodhd-panel",
)

# This is an audit inventory, not a production allow-list.  Any source change
# must make the test fail until package H is deliberately reviewed and updated.
EXPECTED_PYTHON_REFERENCES = frozenset({
    "services/scanner/cache_theme_etfs.py::run",
    "services/scanner/eodhd_factor_pilot.py::adjusted_rows",
    "services/scanner/eodhd_factor_validation.py::run",
    "services/scanner/expand_tracker_universe.py::run",
    "services/scanner/factor_snapshot.py::load_symbol_rows",
    "services/scanner/macd_factor_backtest.py::listing_statuses",
    "services/scanner/macd_factor_backtest.py::run",
    "services/scanner/market_context_factor_test.py::run",
    "services/scanner/market_etf_watch.py::refreshed_rows",
    "services/scanner/neutralization_test.py::run",
    "services/scanner/open_source_industry.py::tracked_symbols",
    "services/scanner/opportunity_ledger.py::<module>",
    "services/scanner/rare_opportunity_scanner.py::run",
    "services/scanner/refresh_validation_analysis.py::run",
    "services/scanner/resonance_tracker.py::bulk_day",
    "services/scanner/resonance_tracker.py::run",
    "services/scanner/unified_v2_scan.py::<module>",
    "services/scanner/unified_v2_scan.py::run",
    "research/backtest/annual_factor_summary_v1.py::<module>",
    "research/backtest/factor_attribution_v1.py::<module>",
    "research/backtest/factor_strategy_lab_v2.py::main",
    "research/backtest/full_line_backtest_v1.py::<module>",
    "research/backtest/market_regime_v1.py::<module>",
    "research/backtest/market_regime_v1.py::run",
    "research/backtest/pullback_context_backtest_v2.py::etf_pullback_events",
    "research/backtest/pullback_context_backtest_v2.py::run",
    "research/backtest/pullback_context_backtest_v2.py::stock_context_trades",
    "research/backtest/ranking_research_v1.py::<module>",
    "research/backtest/ranking_research_v1.py::run",
    "research/backtest/reused_event_study_v2.py::main",
    "research/backtest/selection_research_v1.py::<module>",
    "research/backtest/tracker_backtest_v1.py::<module>",
    "research/backtest/tracker_backtest_v1.py::run",
    "research/backtest/tracker_backtest_v2.py::<module>",
    "research/backtest/trailing_stop_v1.py::<module>",
    "research/backtest/winner_loser_optimization_v1.py::main",
})

EXPECTED_WORKFLOW_REFERENCES = frozenset({
    ".github/workflows/choppiness-state-mechanism-v1.yml",
    ".github/workflows/core-factor-backtest.yml",
    ".github/workflows/daily-eod.yml",
    ".github/workflows/factor-strategy-lab-v2.yml",
    ".github/workflows/full-line-backtest.yml",
    ".github/workflows/industry-radar-validation.yml",
    ".github/workflows/nightly-backtest.yml",
    ".github/workflows/opportunity-ledger-refresh.yml",
    ".github/workflows/pullback-context-backtest.yml",
    ".github/workflows/recover-unified-v2-backfill.yml",
    ".github/workflows/reused-factor-backtest.yml",
    ".github/workflows/trailing-stop-backtest.yml",
    ".github/workflows/unified-v2-backfill.yml",
    ".github/workflows/winner-loser-strategy-optimization.yml",
})


def _has_legacy_path(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Constant)
        and isinstance(item.value, str)
        and any(marker in item.value for marker in LEGACY_PATH_MARKERS)
        for item in ast.walk(node)
    )


def _python_files() -> list[Path]:
    return sorted(path for root in SOURCE_ROOTS for path in root.glob("*.py"))


def _legacy_constant_exports(files: list[Path]) -> set[tuple[str, str]]:
    exports: set[tuple[str, str]] = set()
    for path in files:
        tree = ast.parse(path.read_text())
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not _has_legacy_path(node):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    exports.add((module, target.id))
    return exports


class _ReferenceVisitor(ast.NodeVisitor):
    def __init__(self, imported_aliases: set[str]):
        self.imported_aliases = imported_aliases
        self.functions: list[str] = []
        self.references: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _owner(self) -> str:
        return self.functions[-1] if self.functions else "<module>"

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and any(
            marker in node.value for marker in LEGACY_PATH_MARKERS
        ):
            self.references.add(self._owner())

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.imported_aliases:
            self.references.add(self._owner())


def discover_python_references() -> frozenset[str]:
    files = _python_files()
    exports = _legacy_constant_exports(files)
    references: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text())
        imported_aliases: set[str] = set()
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for name in node.names:
                if (node.module, name.name) in exports:
                    imported_aliases.add(name.asname or name.name)
        visitor = _ReferenceVisitor(imported_aliases)
        visitor.visit(tree)
        relative = path.relative_to(ROOT).as_posix()
        references.update(f"{relative}::{owner}" for owner in visitor.references)
    return frozenset(references)


def discover_workflow_references() -> frozenset[str]:
    return frozenset(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / ".github/workflows").glob("*.yml"))
        if any(marker in path.read_text() for marker in LEGACY_PATH_MARKERS)
    )


class LegacyCacheInventoryTests(unittest.TestCase):
    def test_python_legacy_cache_references_match_reviewed_inventory(self):
        self.assertSetEqual(discover_python_references(), EXPECTED_PYTHON_REFERENCES)

    def test_workflow_legacy_cache_references_match_reviewed_inventory(self):
        self.assertSetEqual(discover_workflow_references(), EXPECTED_WORKFLOW_REFERENCES)


if __name__ == "__main__":
    unittest.main()
