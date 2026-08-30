import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_retired_prototypes_and_starter_assets_are_absent(self):
        retired = (
            "integrations/lean",
            "services/scanner/frameworks.py",
            "services/scanner/run_backtest.py",
            "services/scanner/run_efficiency.py",
            "services/scanner/run_universe.py",
            "services/scanner/sector_watch.py",
            "services/scanner/research_opportunity_pool.py",
            "public/file.svg",
            "public/globe.svg",
            "public/window.svg",
            "public/market-data",
            "public/research-opportunity-pool.json",
            "public/sector-watch.json",
            "public/technical-report.json",
        )
        for relative in retired:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_legacy_research_evidence_is_archived_outside_public(self):
        archive = ROOT / "research/backtest/output/legacy-foundation"
        names = (
            "data-audit.json",
            "eodhd-factor-pilot.json",
            "eodhd-factor-validation.json",
            "market-context-factor-test.json",
            "neutralization-test.json",
            "research-report.json",
        )
        for name in names:
            self.assertTrue((archive / name).is_file(), name)
            self.assertFalse((ROOT / "public" / name).exists(), name)

    def test_core_python_entrypoints_explain_their_role(self):
        entrypoints = (
            "daily_tracker_update.py",
            "factor_snapshot.py",
            "unified_v2_scan.py",
            "industry_radar.py",
            "opportunity_ledger.py",
            "verify_live_deployment.py",
            "project_status.py",
            "discord_daily_digest.py",
        )
        for name in entrypoints:
            source = (ROOT / "services/scanner" / name).read_text()
            docstring = ast.get_docstring(ast.parse(source))
            self.assertIsNotNone(docstring, name)
            self.assertGreaterEqual(len(docstring.split()), 12, name)

    def test_current_discord_variable_uses_sage_vista_name(self):
        workflow = (ROOT / ".github/workflows/daily-eod.yml").read_text()
        digest = (ROOT / "services/scanner/discord_daily_digest.py").read_text()
        self.assertIn("SAGE_VISTA_SITE_URL", workflow)
        self.assertIn("SAGE_VISTA_SITE_URL", digest)
        self.assertNotIn("NORTHSTAR_SITE_URL", workflow)
        self.assertNotIn("NORTHSTAR_SITE_URL", digest)


if __name__ == "__main__":
    unittest.main()
