"""Point-in-time feature calculations for the factor strategy laboratory."""
from __future__ import annotations

import json
import math
import pathlib
import statistics

from research.backtest.winner_loser_optimization_v1 import FeatureSeries
from services.scanner.macd_factor_backtest import adjusted_rows
from services.scanner.technical import atr, rsi


CATALOG_PATH = pathlib.Path(__file__).parents[1] / "factor-candidates-v2.json"


def finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def load_catalog(path: str | pathlib.Path = CATALOG_PATH) -> dict:
    payload = json.loads(pathlib.Path(path).read_text())
    ids = [item["candidate_id"] for item in payload["candidates"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Candidate IDs must be unique")
    if any(item.get("production_weight") != 0 for item in payload["candidates"]):
        raise ValueError("Research candidates must start with zero production weight")
    return payload


CATALOG = load_catalog()
CANDIDATES = {item["candidate_id"]: item for item in CATALOG["candidates"]}


def _pearson(first: list[float], second: list[float]) -> float | None:
    if len(first) < 3 or len(first) != len(second):
        return None
    a_mean, b_mean = statistics.fmean(first), statistics.fmean(second)
    numerator = sum((a - a_mean) * (b - b_mean) for a, b in zip(first, second))
    denominator = math.sqrt(
        sum((a - a_mean) ** 2 for a in first) * sum((b - b_mean) ** 2 for b in second)
    )
    return numerator / denominator if denominator else None


def _linear_fit(values: list[float]) -> tuple[float | None, float | None]:
    if len(values) < 3:
        return None, None
    x_mean = (len(values) - 1) / 2
    y_mean = statistics.fmean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return None, None
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * index for index in range(len(values))]
    total = sum((value - y_mean) ** 2 for value in values)
    residual = sum((value - estimate) ** 2 for value, estimate in zip(values, fitted))
    r_squared = 1 - residual / total if total else None
    return r_squared, values[-1] - fitted[-1]


def _true_ranges(rows: list[dict]) -> list[float]:
    output = []
    for index, row in enumerate(rows):
        high, low = float(row["high"]), float(row["low"])
        if index == 0:
            output.append(high - low)
        else:
            prior = float(rows[index - 1]["close"])
            output.append(max(high - low, abs(high - prior), abs(low - prior)))
    return output


def _directional_control(rows: list[dict], period: int = 14) -> tuple[list[float | None], list[float | None]]:
    """Return signed ADX control and raw ADX using Wilder smoothing."""
    size = len(rows)
    plus_dm, minus_dm, true_range = [0.0] * size, [0.0] * size, _true_ranges(rows)
    for index in range(1, size):
        up = float(rows[index]["high"]) - float(rows[index - 1]["high"])
        down = float(rows[index - 1]["low"]) - float(rows[index]["low"])
        plus_dm[index] = up if up > down and up > 0 else 0.0
        minus_dm[index] = down if down > up and down > 0 else 0.0
    plus_di, minus_di, dx = [None] * size, [None] * size, [None] * size
    if size <= period:
        return [None] * size, [None] * size
    tr_sum = sum(true_range[1:period + 1])
    plus_sum = sum(plus_dm[1:period + 1])
    minus_sum = sum(minus_dm[1:period + 1])
    for index in range(period, size):
        if index > period:
            tr_sum = tr_sum - tr_sum / period + true_range[index]
            plus_sum = plus_sum - plus_sum / period + plus_dm[index]
            minus_sum = minus_sum - minus_sum / period + minus_dm[index]
        if tr_sum <= 0:
            continue
        plus_di[index], minus_di[index] = 100 * plus_sum / tr_sum, 100 * minus_sum / tr_sum
        total = plus_di[index] + minus_di[index]
        dx[index] = 100 * abs(plus_di[index] - minus_di[index]) / total if total else 0.0
    adx = [None] * size
    first_adx_index = 2 * period - 1
    initial = [value for value in dx[period:first_adx_index + 1] if value is not None]
    if len(initial) == period:
        adx[first_adx_index] = statistics.fmean(initial)
        for index in range(first_adx_index + 1, size):
            if dx[index] is not None:
                adx[index] = (adx[index - 1] * (period - 1) + dx[index]) / period
    signed = [None] * size
    for index in range(size):
        if adx[index] is None or plus_di[index] is None or minus_di[index] is None:
            continue
        total = plus_di[index] + minus_di[index]
        signed[index] = adx[index] * (plus_di[index] - minus_di[index]) / total if total else 0.0
    return signed, adx


class CandidateSeries:
    """All calculations are addressable by signal date and use no later row."""

    def __init__(self, raw_rows: list[dict]):
        self.rows = adjusted_rows(raw_rows)
        self.base = FeatureSeries(self.rows)
        self.index = self.base.index
        self.closes = self.base.closes
        self.volumes = self.base.volumes
        self.highs = [float(row["high"]) for row in self.rows]
        self.lows = [float(row["low"]) for row in self.rows]
        self.true_ranges = _true_ranges(self.rows)
        self.atr20 = atr(self.rows, 20)
        self.directional_control, self.adx14 = _directional_control(self.rows)
        self.streaks = self._streaks()
        self.streak_rsi2 = rsi(self.streaks, 2)
        self.close_rsi3 = rsi(self.closes, 3)

    def _streaks(self) -> list[float]:
        streaks = [0.0] * len(self.closes)
        for index in range(1, len(self.closes)):
            if self.closes[index] > self.closes[index - 1]:
                streaks[index] = max(1.0, streaks[index - 1] + 1)
            elif self.closes[index] < self.closes[index - 1]:
                streaks[index] = min(-1.0, streaks[index - 1] - 1)
        return streaks

    def _connors_rsi(self, index: int) -> float | None:
        if index < 100 or self.close_rsi3[index] is None or self.streak_rsi2[index] is None:
            return None
        returns = [
            self.closes[position] / self.closes[position - 1] - 1
            for position in range(index - 99, index + 1)
            if self.closes[position - 1] > 0
        ]
        if len(returns) != 100:
            return None
        current = returns[-1]
        percent_rank = 100 * sum(value < current for value in returns) / len(returns)
        return statistics.fmean((self.close_rsi3[index], self.streak_rsi2[index], percent_rank))

    def technical(self, signal_date: str) -> tuple[dict[str, float | None], dict[str, float | None], dict[str, float | None]]:
        index = self.index.get(signal_date)
        empty = {candidate_id: None for candidate_id in CANDIDATES}
        if index is None or index < 200:
            return empty, self.base.technical(signal_date), {"trend.adx_14": None}

        closes20 = self.closes[index - 19:index + 1]
        closes60 = self.closes[index - 59:index + 1]
        log60 = [math.log(value) for value in closes60 if value > 0]
        r_squared, residual = _linear_fit(log60) if len(log60) == 60 else (None, None)

        changes20 = [self.closes[position] - self.closes[position - 1] for position in range(index - 19, index + 1)]
        movement = sum(abs(value) for value in changes20)
        efficiency = abs(self.closes[index] - self.closes[index - 20]) / movement if movement else 0.0

        highs60 = self.highs[index - 59:index + 1]
        maximum = max(highs60)
        most_recent_high = max(position for position, value in enumerate(highs60) if value == maximum)
        days_since_high = len(highs60) - 1 - most_recent_high

        peak20 = max(closes20)
        ulcer = math.sqrt(statistics.fmean((100 * (value / peak20 - 1)) ** 2 for value in closes20)) if peak20 else None

        return_balance = sum(changes20) / movement if movement else 0.0
        price_returns, volume_changes = [], []
        for position in range(index - 19, index + 1):
            prior_close, prior_volume = self.closes[position - 1], self.volumes[position - 1]
            if prior_close > 0 and prior_volume > 0:
                price_returns.append(self.closes[position] / prior_close - 1)
                volume_changes.append(self.volumes[position] / prior_volume - 1)
        return_volume_corr = _pearson(price_returns, volume_changes)

        money_flow, total_volume = 0.0, 0.0
        for position in range(index - 19, index + 1):
            width = self.highs[position] - self.lows[position]
            volume = self.volumes[position]
            multiplier = (2 * self.closes[position] - self.highs[position] - self.lows[position]) / width if width else 0.0
            money_flow += multiplier * volume
            total_volume += volume
        cmf = money_flow / total_volume if total_volume else None

        high14 = max(self.highs[index - 13:index + 1])
        low14 = min(self.lows[index - 13:index + 1])
        tr14 = sum(self.true_ranges[index - 13:index + 1])
        choppiness = (
            100 * math.log10(tr14 / (high14 - low14)) / math.log10(14)
            if high14 > low14 and tr14 > 0 else None
        )

        standard_deviation = statistics.pstdev(closes20)
        bollinger_width = 4 * standard_deviation
        keltner_width = 3 * self.atr20[index] if self.atr20[index] else None
        squeeze_ratio = bollinger_width / keltner_width if keltner_width else None

        values = {
            "trend.kaufman_efficiency_20": efficiency,
            "trend.regression_r2_60": r_squared,
            "location.regression_residual_60": residual,
            "location.days_since_high_60": float(days_since_high),
            "risk.ulcer_index_20": ulcer,
            "pullback.return_balance_20": return_balance,
            "volume.return_volume_corr_20": return_volume_corr,
            "volume.chaikin_money_flow_20": cmf,
            "momentum.connors_rsi_3_2_100": self._connors_rsi(index),
            "regime.choppiness_14": choppiness,
            "volatility.squeeze_ratio_20": squeeze_ratio,
            "trend.directional_control_14": self.directional_control[index],
        }
        if set(values) != set(CANDIDATES):
            raise RuntimeError("Candidate catalog and implementation are out of sync")
        clean = {key: value if finite(value) else None for key, value in values.items()}
        return clean, self.base.technical(signal_date), {"trend.adx_14": self.adx14[index]}

    def trailing_return(self, signal_date: str, sessions: int) -> float | None:
        index = self.index.get(signal_date)
        if index is None or index < sessions or self.closes[index - sessions] <= 0:
            return None
        return self.closes[index] / self.closes[index - sessions] - 1


class CandidateLoader:
    def __init__(self, cache_dir: str | pathlib.Path):
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache: dict[str, CandidateSeries | None] = {}

    def __call__(self, symbol: str) -> CandidateSeries | None:
        if symbol not in self.cache:
            path = self.cache_dir / f"{symbol}.json"
            try:
                raw = json.loads(path.read_text()) if path.exists() else None
                self.cache[symbol] = CandidateSeries(raw) if raw else None
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, statistics.StatisticsError):
                self.cache[symbol] = None
        return self.cache[symbol]
