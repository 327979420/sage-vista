"""Trace and reconcile one existing VectorBT account; never select trades again."""
import html
import math
from statistics import mean

REASONS={1:'same_stock_held',2:'position_limit',3:'cash_or_whole_share_insufficient'}
ZH={'same_stock_held':'已持有同一股票','position_limit':'持仓数量已满','cash_or_whole_share_insufficient':'现金不足或买不起一整股','entry_at_or_below_planned_stop':'开盘价格不符合原入场条件','rank_and_capacity_available':'按原排名，有仓位且现金足够','pending_next_session':'等待下一交易日','original_plan_not_executable':'原入场计划不可执行'}


def cost_assumptions(config):
    parts=('commission_rate','fee_rate','slippage_rate')
    present=[k in config for k in parts]
    if any(present):
        if not all(present):raise ValueError('complete_cost_breakdown_required')
        if any(type(config[k]) not in (float,int) or not math.isfinite(config[k]) or config[k]<0 for k in parts):raise ValueError('invalid_cost_component')
        if not math.isclose(sum(config[k] for k in parts),config['cost_rate'],abs_tol=1e-12):raise ValueError('cost_breakdown_mismatch')
        return {'mode':'cash_equivalent_proportional_cost','commission_rate':config['commission_rate'],'fee_rate':config['fee_rate'],'slippage_rate':config['slippage_rate'],'total_rate':config['cost_rate'],'note':'Slippage charged as an equivalent cash cost, not a changed fill price.'}
    return {'mode':'legacy_combined_cost','total_rate':config['cost_rate'],'commission_rate':None,'fee_rate':None,'slippage_rate':None,'note':'Historical combined cost; components not separately specified.'}


def close(a,b,label):
    if not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-6):raise ValueError('ledger_reconciliation_failed:'+label)


