"""Funding comes from metaAndAssetCtxs (meta() universe has no funding field)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.hl_perps_scanner as sc


def _scanner(ctxs, meta=None):
    s = sc.HLPerpsScanner.__new__(sc.HLPerpsScanner)
    s._get_asset_ctxs_cached = lambda: ctxs
    s._get_meta_cached = lambda: meta or {"universe": [{"name": "BTC", "szDecimals": 5}]}
    return s


def test_all_rates_from_ctxs():
    s = _scanner({"BTC": {"funding": "-0.0000017964"}, "INJ": {"funding": "0.0000125"},
                  "XMR": {"funding": None}, "BAD": {"funding": "x"}})
    r = s._get_all_funding_rates()
    assert r["BTC"] == pytest.approx(-0.0000017964)
    assert r["INJ"] == pytest.approx(0.0000125)
    assert r["XMR"] == 0.0 and r["BAD"] == 0.0


def test_single_rate():
    s = _scanner({"INJ": {"funding": "0.0003"}})
    assert s._get_funding_rate("inj") == pytest.approx(0.0003)
    assert s._get_funding_rate("NOPE") == 0.0


def test_fallback_keeps_universe_when_ctxs_down():
    s = _scanner({}, meta={"universe": [{"name": "BTC"}, {"name": "INJ"}]})
    assert s._get_all_funding_rates() == {"BTC": 0.0, "INJ": 0.0}


def test_meta_universe_has_no_funding_regression():
    """The old reader looked for 'funding' in meta() universe rows — it never existed."""
    s = _scanner({"BTC": {"funding": "0.0001"}},
                 meta={"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]})
    assert s._get_all_funding_rates()["BTC"] == pytest.approx(0.0001)


def test_scoring_funding_paper_vs_live(monkeypatch):
    monkeypatch.delenv("HL_PERPS_FUNDING_SCORE_LIVE", raising=False)
    monkeypatch.setattr(sc, "_paper_mode_active", lambda: True)
    assert sc.scoring_funding(0.0004) == pytest.approx(0.0004)
    monkeypatch.setattr(sc, "_paper_mode_active", lambda: False)
    assert sc.scoring_funding(0.0004) == 0.0  # live default off
    monkeypatch.setenv("HL_PERPS_FUNDING_SCORE_LIVE", "true")
    assert sc.scoring_funding(0.0004) == pytest.approx(0.0004)
    assert sc.scoring_funding("junk") == 0.0


def test_fade_component_now_reachable(monkeypatch):
    closes = [100 + (i % 5) * 0.1 for i in range(60)]
    vols = [1000.0] * 60
    _, _, comps = sc._score_signal(closes, vols, 0.0005)  # 0.05%/h > 0.03 threshold
    assert comps.get("funding_signal") == "short_fade"


def test_stat_arb_funding_from_ctxs():
    from core.stat_arb import StatArbEngine
    eng = StatArbEngine.__new__(StatArbEngine)
    info = SimpleNamespace(meta_and_asset_ctxs=lambda: [
        {"universe": [{"name": "ARB"}, {"name": "GMX"}]},
        [{"funding": "-0.0002"}, {"funding": "0.00001"}],
    ])
    hl = SimpleNamespace(_info=info, _execute_api=lambda f, *a, **k: f(*a, **k))
    assert eng._get_funding_rate(hl, "arb") == pytest.approx(-0.0002)
    assert eng._get_funding_rate(hl, "NOPE") == 0.0


def test_three_file_rule():
    env = Path(".env.example").read_text()
    ci = Path(".github/workflows/ci.yml").read_text()
    assert "HL_PERPS_FUNDING_SCORE_LIVE=false" in env and "HL_PERPS_FUNDING_SCORE_LIVE=false" in ci
