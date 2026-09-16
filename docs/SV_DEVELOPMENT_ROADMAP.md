# Sage Vista Future Development Plan

## 1. Product Vision

Sage Vista (SV) should evolve from a **quantitative stock picker / research dashboard** into a more mature **quant trading operating system**.

The current stock-selection component is already performing reasonably well. Future development should therefore avoid endlessly adding new factors or redesigning the picker unless evidence shows that changes are necessary.

The main development priority is now to build the infrastructure that turns signals into actual portfolio decisions.

The long-term workflow should become:

**Market Data → Factor Engine → Signal Engine → Stock Selection → Portfolio Construction → Position Sizing → Entry → Position Management → Exit → Risk Management → Execution → Performance Analysis**

SV should eventually help answer:

- What opportunities exist today?
- Why did a stock qualify?
- Should the system actually take the trade?
- How much capital should be allocated?
- What positions are currently open?
- When should positions be reduced or closed?
- What risks currently exist at portfolio level?
- How has the strategy performed historically and forward?
- How closely is live/paper performance matching the research model?

---

# 2. Core Principle

Do not reinvent mature quantitative-trading infrastructure unnecessarily.

There are many strong open-source quant trading and portfolio-management projects available.

Before developing a major SV component:

1. Identify reputable existing implementations.
2. Compare their architecture with SV.
3. Select the implementation or design pattern that best fits SV.
4. Learn from and adapt proven approaches.
5. Validate SV's implementation against established implementations where possible.

We should aggressively reuse proven concepts for:

- portfolio accounting
- trade lifecycle/state
- backtesting
- performance statistics
- order models
- risk calculations
- position sizing
- slippage
- transaction costs
- broker interfaces
- reconciliation
- logging

However:

**Borrow the machinery, but validate the strategy ourselves.**

External projects should not determine SV's alpha or trading signals merely because their strategies look sophisticated.

---

# 3. Preserve the Existing Research Engine

The current SV stock picker should become one component of a larger system rather than being continuously rebuilt.

Conceptually:

## Research Engine

Responsible for:

- market data
- factor calculation
- signal generation
- eligibility rules
- ticker ranking
- factor validation
- backtesting individual hypotheses
- research experiments

## Trading Engine

Responsible for:

- portfolio construction
- position sizing
- entries
- exits
- open-position management
- cash management
- exposure
- portfolio risk
- transaction costs
- orders
- fills
- portfolio state
- performance tracking

The two engines should remain connected but logically separated.

---

# 4. Build a Real Portfolio Simulator

The next major upgrade should be a historical portfolio simulation engine.

Instead of asking:

> Did a selected stock make money 20 days later?

SV should be able to answer:

> What would have happened if SV actually managed a $100,000 portfolio using these signals?

The simulator should progress chronologically through historical trading dates.

For each date it should know:

- available cash
- current positions
- existing exposure
- today's eligible signals
- available portfolio slots
- proposed entries
- proposed exits
- position size
- realised P&L
- unrealised P&L
- portfolio value

The simulation must be **point-in-time safe** and avoid future information leakage.

---

# 5. Portfolio Performance Analytics

SV needs a dedicated performance analytics module.

At minimum it should calculate:

- Total return
- CAGR / annualised return
- Maximum drawdown
- Sharpe ratio
- Sortino ratio
- Annualised volatility
- Equity curve
- Exposure
- Capital utilisation
- Turnover
- Number of trades
- Win rate
- Average winner
- Average loser
- Average win / loss ratio
- Profit factor
- Trade expectancy
- Average holding period
- Largest losing streak
- Largest winning streak
- Realised P&L
- Unrealised P&L
- Sector / industry concentration

Later metrics may include:

- beta
- alpha versus benchmark
- information ratio
- Calmar ratio
- rolling Sharpe
- rolling drawdown
- benchmark-relative return
- risk contribution by position / sector

Metrics should be independently validated against trusted libraries or reference implementations.

---

# 6. Entry Engine

SV should convert research signals into explicit trade instructions.

A signal should have a clear lifecycle such as:

**Detected → Confirmed → Eligible → Proposed → Entered → Open → Exit Triggered → Closed**

Entry rules must explicitly define:

- when the signal becomes valid
- what information is available at that moment
- when an order can be submitted
- assumed execution price
- whether next-open / next-close / limit execution is used
- transaction costs
- slippage assumptions

No future information should be used.

---

