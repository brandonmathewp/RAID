"""Offline test for brain._execute_brain_trades — the path verify.py cannot reach.

The live DB sits at max open positions, so a real brain cycle returns 0 trades and
never exercises trade execution. This test drives that path with an in-memory fake
DB (no Supabase writes, no Claude call) to validate the review fixes:
  #5  operator max_open_trades is enforced (break when book is full)
  #6  booked entry_price = LIVE scanned price, not Claude's quoted level
  #6b a trade whose live price already breached the stop is skipped
  #10 correlation penalty cannot push size below the 0.5% floor
  +   every trade/prediction dict key matches the Supabase schema columns

Run from backend/:  python test_execution_path.py
"""

import asyncio
import sys

# UTF-8 console so ✓/✗ render on legacy Windows code pages (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config
import brain
from scanner import ScanResult

# Columns that actually exist (Phase 0 schema) — a write of any other key 400s live.
TRADES_COLS = {
    "id", "bot_name", "market", "symbol", "direction", "entry_price", "exit_price",
    "size_usd", "confidence", "pnl", "status", "open_time", "close_time",
    "close_reason", "paper_mode", "sl", "tp", "instrument_type", "market_regime",
    "claude_reasoning", "predicted_prob", "kelly_fraction", "trajectory_status",
}
PREDICTIONS_COLS = {
    "id", "trade_id", "predicted_at", "symbol", "direction", "stated_prob",
    "outcome", "actual_win",
}

_PASS, _FAIL = [], []


def check(name, cond):
    (_PASS if cond else _FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}")


class FakeDB:
    """Minimal async stand-in. Captures writes; never touches Supabase."""

    def __init__(self, open_trades=None):
        self._open = open_trades or []
        self.logged_trades = []
        self.logged_predictions = []
        self._id = 0

    async def get_open_trades(self):
        return list(self._open)

    async def get_open_trades_by_market(self, market):
        return [t for t in self._open if t.get("market") == market]

    async def get_kill_switch(self):
        return False

    async def get_equity(self):
        return 4000.0

    async def get_daily_stats(self, date):
        return {"pnl": 0}

    async def get_consecutive_losses(self):
        return 0

    async def get_last_loss_time(self):
        return None

    async def log_trade(self, record):
        self._id += 1
        self.logged_trades.append(record)
        return f"fake-trade-{self._id}"

    async def log_prediction(self, record):
        self.logged_predictions.append(record)


def _scan(symbol, price):
    return ScanResult(market="crypto", symbol=symbol, current_price=price, scan_time="")


def _trade(symbol, direction, entry, sl, tp, size_pct=2.5, prob=0.80):
    return {
        "symbol": symbol, "direction": direction, "entry_price": entry,
        "stop_loss": sl, "take_profit": tp, "size_pct": size_pct,
        "probability": prob, "reasoning": "unit test trade",
    }


TRAJ = {"trajectory_status": "CRITICAL", "equity": 4000.0, "equity_available": True}
SIZING = {"kelly_fraction": 0.25}
CONTROLS = {"max_open_trades": 8, "max_position_pct": 0.07,
            "kill_switch": False, "pause_entries": False}


async def scenario_happy_path():
    print("\nScenario A — empty book, one valid short:")
    db = FakeDB(open_trades=[])
    # Claude quoted entry 149; live market is 150. SL 153 (above, valid short).
    bj = {"trades": [_trade("SOLUSD", "short", 149.0, 153.0, 144.0)],
          "regime_by_asset": {"SOLUSD": "TRENDING_DOWN"}, "skipped": {}}
    scans = [_scan("SOLUSD", 150.0)]
    opened = await brain._execute_brain_trades(bj, scans, TRAJ, SIZING, db, CONTROLS, 0.02)

    check("opens exactly 1 trade", opened == 1 and len(db.logged_trades) == 1)
    if db.logged_trades:
        rec = db.logged_trades[0]
        check("entry anchored to LIVE price 150.0 (not Claude's 149.0)", rec["entry_price"] == 150.0)
        check("size_usd = 2.5% of $4000 = $100", abs(rec["size_usd"] - 100.0) < 0.01)
        check("all 6 brain v2 columns populated", all(
            rec.get(c) is not None for c in
            ("instrument_type", "market_regime", "claude_reasoning", "predicted_prob",
             "kelly_fraction", "trajectory_status")))
        check("trade record has NO unknown columns (would 400 on Supabase)",
              set(rec.keys()) <= TRADES_COLS)
    check("logs exactly 1 prediction", len(db.logged_predictions) == 1)
    if db.logged_predictions:
        check("prediction record has NO unknown columns",
              set(db.logged_predictions[0].keys()) <= PREDICTIONS_COLS)


