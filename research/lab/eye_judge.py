"""Task038: offline training exports and frozen-1.9 forward eye scorecard."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
from research.lab import forward_judge as J

ROOT = Path(__file__).resolve().parents[2]
KEYS = {'daily1': 'work/v3w/daily1-keys.json', 'mixed1': 'work/v3w/mixed035/mixed1-keys.json',
        'hk1': 'work/v3w/hk039/hk1-keys.json'}


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def timestamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('时间必须有时区')
    return t


def describe(rows):
    groups = {c: [r['net_R'] for r in rows if r['choice'] == c] for c in ('do', 'no')}
    a, b = J.mean(groups['do']), J.mean(groups['no'])
    return {'n': len(rows), 'do_n': len(groups['do']), 'no_n': len(groups['no']),
            'mean_net_R': J.mean([r['net_R'] for r in rows]), 'do_mean': a, 'no_mean': b,
            'difference': a-b if a is not None and b is not None else None}


def eye_stats(rows, pooled=False):
    out = describe(rows)
    samples = []
    if out['do_n'] and out['no_n']:
        rng = random.Random(20261019)
        for _ in range(10000):
            draw = [rows[rng.randrange(len(rows))] for _ in rows]
            d = describe(draw)['difference']
            if d is not None:
                samples.append(d)
    # A resample with an empty group has no defined difference; count it explicitly.
    def quantile(xs, p):
        z = (len(xs)-1)*p
        i = int(z)
        return xs[i] + (xs[min(i+1, len(xs)-1)]-xs[i])*(z-i)
    samples.sort()
    ci = [quantile(samples, p) for p in (.025, .975)] if samples else None
    verdict = '样本太少，仅供参考' if len(rows) < 100 else '仅描述'
    if pooled and len(rows) >= 100:
        verdict = '未证明'
        if ci and out['difference'] >= .3 and ci[0] > 0:
            verdict = '眼光有用'
        elif ci and out['difference'] <= -.3 and ci[1] < 0:
            verdict = '眼光有害'
    return {**out, 'ci95': ci, 'bootstrap_valid': len(samples),
            'bootstrap_undefined': 10000-len(samples) if out['difference'] is not None else None,
            'verdict': verdict}


def load_bank(bank, answer_path, key_path):
    raw = key_path.read_bytes()
    keys = json.loads(raw)['cases']
    by = {r['id']: r for r in keys}
    if len(by) != len(keys):
        raise ValueError('重复题号')
    if answer_path is None:
        answers = {}
    elif answer_path.is_dir():
        answers = {p.stem: json.loads(p.read_text()) for p in sorted(answer_path.glob('*.json'))}
    else:
        doc = json.loads(answer_path.read_text())
        if doc.get('collection', bank) != bank:
            raise ValueError('题库不匹配')
        if doc.get('keys_sha256', hashlib.sha256(raw).hexdigest()) != hashlib.sha256(raw).hexdigest():
            raise ValueError('键哈希不匹配')
        answers = doc.get('answers', doc)
    for rid, a in answers.items():
        if rid not in by or a.get('choice') not in ('do', 'no'):
            raise ValueError(f'{bank}/{rid}: 未知题号或缺choice，STOP')
        timestamp(a.get('answered_at', ''))
    # Exactly the page's answer-order tie break, not key order.
    ordered = sorted(answers, key=lambda rid: (answers[rid]['answered_at'], rid))
    n = len(ordered)//10*10
    if bank == 'hk1' and len(ordered) == len(keys):
        n = len(ordered)
    for k in keys:
        r = k.get('net_R', k.get('trade', {}).get('net_R'))
        if not finite(r):
            raise ValueError(f'{bank}/{k["id"]}: 键缺净R，STOP；禁止重算')
        if 'net_R' in k and 'net_R' in k.get('trade', {}) and k['net_R'] != k['trade']['net_R']:
            raise ValueError('键的两份净R不一致')
    rows = [{'id': rid, 'bank': bank, 'choice': answers[rid]['choice'],
             'net_R': by[rid].get('net_R', by[rid].get('trade', {}).get('net_R')),
             'period': by[rid].get('period', 'day')} for rid in ordered[:n]]
    result = {**eye_stats(rows), 'answered': len(answers), 'revealed': n,
              'unanswered': len(keys)-len(answers), 'unrevealed_answered': len(answers)-n,
              'excluded': len(keys)-n, 'keys_sha256': hashlib.sha256(raw).hexdigest(), 'rows': rows}
    if bank == 'mixed1':
        result['periods'] = {p: eye_stats([r for r in rows if r['period'] == p]) for p in ('day', 'week', 'month')}
    return result


def forward_eye(rows, judgements):
    by = {}
    for j in judgements:
        if j['id'] in by or j.get('choice') not in ('do', 'no'):
            raise ValueError('前向答案重复或缺choice')
        by[j['id']] = j
    unknown = set(by)-{r['id'] for r in rows}
    if unknown:
        raise ValueError('前向答案含未知信号')
    decorated = []
    for row in rows:
        j = by.get(row['id'])
        choice = None
        if j:
            at = timestamp(j['judged_at'])
            fill = (row.get('trade') or {}).get('fill_date')
            # Require pre-fill evidence. Legacy same-day/late answers remain visible but not blind.
            if fill and not j.get('judged_after_fill'):
                from zoneinfo import ZoneInfo
                opened = datetime.fromisoformat(fill+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York'))
                if at < opened:
                    choice = j['choice']
        decorated.append({**row, 'choice': choice})
    def checkpoint(done, paper):
        do = [r for r in done if r['choice'] == 'do']
        scored = [r for r in do if r['scored']]
        avg, t = J.paired_stats(scored)
        pause = bool(do and (len(do)-len(scored))/len(do) > .1)
        valid = [{'choice': r['choice'], 'net_R': r['trade']['net_R']} for r in done
                 if r['choice'] and r.get('trade') and finite(r['trade'].get('net_R'))]
        return {'k': len(done), 'scored': len(scored), 'unscorable': len(do)-len(scored),
                'do_completed': len(do), 'mean_d': avg, 't': t, 'alarm1': False,
                'verdict': '暂停判断（对照不足）' if pause else
                '有用' if len(done) >= 100 and t is not None and t >= 2 else '继续记录，未证明',
                'do_no': describe(valid)}
    report = J.score(decorated, checkpoint_judge=checkpoint)
    report['judgements'] = len(by)
    report['blind_eligible'] = sum(bool(r['choice']) for r in decorated)
    report['excluded_judgements'] = len(by)-report['blind_eligible']
    report['basis'] = '冻结1.9合格已结束交易的Task036检查点；t为盲判do组净R减孪生净R；同日须有开盘前时间证据'
    report['current'] = checkpoint([r for r in decorated if r['eligible'] and r['completed']], {})
    report['current']['verdict'] = '仅描述（非检查点结论）'
    return report


def forward_rows(outcome_path, judgement_path):
    frozen = json.loads(outcome_path.read_text())
    records_path = outcome_path.with_name('signals.jsonl')
    records = [json.loads(x) for x in records_path.read_text().splitlines() if x.strip()] if records_path.exists() else []
    if frozen['outcomes'] and not records:
        raise ValueError('前向有结果但无signals，STOP')
    config = json.loads(J.F.CONFIG.read_text())
    rows = []
    for ds in config['datasets']:
        recs = [r for r in records if r['dataset'] == ds]
        if recs:
            px = J.cached_prices(ds, config, frozen['computed_at'][:10])
            rs = J.recompute(px, recs, frozen['outcomes'], config)
            for r in rs:
                g = r.get('trade')
                rec = next(x for x in recs if x['id'] == r['id'])
                if g and 'fill_day' in g:
                    g['fill_date'] = px[rec['symbol']]['date'][g['fill_day']]
            rows.extend(rs)
    if len(rows) != len(records):
        raise ValueError('未知前向数据集')
    js = [json.loads(x) for x in judgement_path.read_text().splitlines() if x.strip()] if judgement_path.exists() else []
    return rows, js


def show(x):
    if x is None:
        return '不可计算'
    if isinstance(x, list):
        return '['+', '.join(show(y) for y in x)+']'
    return f'{x:.4f}' if isinstance(x, float) else str(x)


def markdown(report):
    lines = ['合计：'+report['pooled']['verdict'], '',
             '| 题库 | 已揭晓 | 做/不做 | 全部平均净R | 做平均 | 不做平均 | 做−不做 | 95% CI | 标签 |',
             '|---|---:|---:|---:|---:|---:|---:|---|---|']
    for bank, r in [*report['banks'].items(), ('合计', report['pooled'])]:
        vals = [bank, r['n'], f"{r['do_n']}/{r['no_n']}", r['mean_net_R'], r['do_mean'], r['no_mean'], r['difference'], r['ci95'], r['verdict']]
        lines.append('| '+' | '.join(show(x) for x in vals)+' |')
    for bank, r in report['banks'].items():
        lines.append(f"- {bank}：未答 {r['unanswered']}；已答未揭晓 {r['unrevealed_answered']}；排除 {r['excluded']}。")
    lines += ['', 'mixed1周期分格（仅描述）：']
    for p, r in report['banks']['mixed1']['periods'].items():
        lines.append(f"- {p}：{r['n']}题；做/不做 {r['do_n']}/{r['no_n']}；差 {show(r['difference'])}R；CI {show(r['ci95'])}。")
    f = report['forward']
    lines += ['', f"前向盲判：{f['completed']}笔；{f['verdict']}；下一检查点 {f['next_checkpoint']}。", f['basis']]
    current = f['current']
    lines.append(f"当前描述：做/不做 {current['do_no']['do_n']}/{current['do_no']['no_n']}；do−no {show(current['do_no']['difference'])}R；do对孪生 {show(current['mean_d'])}R；t {show(current['t'])}。")
    for cp in f['checkpoints']:
        lines.append(f"- k={cp['k']}：do−no {show(cp['do_no']['difference'])}R；do对孪生 {show(cp['mean_d'])}R，t={show(cp['t'])}；{cp['verdict']}。")
    lines += ['', '方法：按题（选择和净R成对）重抽10000次，种子20261019；百分位区间采用线性插值。空组重抽无定义，不补抽，数量保留在JSON。',
              'Concerns：小样本、同市场/时期相关性、三库组成差异；训练只描述个人眼光，不证明3W有效，不改冻结规则。',
              '前向判断需要作答时间早于成交开盘；缺时间或晚答不作为盲判证据。已实现，尚未接入Actions正式计分。']
    return '\n'.join(lines)+'\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for bank in KEYS:
        p.add_argument('--'+bank, type=Path)
        p.add_argument('--'+bank+'-keys', type=Path, default=ROOT/KEYS[bank])
    p.add_argument('--outcomes', type=Path, default=ROOT/'research/lab/forward/triangle/outcomes.json')
    p.add_argument('--judgements', type=Path, default=ROOT/'research/lab/forward/triangle/judgements.jsonl')
    p.add_argument('--out', type=Path, default=ROOT/'work/eye-judge')
    a = p.parse_args(argv)
    banks = {b: load_bank(b, getattr(a, b), getattr(a, b+'_keys')) for b in KEYS}
    rows = [r for b in banks.values() for r in b['rows']]
    report = {'banks': banks, 'pooled': eye_stats(rows, pooled=True),
              'forward': forward_eye(*forward_rows(a.outcomes, a.judgements))}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (a.out/'latest.md').write_text(markdown(report))
    print(markdown(report))


if __name__ == '__main__':
    main()
