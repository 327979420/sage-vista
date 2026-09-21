"""Small Chinese visual calibration report; no new website or trading interface."""
import csv
from html import escape
from pathlib import Path


def chart(row):
    bars = row.get('chart')
    if not bars: return '<p>未生成图：此项未进入重点核图范围。</p>'
    width, height = 1120, 380
    low = min(b['low'] for b in bars); high = max(b['high'] for b in bars)
    zone = row['bottom']; line = row.get('three_push')
    low = min(low, zone.get('zone_lower', low)); high = max(high, zone.get('zone_upper', high))
    spread = max(high-low, .01); low -= spread*.08; high += spread*.14
    x = lambda i: 65+i/(len(bars)-1)*(width-100)
    y = lambda value: 22+(high-value)/(high-low)*(height-65)
    ids = {b['date']: i for i, b in enumerate(bars)}
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(row["symbol"])}日线形态标注图">']
    for step in range(5):
        value = low+(high-low)*step/4
        parts.append(f'<line x1="60" x2="1090" y1="{y(value)}" y2="{y(value)}" stroke="#e2e8f0"/><text x="5" y="{y(value)+4}">{value:.2f}</text>')
    if zone.get('zone_lower') is not None:
        parts.append(f'<rect x="60" y="{y(zone["zone_upper"])}" width="1030" height="{y(zone["zone_lower"])-y(zone["zone_upper"])}" fill="#d1fae5" opacity=".65"/>')
        parts.append(f'<text x="1080" y="{y(zone["zone_lower"])+15}" text-anchor="end">支撑区下沿 ${zone["zone_lower"]:.2f}</text>')
    for i, bar in enumerate(bars):
        color = '#047857' if bar['close'] >= bar['open'] else '#dc2626'
        parts.append(f'<line x1="{x(i)}" x2="{x(i)}" y1="{y(bar["high"])}" y2="{y(bar["low"])}" stroke="{color}"/>')
        parts.append(f'<rect x="{x(i)-2.5}" y="{min(y(bar["open"]),y(bar["close"]))}" width="5" height="{max(1,abs(y(bar["open"])-y(bar["close"])))}" fill="{color}"/>')
    if line:
        first = line['anchors'][0]
        parts.append(f'<line x1="{x(ids[first["date"]])}" y1="{y(first["price"])}" x2="{x(len(bars)-1)}" y2="{y(line["level"])}" stroke="#7c3aed" stroke-width="2"/>')
    for group, anchors in [('底', zone['anchors']), ('推', line['anchors'] if line else [])]:
        for n, anchor in enumerate(anchors, 1):
            px, py = x(ids[anchor['date']]), y(anchor['price'])
            parts.append(f'<circle cx="{px}" cy="{py}" r="5" fill="#1d4ed8"/><text x="{px}" y="{py+(20 if group=="底" else -12)}" text-anchor="middle">{group}{n}</text>')
            confirmed = ids.get(anchor['confirmed_at'])
            if confirmed is not None and group == '底':
                parts.append(f'<path d="M {x(confirmed)-4} {py-10} l 4 -6 l 4 6 Z" fill="#b45309"/>')
    parts.append(f'<text x="65" y="375">{bars[0]["date"]}</text><text x="1080" y="375" text-anchor="end">{bars[-1]["date"]}</text></svg>')
    return ''.join(parts)


def card(row, teaching=False):
    symbol = escape(row['symbol'])
    if row.get('unavailable'):
        return f'<article data-search="{symbol.lower()}" data-group="teaching"><h2>{symbol} · 教学案例</h2><p>当前核对行情不足，未伪造识别结果。</p></article>'
    group = 'teaching' if teaching else 'selected' if row['selected'] else 'excluded'
    old = row['old']; heat = row['liquidity']
    bottom_details = ''.join(f'<tr><td>底{i}</td><td>{escape(a["date"])}</td><td>{escape(a["confirmed_at"])}</td><td>${a["price"]:.2f}</td></tr>' for i, a in enumerate(row['bottom']['anchors'], 1))
    line = row.get('three_push')
    anchor_text = '；'.join(f'{a["date"]}（确认 {a["confirmed_at"]}）${a["price"]:.2f}' for a in line['anchors']) if line else '无合格三推，不显示三推标签'
    rank = f'交易热度 #{row["activity_rank"]}' if 'activity_rank' in row else '教学案例：与当前热门榜分开'
    return f'''<article data-search="{symbol.lower()}" data-group="{group}">
<header><div><small>{rank}</small><h2>{symbol} · {escape(row['shape_zh'])}</h2></div><b class="badge">{escape(row['state_zh'])}</b></header>
<p>{escape(row['explanation_zh'])}</p><p class="muted">当日成交额 ${heat['dollar_volume']/1e6:,.1f}百万 · 收盘 ${row['price']:.2f}</p>
<p><b>旧版：</b>{escape(old.get('stage_zh') or '未知')}（{old.get('match_count',0)}/4） → <b>新版：</b>{escape(row['state_zh'])}。{escape(row['comparison_zh'])}。</p>
{chart(row)}<p class="muted">绿底色＝支撑区；紫线＝三推下降线；蓝点＝已确认转折；棕三角＝底部确认日。图使用同一版复权日K。</p>
<details><summary>查看底部日期和识别依据</summary><table><thead><tr><th>底部</th><th>发生日</th><th>确认日</th><th>价格</th></tr></thead><tbody>{bottom_details or '<tr><td colspan="4">没有通过共享底部确认</td></tr>'}</tbody></table><p>三推锚点：{escape(anchor_text)}</p><p>底部确认只说明已有后续K线支持该低点；以后仍可能跌破。已突破标签按当前结构的历史收盘证据核对。</p><small>图与事实窗口：{escape(row['window_fingerprint'])}</small></details></article>'''


