"""Regenerate the human handoff from canonical machine state.

This is the only writer for ``docs/CURRENT_STATUS_ZH.md``. It reads production,
backtest, factor and experiment state so new sessions never copy stale dates or
versions from chat history.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

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


def _shown(value: object) -> str:
    """Render absent identity evidence without guessing a replacement."""
    return str(value) if value not in (None, "", []) else "未知"


def render_shared_version_status(website: dict, nightly: dict) -> str:
    """Render stable deployment and saved-batch evidence for the shared file.

    The caller supplies canonical machine-state dictionaries. This renderer is
    deliberately unaware of Git HEAD and the working tree, so regenerating the
    committed status file cannot change merely because local files are dirty.
    """
    versions = nightly.get("versions")
    if versions is None:
        version = nightly.get("version")
        versions = [] if version in (None, "") else [version]
    versions = list(dict.fromkeys(str(item) for item in versions if item not in (None, "")))
    nightly_version = "、".join(versions) if versions else "未知"
    version_warning = "；警告：同一批次包含多个模型版本" if len(versions) > 1 else ""
    return "\n".join(
        (
            "## 版本与代码身份",
            "",
            f"- 网站实际版本：{_shown(website.get('version'))}",
            f"- 网站部署提交编号：{_shown(website.get('commit'))}",
            f"- 夜间最近已保存批次版本：{nightly_version}{version_warning}",
            f"- 夜间批次编号：{_shown(nightly.get('batch_id'))}",
            f"- 夜间运行提交编号：{_shown(nightly.get('commit'))}",
            "- 版本号相同不能自动判断代码相同。",
            "- 代码一致性：未知（共享状态不读取本地实时证据）。",
        )
    )


def render_local_version_diagnostic(website: dict, local: dict) -> str:
    """Explain injected local Git evidence without collecting it here."""
    website_version = website.get("version")
    website_commit = website.get("commit")
    local_version = local.get("version")
    local_head = local.get("head")
    dirty = local.get("dirty")
    if dirty is True:
        dirty_text = "true"
    elif dirty is False:
        dirty_text = "false"
    else:
        dirty_text = "未知"

    evidence_complete = (
        website.get("verified") is True
        and website_version not in (None, "")
        and website_commit not in (None, "")
        and local_version not in (None, "")
        and local_head not in (None, "")
        and dirty is not None
    )
    if not evidence_complete:
        equality = "未知"
    elif website_version == local_version and website_commit == local_head and dirty is False:
        equality = "是"
    else:
        equality = "不能确认代码相同"

    return "\n".join(
        (
            f"- 网站实际版本：{_shown(website_version)}",
            f"- 网站部署提交编号：{_shown(website_commit)}",
            f"- 本地代码声明版本：{_shown(local_version)}",
            f"- 本地HEAD：{_shown(local_head)}",
            f"- 工作区dirty状态：{dirty_text}",
            f"- 代码一致性：{equality}",
        )
    )


def build() -> str:
    production = _read_json("automation/production-state.json")
    freshness = _read_json("public/update-status.json")
    backtest = _read_json("automation/backtest-state.json")
    registry = _read_json("public/factor-registry.json")
    catalog = _read_json("research/generated/experiment-catalog.json")
    coverage = backtest["coverage"]
    last_batch = backtest["last_successful_batch"]
    next_window = backtest.get("next_window")
    pending = _pending_experiments(catalog)
    pending_lines = "\n".join(f"- `{experiment_id}`：{title}。" for experiment_id, title in pending) or "- 当前没有待运行实验。"
    next_text = f"{next_window['start']} 至 {next_window['end']}" if next_window else "已到目标起点"
    enabled_text = "已开启" if backtest.get("enabled") else "已暂停"
    production_verified = production.get("live_verified") and production.get("as_of") == freshness.get("source_latest_complete_date")
    verified_text = "已核验" if production_verified else "尚未核验或日期不一致"
    website_identity = {
        "version": production.get("website_version"),
        "commit": production.get("deployment_commit"),
        "verified": production_verified,
    }
    nightly_identity = {
        "versions": last_batch.get("model_versions", []),
        "batch_id": last_batch.get("batch_id"),
        "commit": last_batch.get("run_commit"),
    }
    shared_version_status = render_shared_version_status(website_identity, nightly_identity)
    return f"""# Sage Vista 当前状态

> 本文件由 `python3 -m services.scanner.project_status` 从机器状态生成；不要手工修改数字。若与下方机器源不一致，先修复生成流程再改业务代码。

## 现在可确认的事实

- 生产网站：<{production['site_url']}>
- 最新完整美股收盘：{freshness['source_latest_complete_date']}；生产状态{verified_text}。
- UI：v{_ui_version()}。
- 因子库：{registry['registry_version']}，共 {registry['factor_count']} 项。
- 数据审计：日期一致 `{str(freshness['data_dates_match']).lower()}`；未来数据 `{str(freshness['future_data_used']).lower()}`。

{shared_version_status}

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
- `research/generated/experiment-catalog.json`

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
