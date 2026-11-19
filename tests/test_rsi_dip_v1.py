"""Paper-only RSI dip sleeve. Frozen params, no live order path."""
import inspect
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.hyperliquid_executor as hx
from core import rsi_dip_v1 as dip
from core.predator_v1 import get_paper_metrics

_REPO = Path(__file__).resolve().parents[1]


def _decline(n_flat=25, n_drop=40, step=0.4):
    closes = [100.0] * n_flat
    px = 100.0
    for _ in range(n_drop):
        px -= step
        closes.append(px)
    return closes


def _rally(n=40, step=2.0):
    px = 40.0
    closes = []
    for _ in range(n):
        px += step
        closes.append(px)
    return closes


def _candles(closes, *, forming=None):
    start = 1_700_000_000_000
    out = []
    for i, cl in enumerate(closes):
        t = start + i * 3_600_000
        out.append({
            "t": t,
            "T": t + 3_600_000 - 1,
            "o": cl,
            "h": cl * 1.01,
            "l": cl * 0.99,
            "c": cl,
        })
    if forming is not None:
        now = int(time.time() * 1000)
        out.append({
            "t": now,
            "T": now + 3_600_000,
            "o": forming,
            "h": forming * 1.01,
            "l": forming * 0.99,
            "c": forming,
        })
    return out


