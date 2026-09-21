"""Pure daily Market Internals facts and configurable observational risk.

No candidate, ranking, account, provider or cache I/O. All windows are indexed
by the supplied completed SPY sessions; absent bars never silently compress time.
"""
from __future__ import annotations
from statistics import mean, median, pstdev
from services.contracts.market_data import canonical_fingerprint

CALCULATION_VERSION = 'market-internals-calc-1.0.0'


def validate_config(config):
    """Reject accidental weight/threshold edits before appending a new series."""
    groups=config['subscores']
    if abs(sum(g['weight'] for g in groups.values())-1)>1e-9:
        raise ValueError('market_group_weights_must_sum_to_one')
    for g in groups.values():
        if g['weight']<0 or any(w<0 for w in g['components'].values()) or abs(sum(g['components'].values())-1)>1e-9:
            raise ValueError('market_component_weights_invalid')
    q=config['quality']
    if not 0<q['minimum_coverage']<=1 or q['minimum_members']<1 or q['percentile_minimum']<1:
        raise ValueError('market_quality_config_invalid')
    bands=config['temperature_bands']
    if [b['maximum'] for b in bands]!=sorted(set(b['maximum'] for b in bands)) or bands[-1]['maximum']!=100:
        raise ValueError('market_temperature_bands_invalid')
    for spec in config['indicators'].values():
        levels=spec['levels']
        if [b['maximum'] for b in levels]!=sorted(set(b['maximum'] for b in levels)):
            raise ValueError('market_indicator_bands_invalid')
    for knots in [s['risk_knots'] for s in config['indicators'].values()]+list(config['derived_risks'].values()):
        if [k[0] for k in knots]!=sorted(set(k[0] for k in knots)) or any(not 0<=k[1]<=100 for k in knots):
            raise ValueError('market_risk_curve_invalid')


def ratio(a, b, scale=1):
    return a / b * scale if b else None


def rounded(value):
    return round(value, 6) if value is not None else None


