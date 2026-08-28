import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class OpportunityLedgerWorkflowTests(unittest.TestCase):
    def test_completed_backfill_refreshes_and_publishes_ledger(self):
        text = (ROOT / ".github/workflows/opportunity-ledger-refresh.yml").read_text()
        self.assertIn('workflows: ["Unified V2 Historical Backfill"]', text)
        self.assertIn("python3 -m services.scanner.opportunity_ledger", text)
        self.assertIn("public/opportunity-ledger.json", text)
        self.assertIn("deploy-site.yml", text)


if __name__ == "__main__":
    unittest.main()