async def scenario_max_open():
    print("\nScenario B — book already full (8/8), operator cap honored:")
    full_book = [{"symbol": f"X{i}USD", "direction": "long", "market": "crypto"} for i in range(8)]
    db = FakeDB(open_trades=full_book)
    bj = {"trades": [_trade("SOLUSD", "short", 149.0, 153.0, 144.0)],
          "regime_by_asset": {"SOLUSD": "TRENDING_DOWN"}, "skipped": {}}
    opened = await brain._execute_brain_trades(bj, [_scan("SOLUSD", 150.0)], TRAJ, SIZING, db, CONTROLS, 0.02)
    check("opens 0 trades when book is full", opened == 0 and len(db.logged_trades) == 0)

    print("\nScenario B2 — operator lowers max_open_trades to 3, 3 already open:")
    book3 = [{"symbol": f"X{i}USD", "direction": "long", "market": "crypto"} for i in range(3)]
    db2 = FakeDB(open_trades=book3)
    controls_low = dict(CONTROLS, max_open_trades=3)
    opened2 = await brain._execute_brain_trades(bj, [_scan("SOLUSD", 150.0)], TRAJ, SIZING, db2, controls_low, 0.02)
    check("operator cap of 3 blocks the 4th entry (gate uses static 8)", opened2 == 0)


async def scenario_sl_breached():
    print("\nScenario C — live price already past Claude's stop → skip:")
    db = FakeDB(open_trades=[])
    # Short with SL 153, but live price is 155 (already above stop) → must skip.
    bj = {"trades": [_trade("SOLUSD", "short", 149.0, 153.0, 144.0)],
          "regime_by_asset": {"SOLUSD": "TRENDING_DOWN"}, "skipped": {}}
    opened = await brain._execute_brain_trades(bj, [_scan("SOLUSD", 155.0)], TRAJ, SIZING, db, CONTROLS, 0.02)
    check("skips trade when live price already breached the stop", opened == 0)


async def scenario_corr_floor():
    print("\nScenario D — correlation penalty respects the 0.5% floor:")
    # 3 correlated longs open (BTC/ETH/SOL share a group with XRP).
    book = [
        {"symbol": "BTCUSD", "direction": "long", "market": "crypto"},
        {"symbol": "ETHUSD", "direction": "long", "market": "crypto"},
        {"symbol": "SOLUSD", "direction": "long", "market": "crypto"},
    ]
    db = FakeDB(open_trades=book)
    # New XRP trade at the 0.5% floor; penalty would halve to 0.25% → must re-floor to 0.5%.
    bj = {"trades": [_trade("XRPUSD", "long", 0.50, 0.49, 0.55, size_pct=0.5, prob=0.70)],
          "regime_by_asset": {"XRPUSD": "TRENDING_UP"}, "skipped": {}}
    opened = await brain._execute_brain_trades(bj, [_scan("XRPUSD", 0.50)], TRAJ, SIZING, db, CONTROLS, 0.02)
    check("opens the correlated trade", opened == 1)
    if db.logged_trades:
        rec = db.logged_trades[0]
        floor_usd = config.MIN_TRADE_SIZE_PCT * 4000.0  # 0.5% of 4000 = $20
        check(f"size held at 0.5% floor (${floor_usd:.0f}), not halved to $10",
              abs(rec["size_usd"] - floor_usd) < 0.01)


async def main():
    print("=" * 60)
    print("  EXECUTION-PATH TEST (offline, no DB writes, no Claude)")
    print("=" * 60)
    await scenario_happy_path()
    await scenario_max_open()
    await scenario_sl_breached()
    await scenario_corr_floor()
    print("\n" + "=" * 60)
    print(f"  {len(_PASS)} passed, {len(_FAIL)} failed")
    if _FAIL:
        print("  FAILED:", ", ".join(_FAIL))
    print("=" * 60)
    return not _FAIL


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