def _exec(monkeypatch, tmp_path, *, paper=True):
    monkeypatch.setenv("TRADES_FILE", str(tmp_path / "trades.json"))
    monkeypatch.setenv("MODE", "paper" if paper else "live")
    monkeypatch.setenv("PAPER_MODE_LOCKED", "true" if paper else "false")
    monkeypatch.setenv("RSI_DIP_COOLDOWN_STATE_FILE", str(tmp_path / "rsi_stops.json"))
    monkeypatch.setenv("STRATEGY_TOURNAMENT_STATUS_FILE", str(tmp_path / "tournament.json"))
    monkeypatch.setenv("STRATEGY_TOURNAMENT_ENABLED", "false")
    monkeypatch.setattr(hx, "_PAPER_POSITIONS_FILE", tmp_path / "hl_paper_positions.json")
    monkeypatch.setattr(hx, "_TRAILING_STATE_FILE", tmp_path / "trail.json")
    import core.position_monitor as pm
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    e = hx.HyperliquidExecutor.__new__(hx.HyperliquidExecutor)
    e.positions = {}
    e._lock = threading.Lock()
    e._info = None
    e._exchange = MagicMock()
    e.default_leverage = 3
    e.daily_pnl = 0.0
    e.daily_pnl_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    e.daily_loss_limit = 80.0
    e.max_positions = 4
    e.max_position_usd = 150.0
    e.max_notional_usd = 350.0
    e.max_total_exposure = 1400.0
    e.max_margin_equity_pct = 0.15
    e.stop_loss_pct = 2.5
    e.take_profit_pct = 6.0
    e.min_rr_ratio = 1.5
    if paper:
        monkeypatch.setattr(type(e), "is_paper", property(lambda self: True), raising=False)
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 100.0, raising=False)
    monkeypatch.setattr(e, "get_price", lambda sym: 100.0, raising=False)
    monkeypatch.setattr(e, "_feed_daily_goal", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(e, "_inject_scanner_cooldown", lambda *a, **k: None, raising=False)
    return e


class _Scan:
    def __init__(self, executor, candles):
        self.hl_executor = executor
        self.candles = candles
        self.fetches = 0
        self.daily_pnl = 0.0
        self.opens_today = 0
        self._reset = 0

    def _get_candles(self, coin, interval="1h", lookback_hours=120):
        self.fetches += 1
        return self.candles.get(coin, [])

    def _goal_frequency_params(self):
        return {"max_positions": 4, "size_multiplier": 1.0}

    def _check_daily_reset(self):
        self._reset += 1


# ── signal generation ────────────────────────────────────────────────────────

def test_entry_signal_is_long_only_at_20():
    assert dip.entry_signal(20) is True
    assert dip.entry_signal(19.9) is True
    assert dip.entry_signal(20.01) is False
    assert dip.entry_signal(None) is False
    assert dip.entry_signal(85) is False  # overbought is not a short


def test_signal_uses_last_closed_bar_not_the_forming_bar():
    closes = _decline()
    bars = dip.closed_bars(_candles(closes, forming=10_000.0))
    assert bars[-1][4] == closes[-1]
    rsi, atr = dip.bar_indicators(bars)
    assert dip.entry_signal(rsi)
    assert atr > 0
    # A still-forming spike must not flip the signal off.
    raw = _candles(closes, forming=10_000.0)
    assert dip.entry_signal(dip.bar_indicators(dip.closed_bars(raw))[0])


def test_flat_series_does_not_signal():
    closes = [100.0] * 40
    assert dip.rsi_ewm(closes) is None
    ind = dip.bar_indicators(dip.closed_bars(_candles(closes)))
    assert ind is None or not dip.entry_signal(ind[0])


# ── both exits, stop first ───────────────────────────────────────────────────

def test_exit_rsi_and_time_and_stop_precedence():
    assert dip.exit_reason(rsi=49.9, held_hours=11.99, mark=100, stop=90) is None
    assert dip.exit_reason(rsi=50, held_hours=1, mark=100, stop=90) == dip.EXIT_RSI
    assert dip.exit_reason(rsi=70, held_hours=1, mark=100, stop=90) == dip.EXIT_RSI
    assert dip.exit_reason(rsi=30, held_hours=12, mark=100, stop=90) == dip.EXIT_TIME
    assert dip.exit_reason(rsi=30, held_hours=20, mark=100, stop=90) == dip.EXIT_TIME
    # RSI reversion wins over the time stop when both are true.
    assert dip.exit_reason(rsi=50, held_hours=13, mark=100, stop=90) == dip.EXIT_RSI
    # Stop is intrabar and wins over both.
    assert dip.exit_reason(rsi=80, held_hours=13, mark=90, stop=90) == dip.EXIT_STOP
    assert dip.exit_reason(rsi=10, held_hours=1, mark=80, stop=90) == dip.EXIT_STOP


def test_atr_stop_is_three_times_atr_below_entry():
    assert dip.atr_stop_price(100, 2) == 94
    assert dip.atr_stop_price(100, 2, mult=3) == 94
    assert dip.ATR_MULT == 3
    assert dip.atr_stop_price(100, 0) is None
    assert dip.atr_stop_price(100, -1) is None
    assert dip.atr_stop_price(0, 2) is None
    assert dip.atr_stop_price(5, 2) is None  # stop would be negative


# ── position cap ─────────────────────────────────────────────────────────────

def test_sleeve_position_cap_is_three():
    assert dip.MAX_CONCURRENT == 3
    assert dip.sleeve_admission("LINK", {"AAVE", "BTC"}) == (True, "ok")
    ok, why = dip.sleeve_admission("AAVE", {"AAVE"})
    assert ok is False and why == "already_open"
    ok, why = dip.sleeve_admission("LINK", {"AAVE", "BTC", "INJ"})
    assert ok is False and why == "sleeve_cap"


# ── allowlist minus hard ban ─────────────────────────────────────────────────

def test_universe_is_allowlist_minus_hard_ban():
    allow = {"AAVE", "ETH", "SOL", "BTC"}
    ban = {"ETH", "SOL", "TRB", "GRASS"}
    assert dip.in_universe("AAVE", allow, ban)
    assert dip.in_universe("btc", allow, ban)
    assert not dip.in_universe("ETH", allow, ban)
    assert not dip.in_universe("SOL", allow, ban)
    assert not dip.in_universe("TRB", allow, ban)
    assert not dip.in_universe("DOGE", allow, ban)
    assert not dip.in_universe("AAVE", set(), ban)
    assert dip.universe_coins(allow, ban) == ["AAVE", "BTC"]


# ── flag off ─────────────────────────────────────────────────────────────────

def test_flag_off_does_not_trade(monkeypatch):
    monkeypatch.delenv("RSI_DIP_V1_ENABLED", raising=False)
    assert dip.enabled() is False

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"sleeve touched executor via {name}")

    scanner = _Scan(_Boom(), {"AAVE": _candles(_decline())})
    assert dip.run_sleeve(scanner) == []
    assert scanner.fetches == 0