# 7. Portfolio Construction

Ticker ranking and portfolio construction should be treated as different problems.

The picker answers:

> Which securities appear most attractive?

Portfolio construction answers:

> Which of these opportunities should actually receive capital?

The system should handle situations where there are more valid signals than available portfolio capacity.

Possible constraints include:

- maximum positions
- maximum exposure per stock
- maximum sector exposure
- maximum industry exposure
- minimum cash reserve
- correlation limits

The existing ticker score should initially be treated primarily as a **selection / prioritisation mechanism**, not automatically as a position-sizing formula.

---

# 8. Position Sizing

Do not immediately build highly sophisticated sizing algorithms.

Start by testing simple methods:

### Method A
Equal-weight positions.

### Method B
Volatility-adjusted positions.

### Method C
Fixed-risk position sizing.

Compare the effects on:

- CAGR
- drawdown
- volatility
- Sharpe
- turnover
- concentration
- tail losses

More advanced methods should only be introduced if they demonstrate measurable improvement.

---

# 9. Exit Engine

SV currently has stronger research on identifying potential entries than on managing positions after entry.

Exit research should become a major development area.

Potential exit families to test include:

- fixed holding-period exit
- signal deterioration
- trend-break exit
- moving-average break
- volatility-based stop
- ATR stop
- trailing stop
- profit target
- time + signal combination

Do not optimise dozens of combinations simultaneously.

Each exit experiment should have a predefined hypothesis and success criteria.

---

# 10. Risk Engine

A mature SV system must reason at the **portfolio level**, not only ticker level.

Example:

If SV selects six oil companies, the stock picker may view them as six attractive opportunities.

The portfolio risk engine should recognise that the portfolio may effectively have one large energy exposure.

Risk monitoring should eventually include:

- single-position exposure
- industry exposure
- sector exposure
- gross exposure
- net exposure
- portfolio volatility
- cash
- correlation
- concentration
- drawdown
- number of simultaneous positions
- portfolio risk budget

Later, market regime information may be more useful for controlling portfolio exposure than for increasing individual stock scores.

---

# 11. Trading State and Data Models

Design the backend so that the future application can interact with clean trading objects.

Useful core objects may include:

- `Signal`
- `TickerCandidate`
- `TradeProposal`
- `Portfolio`
- `PortfolioState`
- `Position`
- `Order`
- `Fill`
- `ClosedTrade`
- `DailyPortfolioSnapshot`
- `RiskSnapshot`
- `PerformanceSummary`

Avoid burying trading logic directly inside dashboard/UI code.

The trading engine should exist independently from the interface.

---

# 12. Turn SV Into a User-Facing Application

SV should eventually become something I can actually use during trading rather than simply viewing as a board.

Possible application areas:

## Today / Home

Show:

- market regime
- important portfolio alerts
- current portfolio value
- available cash
- current exposure
- strongest new opportunities
- positions requiring attention

## Signals

Show:

- current candidates
- ticker ranking
- qualification reasons
- factor breakdown
- signal date
- signal history
- historical outcome of similar signals

## Portfolio

Show:

- open positions
- cost basis
- current value
- realised P&L
- unrealised P&L
- position weight
- portfolio exposure
- industry concentration
- cash

## Trade Guidance

Show:

- proposed trade
- entry state
- suggested position size
- rationale
- risk allocation
- exit state
- stop / trailing logic where applicable

## Performance

Show:

- equity curve
- CAGR
- Sharpe
- Sortino
- drawdown
- volatility
- win rate
- profit factor
- expectancy
- average holding period
- rolling performance
- benchmark comparison

## Journal / Audit Trail

Record:

- signal generation
- trade proposal
- trade acceptance/rejection
- entry
- position modifications
- exits
- order execution
- reason codes
- timestamps
- strategy version

The audit trail is important for both research and debugging.

---

# 13. Execution Roadmap

Do not jump directly from historical backtesting to automated live trading.

Use the following progression:

**Historical Signal Research**

↓

**Historical Portfolio Simulation**

↓

**Forward / Shadow Portfolio**

↓

**Paper Trading**

↓

**Small Live Capital**

↓

**Semi-Automated Trading**

↓

**Automated Trading**

Paper trading should test operational issues including:

- duplicate orders
- failed orders
- stale signals
- partial fills
- market holidays
- API downtime
- incorrect position state
- system restart / recovery
- broker/account reconciliation

---

