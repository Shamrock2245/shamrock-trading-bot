"""tests/test_alpha_discovery.py — discovery scoring, routing, and gate safety."""
import json
import os

from core import alpha_discovery as ad


def _ctx(px=10.0, prev=9.5, vol=50e6, oi=2e6, funding=0.00001, imp=(9.99, 10.01)):
    return {"markPx": str(px), "prevDayPx": str(prev), "dayNtlVlm": str(vol),
            "openInterest": str(oi), "funding": str(funding), "impactPxs": [str(i) for i in imp]}


def _fake(ctxs, trending=None):
    return dict(fetch_ctx=lambda: ctxs, fetch_trending=lambda: trending or {},
                fetch_detail=lambda c: ([10.0] * 48, 200.0))


def test_score_bounds_and_breakdown_sums():
    s, br, met, vet = ad.score_coin(_ctx(), median_volume=10e6, trending_rank=0)
    assert 0 <= s <= 100
    assert abs(sum(br.values()) - s) < 0.05
    assert set(br) == set(ad.WEIGHTS)
    assert met["holder_unlock_risk"].startswith("unavailable")
    assert vet == []


def test_vetoes():
    _, _, _, vet = ad.score_coin(_ctx(vol=1e5, funding=0.002, imp=(9, 11), prev=13),
                                 median_volume=1e6, trending_rank=None, listing_age_days=2)
    for v in ("low_volume", "extreme_funding", "thin_book", "new_listing_lt_7d", "dumping"):
        assert v in vet


def test_crowded_funding_scores_lower():
    a, *_ = ad.score_coin(_ctx(funding=0.0), median_volume=10e6, trending_rank=None)
    b, *_ = ad.score_coin(_ctx(funding=0.0004), median_volume=10e6, trending_rank=None)
    assert a > b


def test_routing_never_bypasses_allowlist_or_ban(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE,LINK")
    monkeypatch.setenv("HL_PERPS_HARD_BAN_COINS", "TRB")
    ctxs = {"AAVE": _ctx(), "LINK": _ctx(prev=9.9), "TRB": _ctx(prev=8.0), "NEWCOIN": _ctx(prev=8.5)}
    pl = ad.run_discovery_cycle(**_fake(ctxs, {"NEWCOIN": 0}))
    routes = {c["coin"]: c["route"] for c in pl["top"]}
    assert routes["TRB"] == "vetoed"
    assert routes["NEWCOIN"] == "promotion_proposal"
    assert set(pl["predator_queue"]) <= {"AAVE", "LINK"}
    assert json.loads((tmp_path / "discovery.json").read_text())["sources"]["moralis"] is False


def test_priority_order_reorders_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    (tmp_path / "discovery.json").write_text(json.dumps({"predator_queue": ["LINK", "OUTSIDER", "AAVE"]}))
    out = ad.priority_order(["AAVE", "BTC", "LINK"])
    assert out == ["LINK", "AAVE", "BTC"]
    assert "OUTSIDER" not in out


def test_priority_order_disabled_or_stale(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    p = tmp_path / "discovery.json"
    p.write_text(json.dumps({"predator_queue": ["LINK"]}))
    monkeypatch.setenv("DISCOVERY_FEED_SCANNER", "false")
    assert ad.priority_order(["AAVE", "LINK"]) == ["AAVE", "LINK"]
    monkeypatch.setenv("DISCOVERY_FEED_SCANNER", "true")
    os.utime(p, (0, 0))
    assert ad.priority_order(["AAVE", "LINK"]) == ["AAVE", "LINK"]


def test_kprefix_symbol():
    assert ad._norm_symbol("kPEPE") == "PEPE"
    assert ad._norm_symbol("KAITO") == "KAITO"
