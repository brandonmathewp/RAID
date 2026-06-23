"""RAID alert manager — email alerts via Resend API.

Requires env vars: RESEND_API_KEY, RESEND_FROM_EMAIL, OPERATOR_EMAIL
No-ops cleanly if RESEND_API_KEY is empty or a placeholder.

Design notes:
  - The Resend SDK send is synchronous/blocking, so it is dispatched to a thread
    via asyncio.to_thread() — it must never block the 1-second exit monitor loop.
  - The per-type cooldown is recorded ONLY after a successful send, so a dropped
    email does not suppress the next real alert for an hour.
"""

import asyncio
import logging
import time

import config

log = logging.getLogger("raid.alerts")

# Cooldown tracker: at most one successful alert of each type per hour.
_last_sent: dict[str, float] = {}
_COOLDOWN_SECONDS = 3600


def _resend_configured() -> bool:
    """True only if a real Resend key is present (not empty, not a placeholder)."""
    key = config.RESEND_API_KEY or ""
    return bool(key) and not key.startswith("your_")


def _eligible(alert_type: str) -> bool:
    """True if this alert type is outside its cooldown window (does NOT record)."""
    return time.time() - _last_sent.get(alert_type, 0) >= _COOLDOWN_SECONDS


def _send_email_blocking(subject: str, body_html: str) -> bool:
    """Synchronous Resend send. Returns True on success. Runs in a worker thread."""
    try:
        import resend
        resend.api_key = config.RESEND_API_KEY
        resend.Emails.send({
            "from": config.RESEND_FROM_EMAIL,
            "to": [config.OPERATOR_EMAIL],
            "subject": f"[RAID] {subject}",
            "html": body_html,
        })
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Resend send failed (%s): %s", subject, exc)
        return False


async def _emit(alert_type: str, subject: str, body_html: str, bypass_cooldown: bool = False):
    """Send an alert without blocking the event loop; record cooldown only on success."""
    if not _resend_configured():
        log.info("Resend not configured — alert suppressed: %s", subject)
        return
    if not bypass_cooldown and not _eligible(alert_type):
        return
    # Offload the blocking HTTP send to a thread, capped so a hung provider cannot
    # freeze the exit monitor; treat a timeout as a failed (non-cooldown) send.
    try:
        sent = await asyncio.wait_for(
            asyncio.to_thread(_send_email_blocking, subject, body_html), timeout=15
        )
    except asyncio.TimeoutError:
        log.error("Resend send timed out: %s", subject)
        sent = False
    if sent:
        _last_sent[alert_type] = time.time()
        log.info("Alert sent: %s → %s", subject, config.OPERATOR_EMAIL)


def _html(title: str, lines: list[str]) -> str:
    rows = "".join(f"<p style='margin:4px 0'>{line}</p>" for line in lines)
    return f"""
<div style='font-family:monospace;font-size:14px;padding:16px;background:#0a0a0a;color:#e0e0e0;border-left:4px solid #ff4444'>
<h2 style='color:#ff4444;margin:0 0 12px 0'>⚠ RAID ALERT</h2>
<h3 style='color:#fff;margin:0 0 8px 0'>{title}</h3>
{rows}
</div>"""


# ── Public alert functions ────────────────────────────────────────────────

async def alert_daily_loss(equity: float, loss_pct: float, threshold_pct: float):
    await _emit("daily_loss", f"Daily loss {loss_pct:.1%} exceeds threshold",
        _html("Daily Loss Alert", [
            f"Current equity: <b>${equity:,.2f}</b>",
            f"Loss this session: <b>{loss_pct:.1%}</b>",
            f"Alert threshold: {threshold_pct:.1%}",
            "Review open positions in the dashboard.",
        ]))


async def alert_consecutive_losses(count: int, equity: float):
    await _emit("consecutive_losses", f"{count} consecutive losses",
        _html(f"{count} Consecutive Losses", [
            f"Current equity: <b>${equity:,.2f}</b>",
            f"Loss streak: <b>{count}</b>",
            "Trading is paused for 60 minutes. Check market conditions.",
        ]))


async def alert_large_trade(symbol: str, size_usd: float, equity: float):
    pct = size_usd / equity if equity > 0 else 0
    await _emit(f"large_trade_{symbol}", f"Large position: {symbol} ${size_usd:,.0f} ({pct:.1%} equity)",
        _html("Large Position Alert", [
            f"Symbol: <b>{symbol}</b>",
            f"Size: <b>${size_usd:,.2f}</b> ({pct:.1%} of equity)",
            f"Current equity: ${equity:,.2f}",
        ]))


async def alert_bot_silent(cycles_missed: int):
    await _emit("bot_silent", f"Bot silent — {cycles_missed} cycles missed",
        _html("Bot Silence Alert", [
            f"Expected brain cycle missed: <b>{cycles_missed}x</b>",
            "Check Railway logs. Bot may have crashed or stalled.",
        ]))


async def alert_budget_warning(spent: float, budget: float):
    await _emit("budget_warning", f"Claude spend ${spent:.2f} of ${budget:.2f} daily budget",
        _html("AI Budget Warning", [
            f"Spent today: <b>${spent:.2f}</b>",
            f"Daily budget: <b>${budget:.2f}</b>",
            "Brain will continue but watch spend closely.",
        ]))


async def alert_emergency_close(equity: float, open_count: int):
    # Bypass cooldown — but the worker guards against re-sending on a stuck flag.
    await _emit("emergency_close", "EMERGENCY CLOSE triggered",
        _html("🚨 EMERGENCY CLOSE", [
            "All open positions are being closed at market.",
            f"Equity at trigger: <b>${equity:,.2f}</b>",
            f"Positions closed: <b>{open_count}</b>",
            "Kill switch has been activated. Bot is halted.",
        ]), bypass_cooldown=True)


async def alert_kill_switch(reason: str, equity: float):
    await _emit("kill_switch", "Kill switch activated",
        _html("Kill Switch Activated", [
            f"Reason: <b>{reason}</b>",
            f"Equity: ${equity:,.2f}",
            "No new entries will open until kill switch is cleared.",
        ]))


async def alert_critical_trajectory(equity: float, required_daily: float, current_daily: float, days_remaining: int):
    await _emit("critical_trajectory", "Trajectory CRITICAL — intervention may be needed",
        _html("Trajectory: CRITICAL", [
            f"Current equity: <b>${equity:,.2f}</b>",
            f"Required daily return: <b>{required_daily:.2%}</b>",
            f"Current daily return: <b>{current_daily:.2%}</b>",
            f"Days remaining: {days_remaining}",
            "Brain has switched to high-conviction-only mode.",
        ]))
