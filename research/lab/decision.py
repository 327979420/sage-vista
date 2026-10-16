"""Task 005 portfolio decisions; separate from the unchanged account engine.

Decision keys: sector_cap, gaps_first, swap (booleans). Optional diagnostics
records start-of-day/after-entry/end-of-day industry counts. Prices used to
choose a swap are strictly from ci-1; execution uses ci close as registered.
"""
import math
from collections import Counter, defaultdict


def run_account_decision(trades, n_days, scenario, rules, industry, decision):
    entries = defaultdict(list)
    for k, t in enumerate(trades):
        entries[t['entry_ci']].append(k)
    for ks in entries.values():
        ks.sort(key=lambda k: (trades[k]['priority'], trades[k]['event_id']))
    cash = float(scenario['initial_cash'])
    nominal = scenario['initial_cash'] * scenario['allocation_fraction']
    fee = scenario['cost_rate']
    limit = rules['max_positions'] if rules else scenario['max_positions']
    held, equity, exposure, booked, skipped = {}, [], [], [], Counter()
    swaps, positions = [], []
    diagnostics = any(decision.values())

    def sector(symbol):
        return industry.get(symbol) or 'UNKNOWN'

    def counts():
        return dict(Counter(sector(s) for s in held))

    def finish(symbol, p):
        t = p['t']
        booked.append({'event_id': t['event_id'], 'symbol': symbol, 'signal_date': t['signal_date'],
                       'shares': p['original'], 'pnl': round(p['proceeds'] - p['cost'], 4),
                       'return': round(p['proceeds'] / p['cost'] - 1, 6)})
        del held[symbol]

    for ci in range(n_days):
        base = equity[-1] if equity else float(scenario['initial_cash'])
        start_counts = counts() if diagnostics else {}
        ks = entries.get(ci, ())
        if decision.get('gaps_first'):
            ks = sorted(ks, key=lambda k: start_counts.get(sector(trades[k]['symbol']), 0))
        swapped_today = False
        for k in ks:
            t = trades[k]
            if t['symbol'] in held:
                skipped['same_stock_held'] += 1
                continue
            if (decision.get('sector_cap') and sector(t['symbol']) != 'UNKNOWN'
                    and sum(sector(s) == sector(t['symbol']) for s in held) >= 3):
                skipped['sector_cap'] += 1
                continue
            per_share_risk = max(t['entry_price'] - t['stop'], 1e-9)
            if rules:
                qty = min(rules['position_cap'] * base / t['entry_price'],
                          rules['risk_per_trade'] * base / per_share_risk)
            else:
                qty = nominal / t['entry_price']
            if not scenario['fractional_shares']:
                qty = math.floor(qty)
            cost = qty * t['entry_price'] * (1 + fee)

            def failure():
                if len(held) >= limit:
                    return 'position_limit'
                if rules and rules.get('heat_cap') is not None:
                    open_risk = sum(p['shares'] * p['risk_per_share'] for p in held.values())
                    if open_risk + qty * per_share_risk > rules['heat_cap'] * base + 1e-9:
                        return 'open_risk_limit'
                if qty <= 0 or cost > cash + 1e-9:
                    return 'cash_or_whole_share_insufficient'
                return None

            reason = failure()
            if (reason in ('position_limit', 'cash_or_whole_share_insufficient')
                    and decision.get('swap') and not swapped_today):
                eligible = []
                for symbol, p in held.items():
                    old = p['t']
                    # Forty fully completed benchmark sessions before today's entry.
                    if ci - old['entry_ci'] >= 40:
                        previous = old['values'][ci - 1 - old['entry_ci']]
                        unrealised = (previous - old['entry_price']) / p['risk_per_share']
                        eligible.append((unrealised, symbol, p))
                if eligible:
                    # Stable holding insertion order resolves equal R, without future prices.
                    unrealised, symbol, p = min(eligible, key=lambda row: row[0])
                    if unrealised < .5:
                        old = p['t']
                        price = old['values'][ci - old['entry_ci']]
                        proceeds = p['shares'] * price * (1 - fee)
                        cash += proceeds
                        p['proceeds'] += proceeds
                        swaps.append(dict(ci=ci, event_id=old['event_id'], replacement=t['event_id'],
                                          previous_close_R=unrealised, price=price, shares=p['shares'],
                                          fee=p['shares'] * price * fee, trigger=reason,
                                          original_shares=p['original'], original_cost=p['cost']))
                        finish(symbol, p)
                        swapped_today = True
                        reason = failure()
                        swaps[-1]['replacement_entered'] = reason is None
            if reason:
                skipped[reason] += 1
                continue
            cash -= cost
            held[t['symbol']] = {'t': t, 'shares': qty, 'original': qty, 'next': 0, 'cost': cost,
                                 'proceeds': 0.0, 'risk_per_share': per_share_risk}
        after_entries = counts() if diagnostics else {}
        for symbol in list(held):
            p = held[symbol]
            t = p['t']
            while p['next'] < len(t['exits']) and t['exits'][p['next']][0] == ci:
                _, price, fraction = t['exits'][p['next']]
                p['next'] += 1
                last = p['next'] == len(t['exits'])
                qty = p['shares'] if last else min(p['shares'], math.floor(p['original'] * fraction))
                proceeds = qty * price * (1 - fee)
                cash += proceeds
                p['proceeds'] += proceeds
                p['shares'] -= qty
            if t['exits'] and p['next'] == len(t['exits']):
                finish(symbol, p)
        invested = sum(p['shares'] * p['t']['values'][ci - p['t']['entry_ci']] for p in held.values())
        nav = cash + invested
        equity.append(nav)
        exposure.append(invested / nav if nav > 0 else 0.0)
        if diagnostics:
            positions.append(dict(start=start_counts, after_entries=after_entries, end=counts()))
    result = dict(equity=equity, exposure=exposure, trades=booked, open_at_end=len(held), skipped=dict(skipped))
    if diagnostics:
        result['decision'] = dict(swaps=swaps, positions=positions)
    return result
