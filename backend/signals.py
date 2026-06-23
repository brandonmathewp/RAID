"""RAID signals — indicator math library and the Signal dataclass.

brain.py is the sole source of trading decisions. This module provides:
  - Signal dataclass (used by gate.py and executor._claude_override)
  - EMA / RSI / MACD calculation functions (used by brain.py for market context)

Removed in v2: generate_signals(), detect_direction(), score_technical(),
score_kalshi(), adjust_for_news() — all decision logic now lives in brain.py.
"""

import logging
from dataclasses import dataclass

import config
from scanner import ScanResult

log = logging.getLogger("raid.signals")


@dataclass
class Signal:
    """A trade candidate handed to gate.py for risk checks and executor for entry."""

    market: str
    symbol: str
    direction: str          # long / short / yes / no
    confidence: float       # 0.0 – 1.0 (Claude's stated probability)
    technical_score: float  # 0–100 (kept for executor._claude_override shim)
    news_sentiment: str
    news_headline: str
    news_boost: float
    macro_blocked: bool
    block_reason: str
    scan_result: ScanResult


# ── Indicator math (used by brain.py to build asset context) ──────────────

def _ema(values, period):
    """Return the exponential moving average series for the given period."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    out = [ema]
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def _ema_last(values, period):
    """Return the final EMA value for a period, or None if insufficient data."""
    series = _ema(values, period)
    return series[-1] if series else None


def _rsi(closes, period):
    """Return the latest RSI value (0–100) using a Wilder-style average."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _macd(closes):
    """Return (macd_line, signal_line) as series, or ([], []) if insufficient data."""
    if len(closes) < config.MACD_SLOW + config.MACD_SIGNAL:
        return [], []
    fast = _ema(closes, config.MACD_FAST)
    slow = _ema(closes, config.MACD_SLOW)
    offset = len(fast) - len(slow)
    fast = fast[offset:]
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal_line = _ema(macd_line, config.MACD_SIGNAL)
    align = len(macd_line) - len(signal_line)
    return macd_line[align:], signal_line


def _macd_cross(closes):
    """Return 'bullish'/'bearish'/'none' based on the latest MACD/signal crossover."""
    macd_line, signal_line = _macd(closes)
    if len(macd_line) < 2 or len(signal_line) < 2:
        return "none"
    prev_diff = macd_line[-2] - signal_line[-2]
    curr_diff = macd_line[-1] - signal_line[-1]
    if prev_diff <= 0 < curr_diff:
        return "bullish"
    if prev_diff >= 0 > curr_diff:
        return "bearish"
    return "none"
