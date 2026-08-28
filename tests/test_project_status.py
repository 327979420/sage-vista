import pathlib
import unittest

from services.scanner import project_status


ROOT = pathlib.Path(__file__).parents[1]


class ProjectStatusTests(unittest.TestCase):
    def test_committed_status_matches_canonical_machine_state(self):
        self.assertEqual((ROOT / "docs" / "CURRENT_STATUS_ZH.md").read_text(), project_status.build())

    def test_new_conversation_entry_is_current_and_safe(self):
        handoff = (ROOT / "docs" / "NEXT_SESSION_HANDOFF_ZH.md").read_text()
        for phrase in (
            "CURRENT_STATUS_ZH.md",
            "CHANGE_REQUESTS_ZH.md",
            "先更新需求账本和对应规则文字，再改代码",
            "旧聊天",
            "排行榜是唯一权威顺序",
        ):
            self.assertIn(phrase, handoff)
        self.assertNotIn("/Users/xianpeil/Documents/Codex", handoff)
        self.assertNotIn("当前固定六因子", handoff)

    def test_change_ledger_defines_documentation_first_lifecycle(self):
        ledger = (ROOT / "docs" / "CHANGE_REQUESTS_ZH.md").read_text()
        for phrase in ("captured", "approved", "experimental", "implemented", "规则先行", "生产链接"):
            self.assertIn(phrase, ledger)


if __name__ == "__main__":
    unittest.main()
