PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY, company TEXT NOT NULL, exchange TEXT, first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL, security_type TEXT NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bars_daily (
  symbol TEXT NOT NULL, trading_date TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
  low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL, source TEXT NOT NULL,
  ingested_at TEXT NOT NULL, PRIMARY KEY(symbol,trading_date)
);
CREATE TABLE IF NOT EXISTS universe_membership (
  as_of_date TEXT NOT NULL, symbol TEXT NOT NULL, eligible INTEGER NOT NULL, reason TEXT NOT NULL,
  price REAL, avg_dollar_volume_20 REAL, history_bars INTEGER NOT NULL,
  PRIMARY KEY(as_of_date,symbol)
);
CREATE TABLE IF NOT EXISTS factor_observations (
  as_of_date TEXT NOT NULL, symbol TEXT NOT NULL, factor TEXT NOT NULL, value REAL,
  available INTEGER NOT NULL, source TEXT NOT NULL, calculation_version TEXT NOT NULL,
  PRIMARY KEY(as_of_date,symbol,factor)
);
CREATE TABLE IF NOT EXISTS forward_returns (
  as_of_date TEXT NOT NULL, symbol TEXT NOT NULL, horizon_bars INTEGER NOT NULL, return_value REAL,
  PRIMARY KEY(as_of_date,symbol,horizon_bars)
);
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, code_version TEXT NOT NULL,
  data_start TEXT NOT NULL, data_end TEXT NOT NULL, universe_count INTEGER NOT NULL,
  status TEXT NOT NULL, specification_json TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bars_date_symbol ON bars_daily(trading_date,symbol);
CREATE INDEX IF NOT EXISTS idx_universe_eligible_date ON universe_membership(eligible,as_of_date);
CREATE INDEX IF NOT EXISTS idx_factor_name_date ON factor_observations(factor,as_of_date);
CREATE INDEX IF NOT EXISTS idx_forward_horizon_date ON forward_returns(horizon_bars,as_of_date);