def test_flag_on_but_live_mode_does_not_trade(monkeypatch, tmp_path):
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("PAPER_MODE_LOCKED", "false")
    monkeypatch.setenv("MODE", "live")
    assert dip.enabled() is False
    e = _exec(monkeypatch, tmp_path, paper=False)
    # Real is_paper follows MODE. Do not force it true.
    assert e.open_paper_sleeve(
        "AAVE", size_usd=50, leverage=3, atr=1.0, strategy=dip.STRATEGY, rsi=15
    ) is None
    assert e.positions == {}
    e._exchange.market_open.assert_not_called()
    e._exchange.market_close.assert_not_called()
    e._exchange.order.assert_not_called()
    src = inspect.getsource(hx.HyperliquidExecutor.open_paper_sleeve)
    assert ".market_open" not in src and ".market_close" not in src and ".order(" not in src


# ── paper journal, exits, cap, ban, no A/B ───────────────────────────────────

def test_paper_open_journals_and_respects_stop_cap_and_ban(monkeypatch, tmp_path):
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE,ETH,BTC")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "ETH,TRB")
    e = _exec(monkeypatch, tmp_path, paper=True)
    called = {"ab": 0}

    def _ab(*a, **k):
        called["ab"] += 1
        raise AssertionError("exit A/B must not run on the sleeve")

    monkeypatch.setattr(e, "_paper_exit_ab_apply", _ab, raising=False)
    candles = {
        "AAVE": _candles(_decline(), forming=50_000),
        "ETH": _candles(_decline()),  # banned
        "BTC": _candles(_decline()),
        "DOGE": _candles(_decline()),  # off allowlist
    }
    scanner = _Scan(e, candles)
    opened = dip.run_sleeve(scanner)
    assert opened  # at least the oversold allowlist names
    assert "ETH" not in e.positions
    assert "DOGE" not in e.positions
    assert called["ab"] == 0
    assert len([p for p in e.positions.values() if dip.is_sleeve_position(p)]) <= 3
    for coin, pos in e.positions.items():
        assert pos.strategy == "rsi_dip_v1"
        assert pos.side == "long"
        assert pos.take_profit_price is None
        assert pos.exit_variant == ""
        assert pos.stop_loss_price == pytest.approx(pos.entry_price - 3 * pos.regime_ctx["atr"])
        assert coin in {"AAVE", "BTC"}
    trades = json.loads((tmp_path / "trades.json").read_text())
    assert trades
    for row in trades:
        assert row["strategy"] == "rsi_dip_v1"
        assert row["is_paper"] is True
        assert row["tx_hash"] == "PAPER_TX"
        assert row["chain"] == "hyperliquid"
        assert row["reason"].startswith("paper_open")
        assert "exit_variant" not in row
    ledger = (tmp_path / "trade_ledger.jsonl").read_text().strip().splitlines()
    assert ledger and json.loads(ledger[0])["strategy"] == "rsi_dip_v1"
    # Predator promote gate does not count the sleeve opens (or, later, its closes).
    assert get_paper_metrics()["closed_trades"] == 0

    # Cap: a third and fourth name must not push the sleeve past 3.
    # Seed the book to 3 sleeve positions and show LINK is refused.
    e.positions.clear()
    for coin in ("AAVE", "BTC", "INJ"):
        e.positions[coin] = hx.HLPosition(
            coin=coin, side="long", entry_price=100, size=1, size_usd=50,
            leverage=3, stop_loss_price=90, strategy=dip.STRATEGY,
            regime_ctx={"strategy": dip.STRATEGY},
        )
    scanner.candles["LINK"] = _candles(_decline())
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE,BTC,INJ,LINK")
    assert dip.run_sleeve(scanner) == [] or "LINK" not in e.positions
    assert "LINK" not in e.positions
    assert len(e.positions) == 3


