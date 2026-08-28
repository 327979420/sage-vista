"""Generate the short, repository-first handoff status from canonical state files."""
from __future__ import annotations

import argparse
import json
import pathlib
import re

from .factor_registry import REGISTRY_VERSION
from .unified_v2_scan import MODEL_VERSION


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs" / "CURRENT_STATUS_ZH.md"


def _read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text())


def _ui_version() -> str:
    text = (ROOT / "app" / "layout.tsx").read_text()
    match = re.search(r'const UI_VERSION = "UI v([0-9.]+)"', text)
    if not match:
        raise RuntimeError("UI version is missing from app/layout.tsx")
    return match.group(1)


def _pending_experiments(catalog: dict) -> list[tuple[str, str]]:
    pending = []
    for item in catalog.get("experiments", []):
        if item.get("lifecycle", {}).get("completed_at"):
            continue
        summary = item.get("human_summary", {})
        pending.append((item["experiment_id"], summary.get("title_zh") or item["experiment_id"]))
    return pending


def build() -> str:
    production = _read_json("automation/production-state.json")
    freshness = _read_json("public/update-status.json")
    backtest = _read_json("automation/backtest-state.json")
    registry = _read_json("public/factor-registry.json")
    catalog = _read_json("public/experiment-catalog.json")
    coverage = backtest["coverage"]
    last_batch = backtest["last_successful_batch"]
    next_window = backtest.get("next_window")
    pending = _pending_experiments(catalog)
    pending_lines = "\n".join(f"- `{experiment_id}`：{title}。" for experiment_id, title in pending) or "- 当前没有待运行实验。"
    next_text = f"{next_window['start']} 至 {next_window['end']}" if next_window else "已到目标起点"
    enabled_text = "已开启" if backtest.get("enabled") else "已暂停"
    production_verified = production.get("live_verified") and production.get("as_of") == freshness.get("source_latest_complete_date")
    verified_text = "已核验" if production_verified else "尚未核验或日期不一致"
    return f"""# Sage Vista 当前状态

> 本文件由 `python3 -m services.scanner.project_status` 从机器状态生成；不要手工修改数字。若与下方机器源不一致，先修复生成流程再改业务代码。

## 现在可确认的事实

- 生产网站：<{production['site_url']}>
- 最新完整美股收盘：{freshness['source_latest_complete_date']}；生产状态{verified_text}。
- UI：v{_ui_version()}。
- 因子库：{registry['registry_version']}，共 {registry['factor_count']} 项。
- 当前夜间新批次模型：`{MODEL_VERSION}`；因子注册表代码版本 `{REGISTRY_VERSION}`。
- 数据审计：日期一致 `{str(freshness['data_dates_match']).lower()}`；未来数据 `{str(freshness['future_data_used']).lower()}`。

## 历史回测断点

- 已保存：{coverage['start']} 至 {coverage['end']}，共 {coverage['sessions']} 个交易日。
- 最近成功周：{last_batch['start']} 至 {last_batch['end']}，共 {last_batch['sessions']} 个交易日。
- 下一批：{next_text}。
- 夜间续跑：{enabled_text}；{backtest['schedule']}；成功后才移动断点，失败重试同一周。
- 旧批次冻结原规则版本；新规则只用于后续尚未运行批次。
- 回测状态更新时间：{backtest['updated_at']}。

## 实验

- 总数 {catalog['experiment_count']}；已完成 {catalog['summary']['completed']}；待运行 / 进行中 {catalog['summary']['in_progress']}。
{pending_lines}
- 目前策略宝典仍没有达到完整验证门槛的正式条目；候选结论不能冒充生产胜率。

## 当前工作顺序

1. 保持每日 EOD、永久机会账本和夜间逐周回测稳定运行。
2. 用持续扩展的历史样本完成已预登记的周期评分和独立退出实验。
3. 只有验证通过后才调整正式评分、持仓或退出生产规则。
4. 技术主线稳定后再精进行业、大盘和最终 UI 表达。

## 新对话下一步

1. 先检查 `git status` 和最新 `main` 提交。
2. 根据用户的新要求在 `docs/CHANGE_REQUESTS_ZH.md` 新增或更新一条需求。
3. 用 `docs/rules/README.md` 选择唯一主模块；先改规则文字，再改代码。
4. 未收到新的明确任务时，不自行改变生产评分或重跑旧历史。

## 权威机器源

- `automation/backtest-state.json`
- `automation/production-state.json`
- `public/update-status.json`
- `public/factor-registry.json`
- `public/experiment-catalog.json`

来源时间：生产数据更新 {freshness['last_successful_update_at']}；实验目录生成 {catalog['generated_at']}。
"""


def write(out: pathlib.Path = DEFAULT_OUT) -> str:
    text = build()
    out.write_text(text)
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    print(write(pathlib.Path(args.out)), end="")
