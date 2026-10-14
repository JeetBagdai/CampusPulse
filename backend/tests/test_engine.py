import pytest

from app import whatif
from app.engine import Engine


@pytest.fixture
def engine():
    e = Engine()
    e.wa_mode = "off"
    return e


def open_issue(e, itype, target):
    iid = e.open_by_key.get((itype, target))
    return e.issues[iid] if iid else None


def test_lights_left_on_creates_priced_energy_issue(engine):
    engine.inject("lights_left_on", "E-201")
    engine.tick(5)
    issue = open_issue(engine, "ENERGY_WASTE", "E-201")
    assert issue is not None
    assert issue["status"] == "assigned" and issue["wo"] in engine.wos
    assert issue["rate_inr_hr"] > 0 and issue["loss_inr"] > 0
    assert issue["demo"] is True


def test_done_then_verified_closes_the_loop(engine):
    engine.inject("lights_left_on", "E-201")
    engine.tick(5)
    issue = open_issue(engine, "ENERGY_WASTE", "E-201")
    assert engine.resolve(issue["id"]) == "done_pending"
    engine.tick(1)
    assert issue["status"] == "verified"
    assert issue["saved_inr"] > 0 and engine.saved["inr"] >= issue["saved_inr"]
    assert open_issue(engine, "ENERGY_WASTE", "E-201") is None


def test_night_leak_detected_by_meter_after_30_min(engine):
    engine.inject("leak", "E-1WR")
    engine.tick(29)
    assert open_issue(engine, "WATER_LEAK", "E-1WR") is None
    engine.tick(2)
    issue = open_issue(engine, "WATER_LEAK", "E-1WR")
    assert issue is not None and issue["priority"] == "P1"


def test_bin_spike_raises_overflow(engine):
    engine.inject("bin_spike", "BIN-08")
    engine.tick(1)
    assert open_issue(engine, "BIN_OVERFLOW", "BIN-08") is not None


def test_unacknowledged_p1_escalates(engine):
    engine.inject("leak", "E-1WR")
    engine.tick(31)
    issue = open_issue(engine, "WATER_LEAK", "E-1WR")
    engine.tick(16)
    assert issue["escalated"] is True


def test_ack_stops_escalation(engine):
    engine.inject("leak", "E-1WR")
    engine.tick(31)
    issue = open_issue(engine, "WATER_LEAK", "E-1WR")
    engine.ack(issue["wo"])
    engine.tick(20)
    assert issue["escalated"] is False and issue["status"] == "in_progress"


def test_whatif_policy_saves_money():
    r = whatif.run({"auto_off_minutes": 10, "led_retrofit": True, "fix_leaks": True}, days=7)
    assert r["policy"]["waste_kwh"] < r["baseline"]["waste_kwh"]
    assert r["monthly_saving_inr"] > 0 and r["payback_months"] > 0


def test_kpis_and_scores_are_sane(engine):
    engine.tick(60)
    k = engine.kpis()
    assert 0 <= k["score"] <= 100
    assert k["kwh_today"] >= k["waste_kwh_today"] >= 0