def test_rsi_exit_and_time_exit_and_stop_journal(monkeypatch, tmp_path):
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "ETH")
    e = _exec(monkeypatch, tmp_path, paper=True)
    scanner = _Scan(e, {"AAVE": _candles(_decline())})
    assert "AAVE" in dip.run_sleeve(scanner)
    pos = e.positions["AAVE"]
    assert pos.stop_loss_price < pos.entry_price

    # RSI reversion on the next closed bars. Price stays above the stop.
    scanner.candles["AAVE"] = _candles(_rally())
    e.get_price = lambda sym: pos.entry_price * 1.02
    closed = dip.run_sleeve(scanner)
    assert closed == ["AAVE"]
    assert "AAVE" not in e.positions
    rows = json.loads((tmp_path / "trades.json").read_text())
    sell = [r for r in rows if r["action"] == "SELL"]
    assert len(sell) == 1
    assert sell[0]["strategy"] == "rsi_dip_v1"
    assert sell[0]["exit_reason"] == "rsi_revert"
    assert sell[0]["is_paper"] is True
    assert sell[0]["pnl_usd"] is not None
    assert get_paper_metrics()["closed_trades"] == 0
    # Time stop while RSI is still oversold. A fresh entry on the same pass is
    # allowed by the study (one position at a time, re-enter after the exit).
    (tmp_path / "trades.json").write_text("[]")
    scanner.candles["AAVE"] = _candles(_decline())
    e.get_price = lambda sym: 100.0
    dip.run_sleeve(scanner)
    assert "AAVE" in e.positions
    e.positions["AAVE"].opened_at = datetime.now(timezone.utc) - timedelta(hours=12, minutes=5)
    e.get_price = lambda sym: e.positions["AAVE"].entry_price
    dip.run_sleeve(scanner)
    sell = [r for r in json.loads((tmp_path / "trades.json").read_text()) if r["action"] == "SELL"]
    assert sell[-1]["exit_reason"] == "time"
    assert sell[-1]["strategy"] == "rsi_dip_v1"

    # Stop: mark through the 3×ATR stop, RSI still oversold, hold still short.
    if "AAVE" not in e.positions:
        e.get_price = lambda sym: 100.0
        dip.run_sleeve(scanner)
    assert "AAVE" in e.positions
    stop = e.positions["AAVE"].stop_loss_price
    e.positions["AAVE"].opened_at = datetime.now(timezone.utc)
    e.get_price = lambda sym: stop * 0.99
    dip.run_sleeve(scanner)
    sell = [r for r in json.loads((tmp_path / "trades.json").read_text()) if r["action"] == "SELL"]
    assert sell[-1]["exit_reason"] == "stop"
    assert sell[-1]["strategy"] == "rsi_dip_v1"
    assert sell[-1]["pnl_usd"] < 0
    e._exchange.market_close.assert_not_called()
    e._exchange.market_open.assert_not_called()


def test_frozen_constants_and_three_file_rule():
    assert (dip.RSI_PERIOD, dip.RSI_ENTRY, dip.RSI_EXIT) == (14, 20.0, 50.0)
    assert dip.MAX_HOLD_HOURS == 12
    assert dip.ATR_MULT == 3
    assert dip.MAX_CONCURRENT == 3
    assert dip.TIMEFRAME == "1h"
    src = (_REPO / "core" / "rsi_dip_v1.py").read_text()
    assert 'os.getenv(FLAG, "false")' in src
    assert "moralis_score" not in src.lower()
    assert "import moralis" not in src.lower()
    env = (_REPO / ".env.example").read_text()
    ci = (_REPO / ".github" / "workflows" / "ci.yml").read_text()
    assert "RSI_DIP_V1_ENABLED=true" in env
    assert "s/^RSI_DIP_V1_ENABLED=.*/RSI_DIP_V1_ENABLED=true/" in ci
    # Deploy sed matches .env.example, same as the other paper flags.
    assert "MODE=live" not in ci
    assert "PAPER_MODE_LOCKED=false" not in ci
    assert "MORALIS_ENABLED=true" not in ci


def test_loss_cap_shrinks_margin_but_not_the_stop_distance():
    # 1% ATR → 3% stop. Dollar cap ($15) does not bind before the notional cap.
    mild = dip.plan_margin_usd(
        equity=1000, max_positions=4, max_position_usd=150, max_notional_usd=350,
        leverage=3, margin_equity_pct=0.15, max_loss_usd=15, entry=100, atr=1,
    )
    assert mild == pytest.approx(116.67, abs=0.02)
    # 10% ATR → 30% stop. Margin shrinks so a stop-out is about $15. Stop distance stays 3×ATR.
    wide = dip.plan_margin_usd(
        equity=1000, max_positions=4, max_position_usd=150, max_notional_usd=350,
        leverage=3, margin_equity_pct=0.15, max_loss_usd=15, entry=100, atr=10,
    )
    assert wide is not None and wide < mild
    assert wide * 3 * (3 * 10 / 100) == pytest.approx(15, abs=0.05)
    assert dip.atr_stop_price(100, 10) == 70
    # Stop so wide that the $10 minimum would lose more than $15 → no trade.
    assert dip.plan_margin_usd(
        equity=1000, max_positions=4, max_position_usd=150, max_notional_usd=350,
        leverage=3, margin_equity_pct=0.15, max_loss_usd=15, entry=100, atr=30,
    ) is None