def risk(value, knots):
    if value is None or not knots:
        return None
    if value <= knots[0][0]:
        return knots[0][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if value <= x1:
            return y0 + (y1-y0)*(value-x0)/(x1-x0)
    return knots[-1][1]


def band(value, bands):
    if value is None:
        return {'label': '数据不足', 'tone': 'neutral'}
    for item in bands:
        if value <= item['maximum']:
            return {'label': item['label'], 'tone': item['tone']}
    return {'label': bands[-1]['label'], 'tone': bands[-1]['tone']}


def window(series, sessions, end, length):
    if end + 1 < length:
        return None
    dates = sessions[end-length+1:end+1]
    if any(day not in series for day in dates):
        return None
    return [series[day] for day in dates]


def facts(stock_series, etfs, sessions, day, members):
    """Series contain validated adjusted OHLC plus original volume/raw close."""
    end = sessions.index(day)
    advances = declines = unchanged = 0
    up = down = 0
    returns, rvols = [], []
    above = {n: [] for n in (20, 50, 200)}
    highs, lows = [], []
    valid = 0
    for symbol in members:
        series = stock_series.get(symbol, {})
        pair = window(series, sessions, end, 2)
        if pair is None or pair[-1]['volume'] <= 0:
            continue
        valid += 1
        change = pair[-1]['close']/pair[0]['close']-1
        returns.append(change)
        if change > 1e-10:
            advances += 1
            up += pair[-1]['volume']
        elif change < -1e-10:
            declines += 1
            down += pair[-1]['volume']
        else:
            unchanged += 1
        for n in above:
            w = window(series, sessions, end, n)
            if w:
                above[n].append(w[-1]['close'] > mean(b['close'] for b in w))
        w = window(series, sessions, end, 21)
        if w and mean(b['volume'] for b in w[:-1]) > 0:
            rvols.append(w[-1]['volume']/mean(b['volume'] for b in w[:-1]))
        w = window(series, sessions, end, 252)
        if w:
            highs.append(w[-1]['high'] >= max(b['high'] for b in w))
            lows.append(w[-1]['low'] <= min(b['low'] for b in w))
    benchmark = {}
    for ticker in ('SPY', 'RSP'):
        w = window(etfs.get(ticker, {}), sessions, end, 6)
        benchmark[ticker] = w[-1]['close'] if w else None
    rs = ratio(benchmark['RSP'], benchmark['SPY']) if all(benchmark.values()) else None
    values = {f'above{n}': ratio(sum(v), len(v), 100) for n, v in above.items()}
    values.update(ad_ratio=ratio(advances, declines), ad_line=None,
                  up_volume=ratio(up, up+down, 100), median_rvol=median(rvols) if rvols else None,
                  rvol_breadth=ratio(sum(v > 1.5 for v in rvols), len(rvols), 100),
                  new_high_low=ratio(sum(highs)-sum(lows), len(highs), 100),
                  rsp_spy=rs, dispersion=pstdev(returns)*100 if len(returns) >= 2 else None,
                  trin=ratio(advances*down, declines*up) if declines and up and down else None)
    counts = {f'above{n}': len(v) for n, v in above.items()}
    counts.update(ad_ratio=valid, ad_line=valid, up_volume=valid, median_rvol=len(rvols),
                  rvol_breadth=len(rvols), new_high_low=len(highs), dispersion=valid, trin=valid,
                  rsp_spy=2 if rs is not None else 0)
    return {'values': values, 'valid': valid, 'counts': counts, 'spy': benchmark['SPY'],
            'advances': advances, 'declines': declines, 'unchanged': unchanged,
            'net_advances': advances-declines, 'new_highs': sum(highs), 'new_lows': sum(lows),
            'up_shares': up, 'down_shares': down}


def snapshot(raw, *, day, sessions, universe, config, prior, identity, observation_kind):
    """Decorate raw facts using only earlier saved observations in this series."""
    q = config['quality']; n = len(universe['members']); end = sessions.index(day)
    by_day = {p['date']: p for p in prior}
    def earlier(offset):
        return by_day.get(sessions[end-offset]) if end >= offset else None
    def change(key, offset, relative=False):
        p = earlier(offset); value = raw['values'][key]
        old = p['indicators'][key]['value'] if p else None
        if value is None or old is None or not p['indicators'][key]['reliable']:
            return None
        return (ratio(value-old, old, 100) if relative else value-old)
    coverage = ratio(raw['valid'], n) or 0
    reasons = []
    if n < q['minimum_members']: reasons.append('固定样本数量不足')
    if coverage < q['minimum_coverage']: reasons.append('有效行情覆盖不足')
    previous = earlier(1)
    if previous and previous['quality']['coverage']-coverage > q['maximum_coverage_drop']+1e-10:
        reasons.append('行情覆盖较前日明显下降')
    five = [earlier(j) for j in range(1, 5)]
    ad5 = (mean([ratio(raw['net_advances'], raw['valid'], 100)] +
                [ratio(p['counts']['net_advances'], p['quality']['valid_ticker_count'], 100) for p in five])
           if raw['valid'] and all(p and p['quality']['coverage'] >= q['minimum_coverage'] for p in five) else None)
    # A missing aggregate day breaks the cumulative line permanently within the series.
    raw['values']['ad_line'] = (previous['indicators']['ad_line']['value'] + raw['net_advances']
                               if previous and previous['indicators']['ad_line']['value'] is not None else
                               raw['net_advances'] if not prior else None)
    if coverage < q['minimum_coverage']:
        raw['values']['ad_line'] = None
    indicators, risks = {}, {}
    for key, spec in config['indicators'].items():
        value = raw['values'][key]
        reliable = value is not None and (raw['counts'][key]/(2 if key == 'rsp_spy' else n) if n else 0) >= q['minimum_coverage']
        if not reliable and key != 'ad_line': reasons.append(spec['label']+'数据不足')
        delta1, delta5 = change(key, 1, key=='rsp_spy'), change(key, 5, key=='rsp_spy')
        r = risk(value, spec['risk_knots'])
        level = band(value, spec['levels'])
        if key == 'rsp_spy':
            r = risk(delta5, config['derived_risks']['rsp_spy_5d'])
            level = band(delta5, spec['levels'])
        comparable = [p['indicators'][key]['value'] for p in prior[-252:]
                      if p['indicators'][key]['reliable'] and p['indicators'][key]['value'] is not None]
        percentile = ratio(sum(v < value for v in comparable)+sum(v == value for v in comparable)/2, len(comparable), 100) if reliable and len(comparable)>=q['percentile_minimum'] and key!='ad_line' else None
        trend = '观察中'
        if delta5 is not None:
            if abs(delta5) < 1e-8: trend = '持平'
            elif spec['trend'] == 'risk':
                old = earlier(5)['indicators'][key]['risk']
                trend = ('压力升高' if r > old else '压力下降' if r < old else '压力持平') if r is not None and old is not None else '观察中'
            else:
                good = delta5 < 0 if spec['trend']=='lower_healthy' else delta5 > 0
                trend = '改善' if good else '恶化'
        if not reliable: level = band(None, []); trend = '数据不足'
        indicators[key] = {'value':rounded(value), 'valid_count':raw['counts'][key], 'reliable':reliable,
                           'level':level, 'risk':rounded(r) if reliable else None,
                           'change_1d':rounded(delta1) if reliable else None, 'change_5d':rounded(delta5) if reliable else None,
                           'trend':trend, 'percentile':rounded(percentile), 'percentile_samples':len(comparable)}
        risks[key] = r if reliable else None
    extra = {'extension20':raw['values']['above20'], 'extension50':raw['values']['above50'],
             'ad5':ad5, 'breadth50_5d':change('above50',5), 'rsp_spy_5d':change('rsp_spy',5,True)}
    risks.update({k:risk(v,config['derived_risks'][k]) for k,v in extra.items()})
    subscores = {}
    for key, spec in config['subscores'].items():
        components = {k:rounded(risks[k]) for k in spec['components']}
        value = sum(risks[k]*w for k,w in spec['components'].items()) if all(v is not None for v in components.values()) else None
        subscores[key] = {'score':rounded(value), 'weight':spec['weight'], 'components':components}
    if any(v['score'] is None for v in subscores.values()): reasons.append('评分成分或5日比较不足')
    score = round(sum(s['score']*s['weight'] for s in subscores.values()),1) if not reasons else None
    status = band(score, config['temperature_bands'])
    if reasons: status = {'label':'INCOMPLETE','tone':'neutral'}
    temperature = {'score':score,'status':status,'subscores':subscores}
    for offset in (1,5):
        p=earlier(offset); old=p['temperature']['score'] if p else None
        temperature[f'change_{offset}d'] = round(score-old,1) if score is not None and old is not None else None
    b50=raw['values']['above50']; b50_delta=change('above50',5)
    if reasons:
        explanation='数据尚不完整，暂不显示风险温度。'
    else:
        heat='短期不热' if subscores['extension']['score']<=config['temperature_bands'][0]['maximum'] else '短期扩张偏高'
        breadth='广度偏弱' if b50<50 else '多数股票仍在50日均线上方'
        drift=f"，5日{'下降' if b50_delta<0 else '增加'}{abs(b50_delta):.1f}个百分点" if b50_delta is not None else ''
        joiner='但' if b50<50 else '且'
        explanation=f"{heat}，{joiner}{breadth}：{b50:.0f}%个股高于50日均线{drift}。"
    result={'date':day,'universe_id':universe['id'],'calculation_version':CALCULATION_VERSION,
            'config_fingerprint':canonical_fingerprint(config),'identity':identity,'observation_kind':observation_kind,
            'quality':{'status':'incomplete' if reasons else 'complete','reasons':list(dict.fromkeys(reasons)),
                       'universe_size':n,'valid_ticker_count':raw['valid'],'missing_ticker_count':n-raw['valid'],'coverage':rounded(coverage)},
            'temperature':temperature,'explanation':explanation,'indicators':indicators,'spy':rounded(raw['spy']),
            'counts':{k:raw[k] for k in ('advances','declines','unchanged','net_advances','new_highs','new_lows','up_shares','down_shares')}}
    result['fingerprint']=canonical_fingerprint(result)
    return result