def build_ledger(pf, events, trades, pending, rows, sessions, config, decision_cash, decision_positions, reasons):
    costs=cost_assumptions(config)
    original={e['event_id']:e for e in events};prices={s:{r['date']:r for r in rs} for s,rs in rows.items()}
    fills=pf.orders.records.to_dict('records')
    fills=sorted(fills,key=lambda r:(int(r['idx']),int(r['id'])))
    byday={d:[] for d in sessions}
    for f in fills:
        t=trades[int(f['col'])];day=sessions[int(f['idx'])//3]
        byday[day].append({'order_id':int(f['id']),'event_id':t['event_id'],'symbol':t['symbol'],
          'phase':'open' if int(f['idx'])%3==0 else 'exit_phase','action':'BUY' if int(f['side'])==0 else 'SELL',
          'quantity':float(f['size']),'price':float(f['price']),'fees':float(f['fees']),
          'reason':'rank_and_capacity_available' if int(f['side'])==0 else t['execution'].get('exit_reason','exit')})
    decisions={d:[] for d in sessions}
    for col,t in enumerate(trades):
        event=original[t['event_id']]
        executed=t['status'] in ('open','closed')
        decisions[t['entry_date']].append({'event_id':t['event_id'],'symbol':t['symbol'],'signal_date':t['signal_date'],
          'decision_date':t['entry_date'],'phase':'open','rank':t['rank'],
          'action':'BUY' if executed else 'SKIP','reason':'rank_and_capacity_available' if executed else REASONS.get(int(reasons[col]),t['execution'].get('reason','original_plan_not_executable')),
          'cash_at_decision':float(decision_cash[col]) if math.isfinite(decision_cash[col]) else None,
          'positions_at_decision':int(decision_positions[col]) if int(decision_positions[col])>=0 else None,
          'planned_notional':config['initial_cash']*config['allocation_fraction'],
          'entry_policy':event['selection']['execution_policy_version'],
          'opportunity_timeframe':event['selection'].get('opportunity_timeframe',event['selection'].get('timeframe','not_recorded'))})
    cash=float(config['initial_cash']);realised=0.;positions={};last_equity=cash;last_positions=[];days=[]
    reference_cash=pf.cash().iloc[2::3].to_numpy();reference_equity=pf.value().iloc[2::3].to_numpy()
    reference_assets=pf.assets().iloc[2::3].to_numpy()
    for i,day in enumerate(sessions):
        starting_cash=cash;starting_realised=realised;starting_positions=[dict(p) for p in last_positions]
        for f in byday[day]:
            eid=f['event_id'];gross=f['quantity']*f['price'];fee=f['fees']
            if f['action']=='BUY':
                if eid in positions:raise ValueError('duplicate_position_fill')
                positions[eid]={'event_id':eid,'symbol':f['symbol'],'quantity':f['quantity'],'entry_date':day,'cost_basis':gross+fee,'entry_price':f['price']}
                cash-=gross+fee
            else:
                if eid not in positions:raise ValueError('sell_without_position')
                pos=positions.pop(eid);close(pos['quantity'],f['quantity'],'sell_quantity')
                f['realised_pnl']=gross-fee-pos['cost_basis']
                realised+=f['realised_pnl'];cash+=gross-fee
        snapshots=[]
        for eid,pos in positions.items():
            bar=prices[pos['symbol']].get(day)
            if bar is None:raise ValueError('missing_held_mark')
            value=pos['quantity']*bar['close']
            snapshots.append({**pos,'close':bar['close'],'market_value':value,'unrealised_pnl':value-pos['cost_basis']})
        market=sum(p['market_value'] for p in snapshots);unrealised=sum(p['unrealised_pnl'] for p in snapshots);equity=cash+market
        close(cash,float(reference_cash[i]),'cash:'+day);close(equity,float(reference_equity[i]),'equity:'+day)
        close(equity-config['initial_cash'],realised+unrealised,'pnl:'+day)
        for col,t in enumerate(trades):close(positions.get(t['event_id'],{}).get('quantity',0),float(reference_assets[i,col]),'position:'+day)
        if cash < -1e-6:raise ValueError('negative_cash')
        signals=[{'event_id':e['event_id'],'symbol':e['symbol'],'rank':e['selection']['rank'],'available_at':day+' after_close',
          'selection':e['selection'],'state':'eligible_pending_next_open'} for e in events if e['signal_date']==day]
        days.append({'date':day,'starting_cash':starting_cash,'starting_portfolio_value':last_equity,'starting_valuation_basis':'previous_session_close_or_initial_cash',
          'starting_positions':starting_positions,'eligible_signals':signals,'trade_proposals':signals,'decisions':decisions[day],
          'executed_buys':[f for f in byday[day] if f['action']=='BUY'],'executed_sells':[f for f in byday[day] if f['action']=='SELL'],
          'skipped_signals':[d for d in decisions[day] if d['action']=='SKIP'],
          'ending_cash':cash,'positions':snapshots,'market_value':market,'ending_portfolio_value':equity,
          'daily_pnl':equity-last_equity,'cumulative_pnl':equity-config['initial_cash'],
          'realised_pnl':realised,'realised_pnl_today':realised-starting_realised,'unrealised_pnl':unrealised,
          'gross_exposure':market/equity if equity else None,'capital_utilisation':market/equity if equity else None})
        last_equity=equity;last_positions=snapshots
    return {'schema':'sv-daily-portfolio-ledger-v0','role':'legacy_account_engineering_baseline','initial_cash':config['initial_cash'],
      'config':config,'cost_assumptions':costs,'timing':'signal after close -> next-session open decisions/buys -> exits -> closing valuation; no same-day exit proceeds fund opening buys',
      'validation':'Every cash, equity and share balance reconciles to the same VectorBT run.',
      'pending_signals':pending,'days':days,'metrics':performance(days,trades,config['initial_cash'])}


def performance(days,trades,initial):
    import pandas as pd
    import quantstats as qs
    equity=pd.Series([d['ending_portfolio_value'] for d in days],index=pd.to_datetime([d['date'] for d in days]))
    returns=equity.pct_change(fill_method=None);returns.iloc[0]=equity.iloc[0]/initial-1
    def finite(v):
        value=float(v)
        return value if math.isfinite(value) else None
    closed=sorted([t for t in trades if t['status']=='closed'],key=lambda t:(t['execution']['exit_date'],t['event_id']))
    pnls=[t['net_pnl'] for t in closed];wins=[v for v in pnls if v>0];losses=[v for v in pnls if v<0]
    losing=longest=0
    for v in pnls:
        losing=losing+1 if v<0 else 0;longest=max(longest,losing)
    peak=initial;drawdown=0
    for v in equity:
        peak=max(peak,v);drawdown=min(drawdown,v/peak-1)
    close(float(qs.stats.max_drawdown(returns)),drawdown,'drawdown')
    total=equity.iloc[-1]/initial-1;close(qs.stats.comp(returns),total,'total_return')
    mean_win=mean(wins) if wins else None;mean_loss=mean(losses) if losses else None
    notional=sum(f['quantity']*f['price'] for d in days for f in d['executed_buys']+d['executed_sells'])
    return {'total_return':float(total),'cagr':finite(qs.stats.cagr(returns,periods=252)),
      'annualised_volatility':finite(qs.stats.volatility(returns,periods=252)),
      'sharpe':finite(qs.stats.sharpe(returns,rf=0,periods=252)),
      'sortino':finite(qs.stats.sortino(returns,rf=0,periods=252)),
      'max_drawdown':drawdown,'average_gross_exposure':mean(d['gross_exposure'] for d in days),
      'average_capital_utilisation':mean(d['capital_utilisation'] for d in days),
      'gross_turnover':notional/float(equity.mean()),'turnover_definition':'sum buy+sell notional / mean daily equity; not annualised or halved',
      'entered_trades':sum(t['status'] in ('open','closed') for t in trades),'closed_trades':len(closed),'open_trades':sum(t['status']=='open' for t in trades),
      'win_rate':len(wins)/len(closed) if closed else None,'average_winner_dollars':mean_win,'average_loser_dollars':mean_loss,
      'win_loss_ratio':mean_win/abs(mean_loss) if mean_win is not None and mean_loss is not None else None,
      'profit_factor':sum(wins)/abs(sum(losses)) if losses else None,'expectancy_dollars':mean(pnls) if pnls else None,
      'average_closed_holding_sessions':mean(t['execution']['holding_sessions'] for t in closed) if closed else None,
      'largest_losing_streak':longest,'realised_pnl':days[-1]['realised_pnl'],'unrealised_pnl':days[-1]['unrealised_pnl'],
      'sector_concentration':None,'sector_status':'historical_sector_data_not_provided',
      'conventions':'252 sessions per year; rf/Sortino target=0; CAGR uses QuantStats session-count convention; profit factor unavailable if no losses; costs included; trade statistics use closed trades only'}


def render_ledger(ledger,synthetic=False):
    days=ledger['days'];last=days[-1];cash=ledger['initial_cash'];pnl=last['ending_portfolio_value']-cash
    label='人工样例：只验证记账，不是策略业绩' if synthetic else '旧规则账户基线：不是已验证的新分周期策略'
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>每天的钱去了哪里</title><style>body{max-width:1050px;margin:auto;padding:24px;background:#f3f6f8;color:#20303b;font:16px/1.8 system-ui}section{background:white;padding:20px;margin:20px 0;border-radius:12px}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:right}summary{cursor:pointer;font-weight:bold}.scroll{overflow:auto}</style><h1>每天的钱去了哪里？</h1><p>'+label+'</p>',f'<section><h2>先看钱有没有变多</h2><p>开始 ${cash:,.2f} → 最后 ${last["ending_portfolio_value"]:,.2f}；合计{"赚" if pnl>=0 else "亏"} ${abs(pnl):,.2f}。</p><p>已经卖出的盈亏 ${last["realised_pnl"]:,.2f}；仍持有的账面盈亏 ${last["unrealised_pnl"]:,.2f}。</p><p>现金 ${last["ending_cash"]:,.2f}；股票市值 ${last["market_value"]:,.2f}。两项相加等于账户总值。</p><p>点击下面任意一天，可查看当天买卖和没有买的原因。今天收盘出现的信号，最早下一交易日开盘处理。</p></section>']
    contributions={}
    for d in days:
        for f in d['executed_sells']:
            contributions[f['symbol']]=contributions.get(f['symbol'],0)+f['realised_pnl']
    for p in last['positions']:
        contributions[p['symbol']]=contributions.get(p['symbol'],0)+p['unrealised_pnl']
    skipped={}
    for d in days:
        for decision in d['skipped_signals']:
            reason=decision['reason'];skipped[reason]=skipped.get(reason,0)+1
    parts.append('<section><h2>钱主要赚在哪里、亏在哪里？</h2>')
    for symbol,value in sorted(contributions.items(),key=lambda x:x[1],reverse=True):
        parts.append(f'<p>{html.escape(symbol)}：合计盈亏 ${value:,.2f}（已卖出加仍持有，已扣实际发生的成本）。</p>')
    m=ledger['metrics']
    parts.append(f'<p>平均有 {m["average_capital_utilisation"]:.1%} 的资金放在股票里；其余留作现金。期间账户从最高点最多回落 {abs(m["max_drawdown"]):.2%}。</p>')
    parts.append(f'<p>实际买入 {m["entered_trades"]} 笔；已卖出 {m["closed_trades"]} 笔；仍持有 {m["open_trades"]} 笔。</p>')
    for reason,count in skipped.items():
        parts.append(f'<p>没买的原因：{ZH.get(reason,html.escape(reason))}，共 {count} 次。</p>')
    parts.append('<p>这些记录说明钱如何变化。是否应该更早卖、或被跳过的股票是否更好，需要另做对照实验，不能仅凭这份账决定。</p></section>')
    for d in days:
        parts.append(f'<section><details><summary>{d["date"]} · 当日盈亏 ${d["daily_pnl"]:,.2f} · 账户 ${d["ending_portfolio_value"]:,.2f}</summary>')
        parts.append(f'<p>开始现金 ${d["starting_cash"]:,.2f}，持仓{len(d["starting_positions"])}笔；结束现金 ${d["ending_cash"]:,.2f}，持仓{len(d["positions"])}笔。</p>')
        for x in d['decisions']:
            parts.append('<p>'+html.escape(x['symbol'])+'：'+('买入' if x['action']=='BUY' else '跳过')+'。原因：'+ZH.get(x['reason'],html.escape(x['reason']))+f'；原排名第{x["rank"]}。</p>')
        for f in d['executed_buys']+d['executed_sells']:
            parts.append(f'<p>{"买" if f["action"]=="BUY" else "卖"} {html.escape(f["symbol"])}：{f["quantity"]:g}股 × ${f["price"]:.4f}；成本 ${f["fees"]:.2f}。</p>')
        signals='、'.join(html.escape(x['symbol']) for x in d['eligible_signals']) or '没有'
        parts.append('<p>今天收盘新增候选：'+signals+'。</p>')
        for pos in d['positions']:
            parts.append(f'<p>持有 {html.escape(pos["symbol"])} {pos["quantity"]:g}股；市值 ${pos["market_value"]:,.2f}；账面盈亏 ${pos["unrealised_pnl"]:,.2f}。</p>')
        parts.append('</details></section>')
    parts.append('<p>每一天的现金、股票数量和总资产均与同一次VectorBT计算核对。逐日完整数据见JSON。行业信息未提供；现金账户研究不等于真实券商账户。</p></html>')
    return ''.join(parts)


def validate_ledger_receipt(receipt):
    """Reject internally inconsistent saved books, even after receipt resealing."""
    book=receipt['portfolio_ledger'];days=book.get('days',[]);account=receipt.get('daily_account',[])
    if book.get('schema')!='sv-daily-portfolio-ledger-v0' or len(days)!=len(account) or not days:
        raise ValueError('invalid_portfolio_ledger')
    close(book['initial_cash'],receipt['scenario']['initial_cash'],'initial_cash')
    cash=book['initial_cash'];value=cash
    for d,a in zip(days,account):
        if d['date']!=a['date']:raise ValueError('ledger_date_mismatch')
        close(d['starting_cash'],cash,'starting_cash');close(d['starting_portfolio_value'],value,'starting_equity')
        close(d['market_value'],sum(p['market_value'] for p in d['positions']),'market_value')
        for p in d['positions']:
            close(p['quantity']*p['close'],p['market_value'],'position_mark')
            close(p['market_value']-p['cost_basis'],p['unrealised_pnl'],'position_pnl')
        close(d['unrealised_pnl'],sum(p['unrealised_pnl'] for p in d['positions']),'unrealised_pnl')
        cash+=sum(f['quantity']*f['price']-f['fees'] for f in d['executed_sells'])-sum(f['quantity']*f['price']+f['fees'] for f in d['executed_buys'])
        close(cash,d['ending_cash'],'fill_cash')
        close(cash+d['market_value'],a['equity'],'saved_equity')
        close(d['ending_portfolio_value'],a['equity'],'ledger_equity')
        close(d['daily_pnl'],a['equity']-value,'daily_pnl')
        close(d['realised_pnl']+d['unrealised_pnl'],a['equity']-book['initial_cash'],'cumulative_pnl')
        for decision in d['decisions']:
            if decision['signal_date']>=d['date'] or decision['decision_date']!=d['date'] or decision['action'] not in ('BUY','SKIP') or not decision['reason']:
                raise ValueError('invalid_decision_timing_or_reason')
        value=a['equity']