def write_report(report, out):
    out = Path(out)
    rows = report['rows']; selected = [r for r in rows if r['selected']]
    differences = [r for r in rows if not r['selected'] and r['old'].get('bottom')]
    with (out/'逐股对照.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['股票','成交额排序','当日成交额美元','旧版状态','旧版条件数','新版状态','形态','底部确认','底部确认日','支撑区下沿','对照说明'])
        for row in rows:
            writer.writerow([row['symbol'],row['activity_rank'],row['liquidity']['dollar_volume'],row['old'].get('stage_zh'),row['old'].get('match_count'),row['state_zh'],row['shape_zh'],row['bottom_confirmed'],row['bottom'].get('confirmed_at'),row['invalidation_price'],row['comparison_zh']])
    overview = f"从已覆盖的{report['universe']['eligible_covered_count']}只合格普通股中，核对成交额前{len(rows)}只：{len(selected)}只底部通过确认。"
    note = '这是固定日期的识别校准，不是今日实时名单。自动检查通过不代表形态准确率已由人工确认；旧版与新版不同，也不自动表示新版正确。'
    body = ''.join(card(r) for r in selected+differences)+''.join(card(r, True) for r in report['teaching_cases'])
    html = '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>热门股 · 日线 · 形态</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:#172b40;font:16px/1.7 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:30px 24px}h1{font-size:34px;margin:4px 0}h2{font-size:22px;margin:4px 0}header{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}article{padding:25px;background:white;border:1px solid #dce4eb;border-radius:14px;margin:20px 0}.badge{background:#e7eefc;border-radius:7px;padding:6px 12px;font-size:14px}.muted,small{color:#607488}svg{width:100%;height:auto}svg text{font:12px system-ui;fill:#405367}table{width:100%;text-align:left;border-collapse:collapse}td,th{border-bottom:1px solid #e2e8f0;padding:8px}input,select{font:inherit;padding:10px;border:1px solid #bac7d3;border-radius:7px;max-width:100%}.notice{background:#fff5d8;padding:14px;border-radius:9px}details{overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}@media(max-width:600px){main{padding:16px 10px}article{padding:14px}h1{font-size:27px}}
</style><main>'''
    html += f'<small>SAGE VISTA · 识别校准 · {report["as_of"]}</small><h1>热门股 · 日线 · 形态</h1><p>{overview}</p><p>先确认底部，再观察三推回调等结构。没有突破也可以入选。</p><div class="notice">{note}</div><p><label>找股票 <input id="search" placeholder="例如 AAPL" aria-label="按股票代码搜索"></label> <label>查看 <select id="group"><option value="selected">底部已确认</option><option value="excluded">旧版有底、新版未通过</option><option value="teaching">教学案例</option><option value="all">全部核图案例</option></select></label></p><p id="count" aria-live="polite"></p>'
    html += body + '<p>完整100股状态见同目录“逐股对照.csv”；页面只画入选、分歧和教学案例，避免下载无关股票的历史详情。</p></main>'
    html += '''<script>const search=document.querySelector('#search'),group=document.querySelector('#group');function filter(){let n=0;document.querySelectorAll('article').forEach(a=>{const show=a.dataset.search.includes(search.value.trim().toLowerCase())&&(group.value==='all'||a.dataset.group===group.value);a.hidden=!show;if(show)n++});document.querySelector('#count').textContent=n?'显示 '+n+' 个核图案例':'此范围没有匹配案例。'}search.addEventListener('input',filter);group.addEventListener('change',filter);filter();</script></html>'''
    (out/'形态核对.html').write_text(html)
    lines = ['# 热门股 · 日线 · 形态：本轮校准', '', f'行情日期：{report["as_of"]}。', '', overview, '', note, '', '| 股票 | 新版识别 | 当前状态 | 旧版状态 |', '|---|---|---|---|']
    lines += [f'| {r["symbol"]} | {r["shape_zh"]} | {r["state_zh"]} | {r["old"]["stage_zh"]} |' for r in selected]
    lines += ['', '## 本轮能确认什么', '', '- 已共用主功能的日线底部与三推算法；底部未确认不能靠凑条件入选。', '- 三推是否存在与是否突破分开记录；没有三推只显示多底支撑。', '- 热度使用未复权收盘价×成交量；不会把拆股/复权价格变动当成交易热度。', '- 这里是已有缓存覆盖内的热门排序，不是全市场或社交热度榜。', '- 教学案例按本次行情日重算，并非用户历史截图已经精确复现。', '- 自动核对证明规则一致，准确性还需要核图；本轮不改主榜、账户或线上页面。', '', '下一步：人工核对标注是否符合目标形态，再接每日页面。', '', f'行情版本：`{report["price_version"]}`']
    (out/'结论.md').write_text('\n'.join(lines)+'\n')
