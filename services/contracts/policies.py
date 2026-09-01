"""Canonical shared policy identities used across data and gate contracts."""

ADJUSTMENT_POLICY = {
    "version": "eodhd-adjusted-ratio-1.0.0",
    "formula": "ratio=adjusted_close/close; adjusted_ohlc=raw_ohlc*ratio",
}

