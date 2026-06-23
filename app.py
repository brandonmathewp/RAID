#!/usr/bin/env python3
"""
RAID v2 — Rapid AI Decision Engine — Single-file consolidated webapp.
All backend modules merged into one file with embedded HTML dashboard.
Uses OpenRouter via OpenAI client instead of Anthropic.
Requires: openai, supabase, python-dotenv, httpx, resend, tzdata
"""

import asyncio
import json
import logging
import signal as signal_module
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import os

import httpx
from dotenv import load_dotenv

# ────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────

_ROOT_ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(_ROOT_ENV)

class Config:
    """RAID configuration — every tunable lives here."""
    BOT_NAME = "RAID"
    STARTING_EQUITY = 4000.0
    FLOOR_TARGET = 155_000.0
    SUPERSONIC_TARGET = 1_000_000.0
    PAPER_MODE = True
    LIVE_DATE = "2026-07-20"
    BOT_LIVE_DATE = "2026-07-20"
    
    BRAIN_CYCLE_MINUTES = 30
    MAX_OPEN_TRADES = 20
    MAX_ENTRIES_PER_CYCLE = 5
    CLAUDE_DAILY_BUDGET_USD = 7.0
    CLAUDE_MODEL = "claude-3.5-sonnet"  # OpenRouter model ID
    
    KELLY_FRACTION_DEFAULT = 0.25
    TARGET_VOLATILITY = 0.15
    MIN_TRADE_SIZE_PCT = 0.005
    MAX_TRADE_SIZE_PCT = 0.05
    MAX_TRADE_SIZE_PCT_BEHIND = 0.07
    HIGH_CONVICTION_THRESHOLD = 0.72
    CRITICAL_CONVICTION_THRESHOLD = 0.78
    
    CORRELATED_PAIRS = [
        ["SOLUSD", "ETHUSD", "BTCUSD", "XRPUSD"],
        ["XLMUSD", "XMRUSD", "XDGUSD"],
    ]
    
    OPERATOR_TZ = "America/Chicago"
    
    DAILY_LOSS_LIMIT_PCT = 0.10
    CONSECUTIVE_LOSS_PAUSE = 3
    CONSECUTIVE_LOSS_PAUSE_MINUTES = 60
    KALSHI_MAX_OPEN = 4
    
    CRYPTO_ENABLED = True
    KALSHI_ENABLED = False
    STOCKS_ENABLED = False
    OPTIONS_ENABLED = False
    COMMODITIES_ENABLED = False
    
    LOOP_SLEEP_SECONDS = 1
    CONSECUTIVE_LOSS_LOOKBACK = 50
    MACRO_PAUSE_MINUTES_BEFORE = 30
    MACRO_RESUME_MINUTES_AFTER = 15
    
    STOP_LOSS_PCT = 0.02
    TAKE_PROFIT_PCT = 0.04
    KALSHI_SL_PCT = 0.50
    KALSHI_TP_PRICE = 0.95
    TRAIL_TRIGGER_PCT = 0.01
    TRAIL_STEP_PCT = 0.005
    ADVERSE_MOVE_PCT = 0.02
    
    EOD_CLOSE_HOUR = 16
    EOD_CLOSE_TZ = "America/New_York"
    
    # OpenRouter pricing (claude-3.5-sonnet via OpenRouter)
    CLAUDE_INPUT_COST_PER_TOKEN = 0.000003
    CLAUDE_OUTPUT_COST_PER_TOKEN = 0.000015
    CLAUDE_BUDGET_ALERT_AT = 6.0
    
    KRAKEN_OHLC_INTERVAL = 5
    KRAKEN_MAX_PAIRS = 25
    OHLCV_CANDLES = 300
    KRAKEN_QUOTES = ("ZUSD", "USD")
    MIN_24H_USD_VOLUME = 1_000_000
    KRAKEN_TICKER_CHUNK = 200
    KALSHI_CLOSE_WITHIN_HOURS = 24
    NEWS_LOOKBACK_HOURS = 2
    NEWS_TOP_N = 3
    HTTP_TIMEOUT = 20.0
    BULLISH_WORDS = (
        "surge", "rally", "breakout", "bullish", "buy", "up", "gain", "rise", "positive",
    )
    BEARISH_WORDS = (
        "crash", "drop", "bearish", "sell", "down", "loss", "fall", "decline", "negative", "fear",
    )
    
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    EMA_FAST = 20
    EMA_MID = 50
    EMA_SLOW = 200
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    VOLUME_CONFIRM_MULT = 1.5
    
    LEARNING_ENABLED = False
    LEARNING_INTERVAL_DAYS = 7
    LEARNING_MIN_SAMPLE = 50
    LEARNING_LOW_WIN_RATE = 0.40
    LEARNING_HIGH_WIN_RATE = 0.65
    LEARNING_WEIGHT_DOWN = 0.8
    LEARNING_WEIGHT_UP = 1.2
    
    HEALTH_CHECK_PORT = 8080
    BASE_TRADE_SIZE = 100.0
    RISK_REWARD_RATIO = 2.0
    MIN_CONFIDENCE = 0.50
    CLAUDE_GRAY_ZONE_MIN = 0.70
    CLAUDE_GRAY_ZONE_MAX = 0.80
    CLAUDE_SKIP_THRESHOLD = 0.85
    KILL_SWITCH_ACTIVE = False
    PULLBACK_BAND_PCT = 0.01
    PULLBACK_LOOKBACK = 12
    PULLBACK_MIN_BOUNCE = 0.005
    RSI_LONG_BAND_LOW = 45.0
    RSI_LONG_BAND_HIGH = 60.0
    RSI_SHORT_BAND_LOW = 40.0
    RSI_SHORT_BAND_HIGH = 55.0
    TS_RSI_WEIGHT = 25.0
    TS_MACD_WEIGHT = 25.0
    TS_EMA_STRONG = 50.0
    TS_EMA_MIXED = 15.0
    TS_VOLUME_WEIGHT = 10.0
    TS_RSI_PENALTY = 15.0
    KALSHI_YES_LOW = 0.30
    KALSHI_YES_HIGH = 0.70
    KALSHI_SKIP_LOW = 0.35
    KALSHI_SKIP_HIGH = 0.65
    KALSHI_BASE_CONF = 0.75
    KALSHI_VOLUME_BOOST_THRESHOLD = 10000
    KALSHI_VOLUME_BOOST = 0.05
    KALSHI_TIME_URGENCY_HOURS = 2
    KALSHI_TIME_BOOST = 0.05
    CONFIDENCE_CAP = 0.95
    NEWS_BOOST_ALIGNED = 0.05
    NEWS_PENALTY_OPPOSED = 0.10
    NEWS_BLOCK_FLOOR = 0.60
    CONF_MULT = {0.70: 1.0, 0.80: 1.2, 0.90: 1.5, 1.00: 2.0}
    EQUITY_TIER_MULT = [(5000, 1.0), (20000, 1.5), (50000, 2.0), (float("inf"), 3.0)]
    CRYPTO_SCAN_INTERVAL = BRAIN_CYCLE_MINUTES * 60
    KALSHI_SCAN_INTERVAL = BRAIN_CYCLE_MINUTES * 60
    
    # API keys
    KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
    KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET")
    KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Changed from ANTHROPIC_API_KEY
    NEWS_API_KEY = os.getenv("NEWS_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    OPERATOR_EMAIL = os.getenv("OPERATOR_EMAIL", "aasghar311@gmail.com")
    
    _REQUIRED_KEYS = (
        "KRAKEN_API_KEY",
        "KRAKEN_API_SECRET",
        "OPENROUTER_API_KEY",  # Changed from ANTHROPIC_API_KEY
        "NEWS_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    )
    
    @classmethod
    def validate(cls):
        for key in cls._REQUIRED_KEYS:
            if not getattr(cls, key, None):
                raise ValueError(f"Missing required config key: {key}")
        return True

config = Config()

# ────────────────────────────────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("raid")

# ────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    market: str
    symbol: str
    ohlcv: list = field(default_factory=list)
    current_price: float = 0.0
    yes_price: float = None
    no_price: float = None
    volume_24h: float = None
    resolution_time: str = None
    market_id: str = None
    news_headline: str = None
    news_sentiment: str = "neutral"
    news_published: str = None
    macro_event_imminent: bool = False
    macro_event_name: str = None
    macro_minutes_until: int = None
    scan_time: str = None
    error: str = None

@dataclass
class Signal:
    market: str
    symbol: str
    direction: str
    confidence: float
    technical_score: float
    news_sentiment: str
    news_headline: str
    news_boost: float
    macro_blocked: bool
    block_reason: str
    scan_result: ScanResult

@dataclass
class TradeResult:
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    size_usd: float
    sl: float
    tp: float
    status: str
    paper_mode: bool

@dataclass
class GateResult:
    passed: bool
    reason: str

@dataclass
class BrainResult:
    decision: str
    confidence: float

# ────────────────────────────────────────────────────────────────────────────
# OPENAI CLIENT (for OpenRouter)
# ────────────────────────────────────────────────────────────────────────────

from openai import AsyncOpenAI

_openai_client = AsyncOpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# ────────────────────────────────────────────────────────────────────────────
# DATABASE (Async Supabase)
# ────────────────────────────────────────────────────────────────────────────

supabase = None

async def db_init():
    global supabase
    if supabase is None:
        from supabase import acreate_client
        supabase = await acreate_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return supabase

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

async def db_get_equity():
    try:
        res = await (
            supabase.table("equity_snapshots")
            .select("equity")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return float(res.data[0]["equity"])
    except Exception as exc:
        log.error("get_equity failed: %s", exc)
    return config.STARTING_EQUITY

async def db_update_equity(equity: float, daily_pnl: float):
    try:
        await supabase.table("equity_snapshots").insert({
            "equity": equity,
            "daily_pnl": daily_pnl,
            "paper_mode": config.PAPER_MODE
        }).execute()
    except Exception as exc:
        log.error("update_equity failed: %s", exc)

async def db_log_trade(trade: dict):
    try:
        res = await supabase.table("trades").insert(trade).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as exc:
        log.error("log_trade failed: %s", exc)
    return ""

async def db_close_trade(trade_id: str, exit_price: float, pnl: float, reason: str):
    try:
        await supabase.table("trades").update({
            "status": "closed",
            "exit_price": exit_price,
            "pnl": pnl,
            "close_time": _now_iso(),
            "close_reason": reason,
        }).eq("id", trade_id).execute()
    except Exception as exc:
        log.error("close_trade failed: %s", exc)

async def db_get_open_trades():
    try:
        res = await supabase.table("trades").select("*").eq("status", "open").execute()
        return res.data or []
    except Exception as exc:
        log.error("get_open_trades failed: %s", exc)
        return []

async def db_get_open_trades_by_market(market: str):
    try:
        res = await supabase.table("trades").select("*").eq("status", "open").eq("market", market).execute()
        return res.data or []
    except Exception as exc:
        log.error("get_open_trades_by_market failed: %s", exc)
        return []

async def db_get_closed_trades_last_n(n: int):
    try:
        res = await supabase.table("trades").select("*").eq("status", "closed").order("close_time", desc=True).limit(n).execute()
        return res.data or []
    except Exception as exc:
        log.error("get_closed_trades_last_n failed: %s", exc)
        return []

async def db_get_consecutive_losses():
    try:
        res = await supabase.table("trades").select("pnl").eq("status", "closed").order("close_time", desc=True).limit(config.CONSECUTIVE_LOSS_LOOKBACK).execute()
        count = 0
        for row in res.data or []:
            if (row.get("pnl") or 0) < 0:
                count += 1
            else:
                break
        return count
    except Exception as exc:
        log.error("get_consecutive_losses failed: %s", exc)
        return 0

async def db_get_last_loss_time():
    try:
        res = await supabase.table("trades").select("close_time").eq("status", "closed").lt("pnl", 0).order("close_time", desc=True).limit(1).execute()
        if res.data and res.data[0].get("close_time"):
            return datetime.fromisoformat(res.data[0]["close_time"].replace("Z", "+00:00"))
    except Exception as exc:
        log.error("get_last_loss_time failed: %s", exc)
    return None

async def db_get_kill_switch():
    try:
        res = await supabase.table("kill_switch").select("active").order("activated_at", desc=True).limit(1).execute()
        if res.data:
            return bool(res.data[0]["active"])
    except Exception as exc:
        log.error("get_kill_switch failed: %s", exc)
    return config.KILL_SWITCH_ACTIVE

async def db_get_kill_switch_record():
    try:
        res = await supabase.table("kill_switch").select("*").order("activated_at", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception as exc:
        log.error("get_kill_switch_record failed: %s", exc)
    return {}

async def db_set_kill_switch(active: bool, reason: str, activated_by: str):
    try:
        await supabase.table("kill_switch").insert({
            "active": active,
            "reason": reason,
            "activated_at": _now_iso(),
            "activated_by": activated_by,
        }).execute()
    except Exception as exc:
        log.error("set_kill_switch failed: %s", exc)

async def db_get_operator_controls():
    defaults = {
        "kill_switch": False,
        "pause_entries": False,
        "emergency_close": False,
        "max_open_trades": config.MAX_OPEN_TRADES,
        "max_position_pct": config.MAX_TRADE_SIZE_PCT,
        "brain_cycle_minutes": config.BRAIN_CYCLE_MINUTES,
        "crypto_enabled": True,
        "stocks_enabled": False,
        "kalshi_enabled": False,
        "options_enabled": False,
        "daily_loss_limit_pct": config.DAILY_LOSS_LIMIT_PCT,
        "alert_on_loss_pct": 0.05,
        "operator_note": None,
    }
    try:
        res = await supabase.table("operator_controls").select("*").order("updated_at", desc=True).limit(1).execute()
        if res.data:
            row = res.data[0]
            defaults.update({k: v for k, v in row.items() if v is not None})
            return defaults
    except Exception as exc:
        log.error("get_operator_controls failed: %s", exc)
    return defaults

async def db_update_operator_controls(updates: dict) -> bool:
    try:
        updates["updated_at"] = _now_iso()
        res = await supabase.table("operator_controls").select("id").limit(1).execute()
        if not res.data:
            log.error("update_operator_controls: no operator_controls row to update")
            return False
        row_id = res.data[0]["id"]
        upd = await supabase.table("operator_controls").update(updates).eq("id", row_id).execute()
        return bool(upd.data)
    except Exception as exc:
        log.error("update_operator_controls failed: %s", exc)
        return False

async def db_get_daily_stats(date: str):
    try:
        res = await supabase.table("daily_stats").select("*").eq("date", date).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception as exc:
        log.error("get_daily_stats failed: %s", exc)
    return {}

async def db_log_signal(signal: dict):
    try:
        res = await supabase.table("signals").insert(signal).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as exc:
        log.error("log_signal failed: %s", exc)
    return ""

# ────────────────────────────────────────────────────────────────────────────
# SCANNER (Market data)
# ────────────────────────────────────────────────────────────────────────────

KRAKEN_BASE = "https://api.kraken.com/0/public"
NEWS_BASE = "https://newsapi.org/v2/everything"

MACRO_EVENTS = [
    (datetime(2026, 7, 10, 12, 30, tzinfo=timezone.utc), "CPI"),
    (datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc), "FOMC Decision"),
]

def _now_iso_scanner():
    return datetime.now(timezone.utc).isoformat()

async def scan_kraken():
    results = []
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            pairs_res = await client.get(f"{KRAKEN_BASE}/AssetPairs")
            pairs_data = pairs_res.json().get("result", {})
            candidates = {}
            for pair_key, info in pairs_data.items():
                if info.get("quote") in config.KRAKEN_QUOTES and info.get("altname"):
                    candidates[info["altname"]] = pair_key
            if not candidates:
                return results
            canon_to_alt = {canon: alt for alt, canon in candidates.items()}
            prices = {}
            volumes = {}
            altnames = list(candidates)
            for i in range(0, len(altnames), config.KRAKEN_TICKER_CHUNK):
                chunk = altnames[i : i + config.KRAKEN_TICKER_CHUNK]
                try:
                    tick_res = await client.get(f"{KRAKEN_BASE}/Ticker", params={"pair": ",".join(chunk)})
                    tick_data = tick_res.json().get("result", {})
                    for canon, t in tick_data.items():
                        alt = canon_to_alt.get(canon, canon)
                        try:
                            prices[alt] = float(t["c"][0])
                            volumes[alt] = float(t["v"][1]) * float(t["p"][1])
                        except (KeyError, IndexError, TypeError, ValueError):
                            continue
                except Exception as exc:
                    log.error("Kraken Ticker chunk failed: %s", exc)
                    continue
            liquid = sorted(
                (a for a in candidates if volumes.get(a, 0.0) >= config.MIN_24H_USD_VOLUME),
                key=lambda a: volumes.get(a, 0.0),
                reverse=True,
            )[: config.KRAKEN_MAX_PAIRS]
            if not liquid:
                log.warning("No Kraken pairs above $%.0f 24h volume", config.MIN_24H_USD_VOLUME)
                return results
            for altname in liquid:
                try:
                    ohlc_res = await client.get(
                        f"{KRAKEN_BASE}/OHLC",
                        params={"pair": altname, "interval": config.KRAKEN_OHLC_INTERVAL},
                    )
                    ohlc_data = ohlc_res.json().get("result", {})
                    candles = []
                    for k, v in ohlc_data.items():
                        if k == "last":
                            continue
                        candles = v
                        break
                    ohlcv = [
                        [c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])]
                        for c in candles[-config.OHLCV_CANDLES:]
                    ]
                    current = prices.get(altname)
                    if current is None and ohlcv:
                        current = ohlcv[-1][4]
                    results.append(ScanResult(
                        market="crypto",
                        symbol=altname,
                        ohlcv=ohlcv,
                        current_price=current or 0.0,
                        volume_24h=volumes.get(altname),
                        scan_time=_now_iso_scanner(),
                    ))
                except Exception as exc:
                    log.error("Kraken OHLC failed for %s: %s", altname, exc)
                    continue
    except Exception as exc:
        log.error("scan_kraken failed: %s", exc)
    return results

def _score_sentiment(text: str):
    lowered = (text or "").lower()
    bull = sum(lowered.count(w) for w in config.BULLISH_WORDS)
    bear = sum(lowered.count(w) for w in config.BEARISH_WORDS)
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"

async def scan_news(symbols):
    out = {}
    if not symbols:
        return out
    from_dt = (datetime.now(timezone.utc) - timedelta(hours=config.NEWS_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            for symbol in symbols:
                try:
                    res = await client.get(
                        NEWS_BASE,
                        params={
                            "q": symbol,
                            "sortBy": "publishedAt",
                            "from": from_dt,
                            "pageSize": config.NEWS_TOP_N,
                            "language": "en",
                            "apiKey": config.NEWS_API_KEY,
                        },
                    )
                    articles = res.json().get("articles", [])[: config.NEWS_TOP_N]
                    if not articles:
                        out[symbol] = {"headline": None, "sentiment": "neutral", "published_at": None}
                        continue
                    combined = " ".join(
                        f"{a.get('title', '')} {a.get('description', '')}" for a in articles
                    )
                    out[symbol] = {
                        "headline": articles[0].get("title"),
                        "sentiment": _score_sentiment(combined),
                        "published_at": articles[0].get("publishedAt"),
                    }
                except Exception as exc:
                    log.error("scan_news failed for %s: %s", symbol, exc)
                    out[symbol] = {"headline": None, "sentiment": "neutral", "published_at": None}
    except Exception as exc:
        log.error("scan_news failed: %s", exc)
    return out

def check_macro_events():
    try:
        now = datetime.now(timezone.utc)
        for event_dt, name in MACRO_EVENTS:
            delta_min = int((event_dt - now).total_seconds() // 60)
            if 0 <= delta_min <= config.MACRO_PAUSE_MINUTES_BEFORE:
                return True, name, delta_min
            if -config.MACRO_RESUME_MINUTES_AFTER <= delta_min < 0:
                return True, name, delta_min
    except Exception as exc:
        log.error("check_macro_events failed: %s", exc)
    return False, None, None

async def fetch_kraken_price(symbol: str):
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            res = await client.get(f"{KRAKEN_BASE}/Ticker", params={"pair": symbol})
            data = res.json().get("result", {})
            for _, t in data.items():
                return float(t["c"][0])
    except Exception as exc:
        log.error("fetch_kraken_price failed for %s: %s", symbol, exc)
    return None

_KRAKEN_PAIR_MAP = {}

async def _kraken_pair_map(client):
    global _KRAKEN_PAIR_MAP
    if _KRAKEN_PAIR_MAP:
        return _KRAKEN_PAIR_MAP
    try:
        res = await client.get(f"{KRAKEN_BASE}/AssetPairs")
        data = res.json().get("result", {})
        _KRAKEN_PAIR_MAP = {
            info["altname"]: key for key, info in data.items() if info.get("altname")
        }
    except Exception as exc:
        log.error("_kraken_pair_map failed: %s", exc)
    return _KRAKEN_PAIR_MAP

async def fetch_kraken_prices(symbols):
    out = {}
    syms = [s for s in dict.fromkeys(symbols) if s]
    if not syms:
        return out
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            res = await client.get(f"{KRAKEN_BASE}/Ticker", params={"pair": ",".join(syms)})
            result = res.json().get("result", {})
            pair_map = await _kraken_pair_map(client)
            for sym in syms:
                canonical = pair_map.get(sym, sym)
                t = result.get(canonical) or result.get(sym)
                if t is None:
                    t = next((v for k, v in result.items() if sym in k), None)
                if t is None:
                    continue
                try:
                    out[sym] = float(t["c"][0])
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
    except Exception as exc:
        log.error("fetch_kraken_prices failed: %s", exc)
    return out

# ────────────────────────────────────────────────────────────────────────────
# SIGNALS & INDICATORS
# ────────────────────────────────────────────────────────────────────────────

def _ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    out = [ema]
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out

def _rsi(closes, period):
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

# ────────────────────────────────────────────────────────────────────────────
# EXECUTOR (Position sizing, SL/TP, entry)
# ────────────────────────────────────────────────────────────────────────────

def calculate_size(confidence: float, equity: float):
    keys = sorted(config.CONF_MULT)
    if confidence <= keys[0]:
        conf_mult = config.CONF_MULT[keys[0]]
    elif confidence >= keys[-1]:
        conf_mult = config.CONF_MULT[keys[-1]]
    else:
        conf_mult = config.CONF_MULT[keys[0]]
        for i in range(len(keys) - 1):
            lo, hi = keys[i], keys[i + 1]
            if lo <= confidence <= hi:
                frac = (confidence - lo) / (hi - lo)
                conf_mult = config.CONF_MULT[lo] + frac * (config.CONF_MULT[hi] - config.CONF_MULT[lo])
                break
    tier_mult = config.EQUITY_TIER_MULT[-1][1]
    for threshold, mult in config.EQUITY_TIER_MULT:
        if equity < threshold:
            tier_mult = mult
            break
    return config.BASE_TRADE_SIZE * conf_mult * tier_mult

def calculate_sl_tp(entry: float, direction: str):
    if direction == "long":
        return entry * (1 - config.STOP_LOSS_PCT), entry * (1 + config.TAKE_PROFIT_PCT)
    if direction == "short":
        return entry * (1 + config.STOP_LOSS_PCT), entry * (1 - config.TAKE_PROFIT_PCT)
    return entry * (1 - config.STOP_LOSS_PCT), entry * (1 + config.TAKE_PROFIT_PCT)

def compute_pnl(direction: str, entry: float, exit_price: float, size_usd: float):
    if entry <= 0:
        return 0.0
    KRAKEN_TAKER_FEE_PCT = 0.0016
    fee_cost = size_usd * KRAKEN_TAKER_FEE_PCT * 2
    if direction in ("long", "yes"):
        gross_pnl = size_usd * (exit_price - entry) / entry
    else:
        gross_pnl = size_usd * (entry - exit_price) / entry
    return gross_pnl - fee_cost

async def execute_trade(signal: Signal):
    try:
        equity = await db_get_equity()
        size_usd = calculate_size(signal.confidence, equity)
        entry = signal.scan_result.current_price or 0.0
        sl, tp = calculate_sl_tp(entry, signal.direction)
        trade = {
            "bot_name": config.BOT_NAME,
            "market": signal.market,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": entry,
            "size_usd": size_usd,
            "confidence": signal.confidence,
            "pnl": 0,
            "status": "open",
            "close_reason": None,
            "paper_mode": config.PAPER_MODE,
            "sl": sl,
            "tp": tp,
        }
        trade_id = await db_log_trade(trade)
        log.info(
            "TRADE OPEN %s %s %s size=$%.2f entry=%.5f sl=%.5f tp=%.5f conf=%.2f (%s)",
            signal.market, signal.symbol, signal.direction, size_usd, entry, sl, tp,
            signal.confidence, "PAPER" if config.PAPER_MODE else "LIVE",
        )
        return TradeResult(trade_id, signal.symbol, signal.direction, entry, size_usd, sl, tp, "open", config.PAPER_MODE)
    except Exception as exc:
        log.error("execute_trade failed for %s: %s", signal.symbol, exc)
        return TradeResult("", signal.symbol, signal.direction, 0.0, 0.0, 0.0, 0.0, "error", config.PAPER_MODE)

def _sl_tp_hit(direction: str, price: float, sl: float, tp: float):
    long_like = direction in ("long", "yes")
    if long_like:
        if sl is not None and price <= sl:
            return "stop_loss"
        if tp is not None and price >= tp:
            return "take_profit"
    else:
        if sl is not None and price >= sl:
            return "stop_loss"
        if tp is not None and price <= tp:
            return "take_profit"
    return None

async def monitor_positions():
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        if config.PAPER_MODE and today >= config.BOT_LIVE_DATE:
            config.PAPER_MODE = False
            log.warning("RAID GOING LIVE — %s", datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        log.error("auto-flip check failed: %s", exc)
    try:
        open_trades = await db_get_open_trades()
    except Exception as exc:
        log.error("monitor_positions could not load open trades: %s", exc)
        return
    crypto_symbols = [
        t["symbol"] for t in open_trades if t.get("market") == "crypto" and t.get("symbol")
    ]
    crypto_prices = await fetch_kraken_prices(crypto_symbols) if crypto_symbols else {}
    for trade in open_trades:
        try:
            symbol = trade.get("symbol")
            if symbol in crypto_prices:
                price = crypto_prices[symbol]
            else:
                price = await fetch_kraken_price(symbol) if symbol else None
            if price is None or price <= 0:
                continue
            direction = trade.get("direction")
            entry = trade.get("entry_price") or 0
            sl = trade.get("sl")
            tp = trade.get("tp")
            hit = _sl_tp_hit(direction, price, sl, tp)
            if hit:
                pnl = compute_pnl(direction, entry, price, trade.get("size_usd") or 0)
                await db_close_trade(trade["id"], price, pnl, hit)
                log.info("TRADE CLOSE %s %s reason=%s pnl=$%.2f", trade["market"], trade["symbol"], hit, pnl)
        except Exception as exc:
            log.error("monitor_positions failed for trade %s: %s", trade.get("id"), exc)
            continue

# ────────────────────────────────────────────────────────────────────────────
# GATE (Risk checks)
# ────────────────────────────────────────────────────────────────────────────

async def check_gate(signal: Signal) -> GateResult:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        if await db_get_kill_switch():
            return GateResult(False, "kill_switch_active")
    except Exception as exc:
        log.error("gate kill-switch check failed: %s", exc)
    try:
        equity = await db_get_equity()
        daily_loss_limit = equity * config.DAILY_LOSS_LIMIT_PCT
        stats = await db_get_daily_stats(today)
        if stats and abs(min(stats.get("pnl", 0) or 0, 0)) >= daily_loss_limit:
            await db_set_kill_switch(True, f"Daily loss limit hit: ${abs(stats.get('pnl', 0)):.2f}", "gate_auto")
            return GateResult(False, "daily_loss_limit")
    except Exception as exc:
        log.error("gate daily-loss check failed: %s", exc)
    try:
        consec = await db_get_consecutive_losses()
        if consec >= config.CONSECUTIVE_LOSS_PAUSE:
            last_loss = await db_get_last_loss_time()
            if last_loss is not None:
                elapsed_min = (datetime.now(timezone.utc) - last_loss).total_seconds() / 60
                if elapsed_min < config.CONSECUTIVE_LOSS_PAUSE_MINUTES:
                    return GateResult(False, f"consecutive_loss_pause_{consec}_losses")
    except Exception as exc:
        log.error("gate consecutive-loss check failed: %s", exc)
    try:
        open_trades = await db_get_open_trades()
        if len(open_trades) >= config.MAX_OPEN_TRADES:
            return GateResult(False, "max_open_trades")
        for t in open_trades:
            if t.get("symbol") == signal.symbol and t.get("direction") == signal.direction:
                return GateResult(False, f"duplicate_{signal.symbol}_{signal.direction}")
    except Exception as exc:
        log.error("gate max-open check failed: %s", exc)
    return GateResult(True, "all_checks_passed")

# ────────────────────────────────────────────────────────────────────────────
# BRAIN (Trading decisions via OpenRouter/Claude)
# ────────────────────────────────────────────────────────────────────────────

_daily_spend = 0.0

def reset_daily_spend():
    global _daily_spend
    _daily_spend = 0.0

def get_daily_spend():
    return _daily_spend

async def call_openrouter(system_prompt: str, user_prompt: str) -> tuple[dict | None, float]:
    """Call OpenRouter Claude API and return (parsed_json, cost_usd)."""
    global _daily_spend
    
    try:
        response = await _openai_client.chat.completions.create(
            model="anthropic/claude-3.5-sonnet",  # OpenRouter model identifier
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4096,
        )
        
        raw = response.choices[0].message.content
        cost = (
            response.usage.prompt_tokens * config.CLAUDE_INPUT_COST_PER_TOKEN +
            response.usage.completion_tokens * config.CLAUDE_OUTPUT_COST_PER_TOKEN
        )
        _daily_spend += cost
        
        log.info(
            "BRAIN OPENROUTER CALL — in=%d out=%d cost=$%.4f total_today=$%.4f",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            cost,
            _daily_spend,
        )
        
        # Parse JSON response (basic extraction)
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                return parsed, cost
            except json.JSONDecodeError:
                log.error("Failed to parse OpenRouter response as JSON")
                return None, cost
        return None, cost
    except Exception as exc:
        log.error("OpenRouter call failed: %s", exc)
        return None, 0.0

async def run_brain_cycle(scan_results, news_by_symbol):
    log.info("── Brain cycle start ──")
    try:
        for r in scan_results:
            try:
                info = news_by_symbol.get(r.symbol)
                if info:
                    r.news_headline = info.get("headline")
                    r.news_sentiment = info.get("sentiment", "neutral")
                log.debug("Evaluated %s in brain cycle", r.symbol)
            except Exception as exc:
                log.error("Brain eval failed for %s: %s", r.symbol, exc)
    except Exception as exc:
        log.error("run_brain_cycle failed: %s", exc)

# ────────────────────────────────────────────────────────────────────────────
# WORKER (Main event loop)
# ────────────────────────────────────────────────────────────────────────────

STATE = {
    "equity": config.STARTING_EQUITY,
    "daily_pnl": 0.0,
    "open_trades": 0,
    "kill_switch": False,
    "last_cycle": None,
    "trajectory_status": "ON_TRACK",
    "ai_spend_today": 0.0,
    "start_time": time.time(),
}

_shutdown = asyncio.Event()
_emergency_alerted = False
EMERGENCY_CHECK_SECONDS = 3
CDT = ZoneInfo("America/Chicago")

async def _handle_emergency_close():
    global _emergency_alerted
    log.warning("OPERATOR: EMERGENCY CLOSE triggered")
    equity = await db_get_equity()
    open_trades = await db_get_open_trades()
    crypto_symbols = [t["symbol"] for t in open_trades if t.get("market") == "crypto" and t.get("symbol")]
    prices = await fetch_kraken_prices(crypto_symbols) if crypto_symbols else {}
    closed = 0
    for trade in open_trades:
        try:
            price = prices.get(trade.get("symbol"))
            if price is None or price <= 0:
                price = trade.get("entry_price") or 0
            pnl = compute_pnl(trade.get("direction"), trade.get("entry_price") or 0, price, trade.get("size_usd") or 0)
            await db_close_trade(trade["id"], price, pnl, "emergency_close")
            closed += 1
        except Exception as exc:
            log.error("Emergency close failed for %s: %s", trade.get("id"), exc)
    cleared = await db_update_operator_controls({"emergency_close": False, "kill_switch": True})
    if not cleared:
        log.error("EMERGENCY: failed to clear emergency_close flag — needs manual DB fix")
    if not _emergency_alerted:
        _emergency_alerted = True
    log.warning("OPERATOR: EMERGENCY CLOSE complete — %d positions closed", closed)

async def _exit_monitor_loop():
    global _emergency_alerted
    last_safety_check = 0.0
    while not _shutdown.is_set():
        try:
            now = time.time()
            if now - last_safety_check >= EMERGENCY_CHECK_SECONDS:
                controls = await db_get_operator_controls()
                if controls.get("emergency_close"):
                    await _handle_emergency_close()
                else:
                    _emergency_alerted = False
                last_safety_check = now
            await monitor_positions()
        except Exception as exc:
            log.error("exit monitor loop error: %s", exc)
        await asyncio.sleep(config.LOOP_SLEEP_SECONDS)

async def _brain_entry_gate(controls: dict) -> bool:
    if controls.get("kill_switch"):
        log.info("OPERATOR: kill_switch active — no brain entries this cycle")
        return False
    if controls.get("pause_entries"):
        log.info("OPERATOR: pause_entries active — monitoring only, no new trades")
        return False
    return True

async def _run_brain_cycle(controls: dict):
    log.info("── Brain cycle start ──")
    try:
        if not controls.get("crypto_enabled", True):
            log.info("WORKER: crypto disabled by operator_controls — skipping")
            return
        scan_results = await scan_kraken()
        if not scan_results:
            log.warning("WORKER: scan_kraken returned no results")
            return
        symbols = [r.symbol for r in scan_results]
        news_by_symbol = await scan_news(symbols)
        await run_brain_cycle(scan_results, news_by_symbol)
    except Exception as exc:
        log.error("_run_brain_cycle failed: %s", exc)

async def _brain_loop():
    last_brain_cycle = 0.0
    while not _shutdown.is_set():
        try:
            now = time.time()
            controls = await db_get_operator_controls()
            brain_cycle_secs = int(controls.get("brain_cycle_minutes") or config.BRAIN_CYCLE_MINUTES) * 60
            if (now - last_brain_cycle) >= brain_cycle_secs:
                if await _brain_entry_gate(controls):
                    await _run_brain_cycle(controls)
                last_brain_cycle = now
        except Exception as exc:
            log.error("brain loop error: %s", exc)
        await asyncio.sleep(5)

async def _periodic_loop():
    last_alert_check = 0.0
    while not _shutdown.is_set():
        try:
            now = time.time()
            now_dt = datetime.now(timezone.utc)
            if (now - last_alert_check) >= 900:
                STATE["equity"] = await db_get_equity()
                open_trades = await db_get_open_trades()
                STATE["open_trades"] = len(open_trades)
                STATE["kill_switch"] = await db_get_kill_switch()
                STATE["ai_spend_today"] = get_daily_spend()
                STATE["last_cycle"] = now_dt.isoformat()
                today_str = now_dt.date().isoformat()
                if config.PAPER_MODE and today_str >= config.LIVE_DATE:
                    config.PAPER_MODE = False
                    log.warning("RAID GOING LIVE — %s", now_dt.isoformat())
                last_alert_check = now
        except Exception as exc:
            log.error("periodic loop error: %s", exc)
        await asyncio.sleep(15)

def _health_payload():
    return {
        "status": "online",
        "bot": config.BOT_NAME,
        "mode": "paper" if config.PAPER_MODE else "live",
        "equity": STATE["equity"],
        "daily_pnl": STATE["daily_pnl"],
        "open_trades": STATE["open_trades"],
        "kill_switch": STATE["kill_switch"],
        "trajectory_status": STATE["trajectory_status"],
        "ai_spend_today": STATE["ai_spend_today"],
        "last_cycle": STATE["last_cycle"],
        "uptime_seconds": int(time.time() - STATE["start_time"]),
    }

async def _handle_health_conn(reader, writer):
    try:
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, asyncio.LimitOverrunError):
            pass
        body = json.dumps(_health_payload()).encode("utf-8")
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        writer.write(response)
        await writer.drain()
    except Exception as exc:
        log.error("health request failed: %s", exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def start_health_server():
    server = await asyncio.start_server(
        _handle_health_conn, "0.0.0.0", config.HEALTH_CHECK_PORT
    )
    log.info("Health server listening on :%d", config.HEALTH_CHECK_PORT)
    return server

# ────────────────────────────────────────────────────────────────────────────
# EMBEDDED DASHBOARD HTML (Static endpoint)
# ────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>RAID · Trading Dashboard</title>
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
    :root {
      --bg:       #07070f;
      --surface:  #0e0e1c;
      --border:   #18182c;
      --text:     #d8d8ee;
      --muted:    #444460;
      --faint:    #1e1e30;
      --green:    #00e87a;
      --red:      #ff3d5a;
      --purple:   #7c6eff;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
      font-size: 14px;
      line-height: 1.5;
      min-height: 100vh;
    }
    .header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 14px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .logo {
      font-size: 20px;
      font-weight: 900;
      color: var(--purple);
      text-transform: uppercase;
    }
    .main {
      max-width: 1440px;
      margin: 0 auto;
      padding: 28px;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 14px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
    }
    .stat-label {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .stat-value {
      font-size: 24px;
      font-weight: 800;
      color: var(--text);
    }
    .section {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 20px;
    }
    .section-head {
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      font-size: 11px;
    }
    .empty {
      padding: 36px;
      text-align: center;
      color: var(--faint);
    }
  </style>
</head>
<body>
<div class="header">
  <div class="logo">RAID</div>
  <div>Dashboard (OpenRouter/Claude via OpenAI)</div>
</div>
<div class="main">
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Equity</div>
      <div class="stat-value" id="sEquity">$4,000.00</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Open Positions</div>
      <div class="stat-value" id="sOpen">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Kill Switch</div>
      <div class="stat-value" id="sKill">OFF</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Mode</div>
      <div class="stat-value" id="sMode">PAPER</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Uptime</div>
      <div class="stat-value" id="sUptime">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Last Cycle</div>
      <div class="stat-value" id="sLast">--</div>
    </div>
  </div>
  <div class="section">
    <div class="section-head">Health Status</div>
    <div class="empty" id="healthData">Loading...</div>
  </div>
</div>
<script>
  async function updateDashboard() {
    try {
      const res = await fetch('/health');
      const data = await res.json();
      document.getElementById('sEquity').textContent = '$' + data.equity.toFixed(2);
      document.getElementById('sOpen').textContent = data.open_trades;
      document.getElementById('sKill').textContent = data.kill_switch ? 'ON' : 'OFF';
      document.getElementById('sMode').textContent = data.mode.toUpperCase();
      document.getElementById('sUptime').textContent = data.uptime_seconds + 's';
      document.getElementById('sLast').textContent = data.last_cycle ? new Date(data.last_cycle).toLocaleTimeString() : '--';
      document.getElementById('healthData').textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      document.getElementById('healthData').textContent = 'Error: ' + e.message;
    }
  }
  updateDashboard();
  setInterval(updateDashboard, 15000);
</script>
</body>
</html>
"""

# ────────────────────────────────────────────────────────────────────────────
# HTTP SERVER (for dashboard and health endpoints)
# ────────────────────────────────────────────────────────────────────────────

async def handle_request(reader, writer):
    try:
        request_line = (await reader.readline()).decode('utf-8').strip()
        headers = {}
        while True:
            line = (await reader.readline()).decode('utf-8').strip()
            if not line:
                break
            if ':' in line:
                key, val = line.split(':', 1)
                headers[key.strip()] = val.strip()
        method, path, _ = request_line.split()
        if path == '/health' or path == '/api/health':
            body = json.dumps(_health_payload()).encode('utf-8')
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        elif path == '/' or path == '/dashboard':
            body = DASHBOARD_HTML.encode('utf-8')
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        else:
            response = b"HTTP/1.1 404 Not Found\r\n\r\n"
        writer.write(response)
        await writer.drain()
    except Exception as exc:
        log.error("HTTP request failed: %s", exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def start_http_server(port=5000):
    server = await asyncio.start_server(handle_request, "0.0.0.0", port)
    log.info("HTTP server listening on :%d", port)
    return server

# ────────────────────────────────────────────────────────────────────────────
# MAIN STARTUP
# ────────────────────────────────────────────────────────────────────────────

async def main():
    config.validate()
    try:
        await db_init()
        equity = await db_get_equity()
    except Exception as exc:
        raise RuntimeError(f"Supabase connection failed: {exc}") from exc
    log.info(
        "RAID ONLINE — %s — %s MODE — Equity: $%.2f — Using OpenRouter Claude",
        datetime.now(timezone.utc).isoformat(),
        "PAPER" if config.PAPER_MODE else "LIVE",
        equity,
    )
    reset_daily_spend()
    http_server = await start_http_server(5000)
    health_server = await start_health_server()
    tasks = [
        asyncio.create_task(_exit_monitor_loop(), name="exit_monitor"),
        asyncio.create_task(_brain_loop(), name="brain"),
        asyncio.create_task(_periodic_loop(), name="periodic"),
    ]
    try:
        await _shutdown.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        http_server.close()
        health_server.close()
        await http_server.wait_closed()
        await health_server.wait_closed()
        log.info("RAID OFFLINE — %s", datetime.now(timezone.utc).isoformat())

def _install_signal_handlers(loop):
    def _request_shutdown():
        log.info("Shutdown signal received.")
        _shutdown.set()
    for sig in (signal_module.SIGTERM, signal_module.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, AttributeError):
            try:
                signal_module.signal(sig, lambda *_: _request_shutdown())
            except Exception:
                pass

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()

if __name__ == "__main__":
    run()