def test_sleeve_closes_are_not_paired_into_predator_outcomes():
    import core.hl_perps_scanner as sc

    rows = [
        {"token_symbol": "AAVE", "strategy": "rsi_dip_v1", "pnl_usd": -5.0,
         "reason": "paper_close", "timestamp": "2026-11-18T00:00:00+00:00"},
        {"token_symbol": "BTC", "pnl_usd": 1.25, "reason": "paper_close",
         "timestamp": "2026-11-18T00:00:00+00:00"},
    ]
    paired = sc._pair_positions(rows)
    assert [coin for coin, _ts, _pnl in paired] == ["BTC"]


def test_rsi_path_matches_rsi_ewm():
    closes = _decline()
    assert dip.rsi_path(closes)[-1] == pytest.approx(dip.rsi_ewm(closes))


def test_stop_blocks_reentry_until_cooldown_and_rsi_rearm(monkeypatch, tmp_path):
    """The SKY bug: a stop with RSI still oversold must not reopen on the next pass."""
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "ETH")
    monkeypatch.setenv("RSI_DIP_STOP_COOLDOWN_HOURS", "6")
    monkeypatch.setenv("RSI_DIP_STOP_REARM_RSI", "35")
    e = _exec(monkeypatch, tmp_path, paper=True)
    scanner = _Scan(e, {"AAVE": _candles(_decline())})
    assert "AAVE" in dip.run_sleeve(scanner)
    stop = e.positions["AAVE"].stop_loss_price
    e.positions["AAVE"].opened_at = datetime.now(timezone.utc)
    e.get_price = lambda sym: stop * 0.99
    dip.run_sleeve(scanner)
    assert "AAVE" not in e.positions
    sells = [r for r in json.loads((tmp_path / "trades.json").read_text()) if r["action"] == "SELL"]
    assert sells[-1]["exit_reason"] == "stop"
    # Same dip, a few seconds later. This is the re-open the cooldown exists to stop.
    e.get_price = lambda sym: 100.0
    assert dip.run_sleeve(scanner) == []
    assert "AAVE" not in e.positions
    state = json.loads((tmp_path / "rsi_stops.json").read_text())
    assert state["AAVE"]["rearmed"] is False
    assert dip.stop_block_reason("AAVE") == "stop_cooldown"

    # Clock elapsed, RSI never recovered: still blocked. Then a later rally
    # re-arms, and only a new dip after that is allowed through.
    stopped = 1_700_000_000.0
    dip.note_stop_out("AAVE", now=stopped)
    assert dip.stop_block_reason("AAVE", now=stopped + 60) == "stop_cooldown"
    assert dip.stop_block_reason("AAVE", now=stopped + 7 * 3600) == "stop_rearm"
    monkeypatch.setattr(dip, "now_ts", lambda: stopped + 8 * 3600)
    assert dip.run_sleeve(scanner) == []
    rally = _candles(_rally())
    bars = dip.closed_bars(rally, now_ms=rally[-1]["T"] + 10_000)
    assert dip.rsi_path([b[4] for b in bars])[-1] >= 35
    dip.refresh_stop_rearm("AAVE", bars)
    assert json.loads((tmp_path / "rsi_stops.json").read_text())["AAVE"]["rearmed"] is True
    assert dip.stop_block_reason("AAVE", now=stopped + 8 * 3600) is None
    monkeypatch.setattr(dip, "now_ts", time.time)
    e.get_price = lambda sym: 100.0
    scanner.candles["AAVE"] = _candles(_decline())
    assert dip.run_sleeve(scanner) == ["AAVE"]


