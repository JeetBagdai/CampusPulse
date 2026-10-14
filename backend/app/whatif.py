"""What-if engine: replays the same 30 days of campus life with and without a
policy (same random events, so the only difference is the policy) and reports
the savings, CO2 and payback period."""
from datetime import datetime, timedelta
from functools import lru_cache

from . import config as cfg
from .datasource.mock import MockSource, Policy, load_campus

START = datetime(2026, 9, 1)
SEED = 11


def _metrics(s: MockSource) -> dict:
    t = {k: sum(s.totals[b][k] for b in s.totals) for k in next(iter(s.totals.values()))}
    inr = t["kwh"] * cfg.TARIFF_INR_PER_KWH + t["water_l"] / 1000 * cfg.WATER_INR_PER_KL
    return {"kwh": round(t["kwh"]), "waste_kwh": round(t["waste_kwh"]), "water_kl": round(t["water_l"] / 1000, 1),
            "leak_kl": round(t["leak_l"] / 1000, 1), "overflow_hours": round(t["overflow_min"] / 60, 1),
            "bill_inr": round(inr), "co2_kg": round(t["kwh"] * cfg.GRID_EF_KG_PER_KWH)}


@lru_cache(maxsize=64)
def _simulate(auto_off: int | None, led: bool, fix_leaks: bool, consolidate: bool, pickup: bool, days: int) -> dict:
    pol = Policy(auto_off_minutes=auto_off, led_retrofit=led, leak_cap_hours=1.0 if fix_leaks else None,
                 release_no_shows=consolidate, extra_pickup=pickup)
    s = MockSource(load_campus(), START, seed=SEED, policy=pol, record_history=False)
    s.fast_forward(START + timedelta(days=days), step_minutes=10)
    return _metrics(s)


def run(policy: dict, days: int = 30) -> dict:
    auto_off = int(policy.get("auto_off_minutes") or 0) or None
    led, fix_leaks = bool(policy.get("led_retrofit")), bool(policy.get("fix_leaks"))
    consolidate, pickup = bool(policy.get("consolidate")), bool(policy.get("extra_pickup"))
    base = _simulate(None, False, False, False, False, days)
    new = _simulate(auto_off, led, fix_leaks, consolidate, pickup, days)

    campus = load_campus()
    rooms = [r for r in campus["rooms"] if r["type"] != "washroom"]
    tubes = sum(f["count"] for r in campus["rooms"] for f in r["fixtures"] if f["type"] == "tube_light")
    washrooms = sum(1 for r in campus["rooms"] if r["type"] == "washroom")
    capex = {}
    if auto_off:
        capex["Occupancy sensors / smart switches"] = len(rooms) * cfg.CAPEX["occupancy_sensor_per_room"]
    if led:
        capex["LED retrofit of tube lights"] = tubes * cfg.CAPEX["led_per_tube"]
    if fix_leaks:
        capex["Plumbing maintenance kit"] = washrooms * cfg.CAPEX["leak_fix_per_washroom"]
    opex_month = cfg.CAPEX["extra_pickup_per_day"] * 30 if pickup else 0

    scale = 30 / days
    delta = {k: round((base[k] - new[k]) * scale, 1) for k in base}
    monthly = round(delta["bill_inr"] - opex_month)
    total_capex = sum(capex.values())
    payback = round(total_capex / monthly, 1) if monthly > 0 and total_capex else (0 if total_capex == 0 else None)
    return {"days": days, "baseline": base, "policy": new, "delta_per_month": delta,
            "monthly_saving_inr": monthly, "annual_saving_inr": monthly * 12, "capex": capex,
            "capex_total_inr": total_capex, "opex_month_inr": opex_month, "payback_months": payback,
            "assumptions": {"tariff_inr_per_kwh": cfg.TARIFF_INR_PER_KWH, "water_inr_per_kl": cfg.WATER_INR_PER_KL,
                            "grid_ef": cfg.GRID_EF_KG_PER_KWH}}
