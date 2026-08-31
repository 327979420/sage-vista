import json
import pathlib
import unittest

from services.scanner import project_status
from services.scanner.unified_v2_scan import MODEL_VERSION as LOCAL_MODEL_VERSION


ROOT = pathlib.Path(__file__).parents[1]


class ProjectStatusTests(unittest.TestCase):
    @staticmethod
    def _line_starting_with(text: str, label: str) -> str:
        for line in text.splitlines():
            if line.startswith(label):
                return line
        raise AssertionError(f"missing status line: {label}")

    def _render_shared(self, website: dict, nightly: dict) -> str:
        self.assertTrue(
            hasattr(project_status, "render_shared_version_status"),
            "shared status renderer is missing",
        )
        return project_status.render_shared_version_status(website, nightly)

    def _render_local(self, website: dict, local: dict) -> str:
        self.assertTrue(
            hasattr(project_status, "render_local_version_diagnostic"),
            "local real-time diagnostic renderer is missing",
        )
        return project_status.render_local_version_diagnostic(website, local)

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

    def test_shared_status_separates_website_and_saved_nightly_identity(self):
        text = self._render_shared(
            {"version": "1.4.0", "commit": "web111"},
            {"version": "1.3.0", "batch_id": "2025-12-29_to_2026-01-01", "commit": None},
        )
        self.assertIn("网站实际版本：1.4.0", text)
        self.assertIn("网站部署提交编号：web111", text)
        self.assertIn("夜间最近已保存批次版本：1.3.0", text)
        self.assertIn("夜间批次编号：2025-12-29_to_2026-01-01", text)
        self.assertIn("夜间运行提交编号：未知", text)
        self.assertNotIn("工作区dirty", text)
        self.assertNotIn("本地HEAD", text)

        multi_version_text = self._render_shared(
            {"version": "1.4.0", "commit": "web111"},
            {"versions": ["1.3.0", "1.4.0"], "batch_id": "mixed-001", "commit": "run111"},
        )
        self.assertIn("夜间最近已保存批次版本：1.3.0、1.4.0", multi_version_text)
        self.assertIn("警告：同一批次包含多个模型版本", multi_version_text)

    def test_committed_shared_report_contains_stable_identity_evidence_only(self):
        text = project_status.build()
        for phrase in (
            "网站实际版本：",
            "网站部署提交编号：",
            "夜间最近已保存批次版本：",
            "夜间批次编号：",
            "夜间运行提交编号：",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("工作区dirty状态：", text)
        self.assertNotIn("本地HEAD：", text)

    def test_nightly_identity_uses_the_saved_batch_not_the_local_model_constant(self):
        backtest = json.loads((ROOT / "automation" / "backtest-state.json").read_text())
        saved_batch = backtest["last_successful_batch"]
        saved_version = saved_batch["model_versions"][0]
        self.assertNotEqual(saved_version, LOCAL_MODEL_VERSION)

        nightly_line = self._line_starting_with(project_status.build(), "- 夜间最近已保存批次版本：")
        batch_line = self._line_starting_with(project_status.build(), "- 夜间批次编号：")
        self.assertIn(saved_version, nightly_line)
        self.assertIn(saved_batch["batch_id"], batch_line)

    def test_shared_status_keeps_missing_website_and_nightly_commits_unknown(self):
        text = self._render_shared(
            {"version": "1.4.0", "commit": None},
            {"version": "1.3.0", "batch_id": "batch-001", "commit": None},
        )
        self.assertIn("网站部署提交编号：未知", text)
        self.assertIn("夜间运行提交编号：未知", text)
        self.assertIn("版本号相同不能自动判断代码相同", text)
        self.assertIn("代码一致性：未知", text)

    def test_shared_status_is_deterministic_when_local_dirty_state_changes(self):
        website = {"version": "1.4.0", "commit": "same111"}
        nightly = {"version": "1.3.0", "batch_id": "batch-001", "commit": None}
        local = {"version": "1.4.0", "head": "same111", "dirty": False}
        clean_text = self._render_shared(website, nightly)
        local["dirty"] = True
        dirty_text = self._render_shared(website, nightly)
        self.assertEqual(clean_text, dirty_text)

    def test_local_diagnostic_rejects_same_version_when_dirty(self):
        text = self._render_local(
            {"version": "1.4.0", "commit": "web111", "verified": True},
            {"version": "1.4.0", "head": "web111", "dirty": True},
        )
        self.assertIn("本地代码声明版本：1.4.0", text)
        self.assertIn("本地HEAD：web111", text)
        self.assertIn("工作区dirty状态：true", text)
        self.assertIn("不能确认代码相同", text)

    def test_local_diagnostic_rejects_same_version_with_different_commits(self):
        text = self._render_local(
            {"version": "1.4.0", "commit": "web111", "verified": True},
            {"version": "1.4.0", "head": "local222", "dirty": False},
        )
        self.assertIn("不能确认代码相同", text)

    def test_local_diagnostic_stays_unknown_when_website_commit_is_missing(self):
        text = self._render_local(
            {"version": "1.4.0", "commit": None, "verified": True},
            {"version": "1.4.0", "head": "local222", "dirty": False},
        )
        self.assertIn("网站部署提交编号：未知", text)
        self.assertIn("代码一致性：未知", text)

    def test_local_diagnostic_confirms_clean_matching_version_and_commit(self):
        text = self._render_local(
            {"version": "1.4.0", "commit": "same111", "verified": True},
            {"version": "1.4.0", "head": "same111", "dirty": False},
        )
        self.assertIn("工作区dirty状态：false", text)
        self.assertIn("代码一致性：是", text)


if __name__ == "__main__":
    unittest.main()