def test_trailing_monitor_stop_still_arms_the_cooldown(monkeypatch, tmp_path):
    """main.py closes paper stops via check_paper_triggers before the sleeve runs."""
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "")
    monkeypatch.setenv("RSI_DIP_STOP_COOLDOWN_HOURS", "6")
    monkeypatch.setenv("RSI_DIP_STOP_REARM_RSI", "35")
    monkeypatch.setenv("PAPER_SLTP_ENFORCE", "true")
    e = _exec(monkeypatch, tmp_path, paper=True)
    scanner = _Scan(e, {"AAVE": _candles(_decline())})
    assert "AAVE" in dip.run_sleeve(scanner)
    stop = e.positions["AAVE"].stop_loss_price
    res = e.check_paper_triggers("AAVE", stop * 0.99)
    assert res is not None
    assert res["exit_reason"] == "stop"
    assert "AAVE" not in e.positions
    assert dip.stop_block_reason("AAVE") == "stop_cooldown"
    e.get_price = lambda sym: 100.0
    assert dip.run_sleeve(scanner) == []
    assert "AAVE" not in e.positions


def test_rsi_and_time_exits_do_not_arm_the_stop_cooldown(monkeypatch, tmp_path):
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "")
    monkeypatch.setenv("RSI_DIP_STOP_COOLDOWN_HOURS", "6")
    monkeypatch.setenv("RSI_DIP_STOP_REARM_RSI", "35")
    e = _exec(monkeypatch, tmp_path, paper=True)
    scanner = _Scan(e, {"AAVE": _candles(_decline())})
    dip.run_sleeve(scanner)
    scanner.candles["AAVE"] = _candles(_rally())
    e.get_price = lambda sym: e.positions["AAVE"].entry_price * 1.02
    dip.run_sleeve(scanner)
    sells = [r for r in json.loads((tmp_path / "trades.json").read_text()) if r["action"] == "SELL"]
    assert sells[-1]["exit_reason"] == "rsi_revert"
    assert not (tmp_path / "rsi_stops.json").exists() or "AAVE" not in json.loads(
        (tmp_path / "rsi_stops.json").read_text() or "{}"
    )
    assert dip.stop_block_reason("AAVE") is None


def test_tournament_pause_blocks_sleeve_entries_only(monkeypatch, tmp_path):
    monkeypatch.setenv("RSI_DIP_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_MIN_CLOSES", "20")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_PF_FLOOR", "0.80")
    e = _exec(monkeypatch, tmp_path, paper=True)
    monkeypatch.setenv("STRATEGY_TOURNAMENT_ENABLED", "true")
    rows = []
    for i in range(20):
        rows.append({
            "chain": "hyperliquid", "action": "SELL", "is_paper": True,
            "token_symbol": "AAVE", "strategy": "rsi_dip_v1", "pnl_usd": -1.0,
            "reason": "paper_close", "timestamp": f"2026-11-01T00:{i:02d}:00+00:00",
        })
    rows.append({
        "chain": "hyperliquid", "action": "SELL", "is_paper": True,
        "token_symbol": "BTC", "strategy": "", "pnl_usd": -5.0,
        "reason": "paper_close", "timestamp": "2026-11-01T01:00:00+00:00",
    })
    (tmp_path / "trades.json").write_text(json.dumps(rows))
    scanner = _Scan(e, {"AAVE": _candles(_decline())})
    assert dip.run_sleeve(scanner) == []
    assert e.positions == {}
    status = json.loads((tmp_path / "tournament.json").read_text())
    assert status["applied_to_live"] is False
    assert status["sleeves"]["rsi_dip_v1"]["paused"] is True
    assert status["sleeves"]["predator_v1"]["paused"] is False
    e._exchange.market_open.assert_not_called()


def test_sleeve_opens_are_saved_after_the_pass(monkeypatch):
    import core.hl_perps_scanner as sc

    scanner = sc.HLPerpsScanner.__new__(sc.HLPerpsScanner)
    scanner.opens_today = 2
    scanner._last_cycle_signals = []
    seen = {}

    def _open(s, allow_entries=True):
        s.opens_today += 1
        return ["AAVE"]

    def _save(signals):
        seen["opens"] = scanner.opens_today
        seen["n"] = len(signals)

    monkeypatch.setattr(dip, "run_sleeve", _open)
    scanner._save_state = _save
    scanner._run_rsi_dip_sleeve(allow_entries=True)
    assert seen == {"opens": 3, "n": 0}
