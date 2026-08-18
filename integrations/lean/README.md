# LEAN verification adapter

`NorthstarConfluence/main.py` expresses the core Northstar entry, risk, target, sizing, and time-exit rules as a LEAN `QCAlgorithm`. It is intentionally an independent implementation rather than importing the custom Python backtester; disagreements should be investigated, not hidden.

Run with `lean backtest integrations/lean/NorthstarConfluence` after installing the LEAN CLI, Docker, and a compatible data source. This workspace currently has neither LEAN nor .NET installed, so the adapter is source-complete but has not yet produced a LEAN result. Local LEAN CLI backtesting may also require an eligible QuantConnect organization tier.