# 14. Development Process

Before every major development phase, create a short sprint document.

Each sprint should contain:

## Objective

What specific problem are we solving?

## Hypothesis

Why should this improve SV?

## Scope

What exactly will be built or tested?

## Deliverables

What concrete outputs must exist?

## Milestones

What are the implementation stages?

## Acceptance Criteria

What conditions must be met before the sprint is considered complete?

## Dependencies

What data, modules or external systems are required?

## Out of Scope

What specifically should NOT be worked on during this sprint?

This is critical for preventing scope drift.

---

# 15. Research Experiment Standard

Before implementing a new trading idea, record:

**Hypothesis**

What should improve and why?

**Change**

What exactly changes in the system?

**Data**

What information may the experiment use?

**Baseline**

What are we comparing against?

**Success Metrics**

What would justify keeping the idea?

**Failure Criteria**

What result would cause us to reject it?

**Result**

What happened?

**Decision**

Accepted / Rejected / Requires More Data.

Maintain a rejected-experiments log.

A mature quantitative system should document not only what works but also what was tested and rejected.

---

# 16. Initial Development Priority

Unless new evidence suggests otherwise, development priority should be:

### Phase 1 — Trading Foundation
1. Review existing quant frameworks/repositories.
2. Freeze unnecessary picker changes.
3. Define portfolio/trading data models.
4. Build historical portfolio simulator.
5. Implement cash/position accounting.
6. Generate equity curve.
7. Build performance analytics.

### Phase 2 — Trading Logic
8. Formalise entry lifecycle.
9. Test position-sizing methods.
10. Develop exit engine.
11. Implement portfolio construction rules.

### Phase 3 — Risk
12. Position-level risk.
13. Sector/industry concentration.
14. portfolio exposure.
15. drawdown/risk controls.

### Phase 4 — Product
16. Build SV application interface.
17. Today dashboard.
18. Portfolio page.
19. Signal page.
20. Performance analytics.
21. Trade journal/audit trail.

### Phase 5 — Execution
22. Shadow portfolio.
23. Paper broker integration.
24. Execution engine.
25. Order reconciliation.
26. Small-capital live testing.
27. Gradual automation.

---

# 17. Proposed Next Sprint

## Sprint: SV Trading Foundation V0

### Goal

Transform SV from a signal-ranking system into the foundation of a portfolio-level trading system.

### Deliverables

- research comparison of suitable open-source quant projects
- selected reference architectures
- core portfolio/trading data model
- historical portfolio simulator
- cash accounting
- position accounting
- trade lifecycle
- reproducible equity curve
- CAGR
- annualised volatility
- Sharpe
- Sortino
- maximum drawdown
- exposure
- capital utilisation
- basic trade statistics

### Acceptance Criteria

Starting with a defined amount of capital on a historical date, SV must be able to:

1. process historical signals chronologically;
2. only use information available at that time;
3. decide which eligible securities enter the portfolio under fixed rules;
4. create and close positions;
5. correctly account for cash and P&L;
6. produce daily portfolio values;
7. generate a reproducible equity curve;
8. calculate validated performance metrics.

### Explicitly Out of Scope

Do NOT spend this sprint on:

- new alpha factors
- major ticker-picker redesign
- machine learning
- live broker API
- automated live trading
- extensive UI redesign
- dozens of exit-rule combinations
- unnecessary optimisation

---

# Working Instruction for Future ChatGPT / Codex Conversations

Use this roadmap as the strategic direction for Sage Vista.

Before proposing substantial implementation work:

1. Inspect the existing SV design and code.
2. Preserve working functionality unless there is evidence it should change.
3. Determine which roadmap layer the task belongs to.
4. Research strong existing open-source quant implementations when relevant.
5. Prefer adapting proven infrastructure over reinventing it.
6. Keep alpha/research logic evidence-driven.
7. Avoid unnecessary complexity.
8. Explicitly distinguish research metrics from portfolio/trading metrics.
9. Protect against look-ahead bias and leakage.
10. Keep the trading engine separated from the application/UI.
11. Design outputs so they can later support an interactive SV trading application.
12. Work according to the current sprint's scope and acceptance criteria.
13. Do not introduce unrelated features during the sprint.
14. Record major architectural decisions and rejected approaches.

The objective is not to make Sage Vista look more sophisticated.

The objective is to make it **more testable, reliable, usable, and capable of managing an actual trading strategy end-to-end**.