import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
RULES = ROOT / "docs" / "rules"


class RulebookContractTests(unittest.TestCase):
    def test_overview_has_purpose_and_routes_every_module(self):
        overview = (ROOT / "docs" / "SAGE_VISTA_RULEBOOK_ZH.md").read_text()
        for phrase in (
            "交易知识库",
            "机械化决策助手",
            "选股器",
            "多因子研究系统",
            "有效策略宝典",
            "交易红线",
            "月线 → 周线 → 日线",
        ):
            self.assertIn(phrase, overview)
        for number in range(1, 13):
            self.assertIn(f"rules/{number:02d}_", overview)

    def test_modules_are_independently_versioned_and_routed(self):
        files = sorted(RULES.glob("[0-9][0-9]_*.md"))
        self.assertEqual(len(files), 12)
        for path in files:
            text = path.read_text()
            self.assertIn("版本：`", text, path.name)
            self.assertIn("最后更新：", text, path.name)
            self.assertIn("## 本文件负责", text, path.name)
            self.assertIn("## 变更记录", text, path.name)

    def test_scoring_formula_has_one_module_owner(self):
        owners = []
        for path in RULES.glob("[0-9][0-9]_*.md"):
            if "## 当前技术候选分（current）" in path.read_text():
                owners.append(path.name)
        self.assertEqual(owners, ["04_SCORING.md"])
        overview = (ROOT / "docs" / "SAGE_VISTA_RULEBOOK_ZH.md").read_text()
        self.assertNotIn("长期趋势 `+2`", overview)

    def test_experiments_are_resumable_and_never_discarded(self):
        experiments = (RULES / "08_BACKTEST_AND_EXPERIMENTS.md").read_text()
        for phrase in (
            "中断后从最后成功日期继续",
            "成功、失败、负结果、样本不足和中断都只追加、不删除、不覆盖",
            "research/experiments.jsonl",
            "可以使用 / 候选观察 / 样本不足 / 不稳定 / 不成立",
            "2个代表赢家、2个代表输家和1个边界／反例",
            "post_hoc_hypothesis",
            "案例是人工审计和发现规则漏洞的工具，不是统计证明",
        ):
            self.assertIn(phrase, experiments)

    def test_future_codex_uses_overview_then_exact_module(self):
        instructions = (ROOT / "AGENTS.md").read_text()
        self.assertIn("docs/NEXT_SESSION_HANDOFF_ZH.md", instructions)
        self.assertIn("docs/CURRENT_STATUS_ZH.md", instructions)
        self.assertIn("docs/CHANGE_REQUESTS_ZH.md", instructions)
        self.assertIn("docs/SAGE_VISTA_RULEBOOK_ZH.md", instructions)
        self.assertIn("docs/rules/README.md", instructions)
        self.assertIn("docs/rules/04_SCORING.md", instructions)
        self.assertIn("Do not load every module for a single-module change", instructions)

    def test_documentation_precedes_code_and_fragments_are_preserved(self):
        governance = (RULES / "01_GOVERNANCE.md").read_text()
        for phrase in (
            "这一步必须发生在代码编辑之前",
            "碎片想法标为 `captured`",
            "纯修错、重构或性能优化",
            "测试、提交、网站证据写回需求账本",
        ):
            self.assertIn(phrase, governance)

    def test_framework_review_requires_explicit_approval_before_code(self):
        governance = (RULES / "01_GOVERNANCE.md").read_text()
        workflow = (ROOT / "docs" / "CHANGE_WORKFLOW_ZH.md").read_text()
        instructions = (ROOT / "AGENTS.md").read_text()
        for phrase in (
            "架构评审闸门",
            "design_review",
            "明确批准",
            "不超过20分钟",
            "退回`design_review`",
        ):
            self.assertIn(phrase, governance)
        for phrase in (
            "当前链路",
            "目标接入方式",
            "影响矩阵",
            "明确禁止修改",
            "回退点",
            "范围蔓延",
        ):
            self.assertIn(phrase, workflow)
        self.assertIn("Framework-first approval gate", instructions)
        self.assertIn("wait for explicit user approval", instructions)

    def test_playbook_and_hard_rules_have_evidence_gates(self):
        playbook = (RULES / "11_VALIDATED_PLAYBOOK.md").read_text()
        hard_rules = (RULES / "12_HARD_RULES.md").read_text()
        self.assertIn("当前已验证条目", playbook)
        self.assertIn("**暂无。**", playbook)
        self.assertIn("引用已完成且不可变的实验 ID", playbook)
        self.assertIn("红线优先于机会分数", hard_rules)
        self.assertIn("必须有可追溯证据", hard_rules)


if __name__ == "__main__":
    unittest.main()
