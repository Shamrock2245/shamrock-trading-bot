"""HL paper journal → immutable ledger, shared executor, Base mempool flag."""
import json
import threading

import core.hyperliquid_executor as hx
import core.position_monitor as pm
from tests.test_hl_paper_persistence import _exec


def _ledger(tmp_path):
    p = tmp_path / "trade_ledger.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_paper_open_and_close_journal_to_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    monkeypatch.setattr(pm, "_running_pnl_usd", 0.0)
    e = _exec(monkeypatch, tmp_path)
    assert e._paper_open_position("INJ", "buy", 100.0, 3, 70.0, 9.5, 11.0) is not None
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 11.0, raising=False)
    assert e._paper_close_position("INJ") is not None

    rows = _ledger(tmp_path)
    trades = json.loads((tmp_path / "trades.json").read_text())
    assert len(rows) == len(trades) == 2
    close = [r for r in rows if r["reason"] == "paper_close"][0]
    assert close["chain"] == "hyperliquid" and close["pnl_usd"] > 0
    assert close["running_total_pnl_usd"] == round(close["pnl_usd"], 4)
    assert [r["ledger_seq"] for r in rows] == [0, 1]


def test_orphans_not_written_to_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    hx._journal_to_ledger({"action": "SELL", "pnl_usd": -50.0, "exclude_from_metrics": True})
    assert _ledger(tmp_path) == []
    # Orphan reconcile path never touches the ledger either
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    (tmp_path / "trades.json").write_text(json.dumps([{
        "chain": "hyperliquid", "is_paper": True, "quantity": 1, "price_usd": 9.0,
        "timestamp": now, "token_symbol": "XMR", "action": "BUY", "reason": "paper_open",
    }]))
    e = _exec(monkeypatch, tmp_path)
    assert e._reconcile_paper_orphans() == 1
    assert _ledger(tmp_path) == []


def test_shared_executor_is_singleton_per_account(monkeypatch):
    built = []

    class Fake:
        def __init__(self, sub_account_address=None):
            built.append(sub_account_address)
            self._initialized = True
            self.is_paper = True

    monkeypatch.setattr(hx, "HyperliquidExecutor", Fake)
    monkeypatch.setattr(hx, "_SHARED_EXECUTORS", {})
    a, b = hx.get_shared_executor(), hx.get_shared_executor("")
    c = hx.get_shared_executor("0xABCDEF0123456789")
    assert a is b and c is not a
    assert c is hx.get_shared_executor("0xabcdef0123456789")
    assert len(built) == 2


def test_failed_live_init_not_cached(monkeypatch):
    class Fake:
        def __init__(self, sub_account_address=None):
            self._initialized = False
            self.is_paper = False

    monkeypatch.setattr(hx, "HyperliquidExecutor", Fake)
    monkeypatch.setattr(hx, "_SHARED_EXECUTORS", {})
    assert hx.get_shared_executor() is not hx.get_shared_executor()


def test_sub_account_gets_own_paper_file(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.sub_account_address = None
    main_file = e._paper_positions_file
    e.sub_account_address = "0xAAAA11112222"
    assert e._paper_positions_file != main_file
    assert e._paper_positions_file.parent == main_file.parent


def test_concurrent_journal_writes_lose_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    e = _exec(monkeypatch, tmp_path)

    def w(i):
        e._log_hl_trade(action="BUY", coin=f"C{i}", side="long", price=1.0,
                        quantity=1.0, value_usd=1.0, reason="paper_open")

    ts = [threading.Thread(target=w, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(json.loads((tmp_path / "trades.json").read_text())) == 20
    assert len(_ledger(tmp_path)) == 20


def test_base_mempool_watcher_off_by_default():
    import inspect
    import os

    import core.mev_extractor as mev
    if "MEV_SANDWICH_BASE_MEMPOOL_ENABLED" not in os.environ:
        assert mev.SANDWICH_BASE_MEMPOOL_ENABLED is False
    src = inspect.getsource(mev.MEVExtractorEngine)
    assert "SANDWICH_ENABLED and SANDWICH_BASE_MEMPOOL_ENABLED" in src
