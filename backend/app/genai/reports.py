"""Weekly sustainability report and NAAC Criterion 7 green-audit report.
The engine computes every figure; the LLM only writes prose around them, and
each section is checked by the numeric validator (falls back to a template)."""
import asyncio
import json
from datetime import datetime

from .. import config as cfg
from .. import whatif
from . import llm
from .validator import check_numbers, facts_numbers


def _sum(daily: list[dict], b: str | None = None) -> dict:
    keys = ["kwh", "waste_kwh", "water_l", "leak_l", "overflow_min", "waste_events", "leak_events", "overflow_events"]
    out = dict.fromkeys(keys, 0.0)
    for d in daily:
        for bid, v in d["b"].items():
            if b is None or bid == b:
                for k in keys:
                    out[k] += v[k]
    return out


async def build_facts(engine, kind: str) -> dict:
    days = 7 if kind == "weekly" else 30
    daily = engine.src.daily[-days:]
    tot = _sum(daily)
    t, w, ef = cfg.TARIFF_INR_PER_KWH, cfg.WATER_INR_PER_KL, cfg.GRID_EF_KG_PER_KWH
    buildings = {}
    for b, bc in ((b, engine.bld_cfg[b]) for b in engine.src.buildings):
        s = _sum(daily, b)
        buildings[b] = {"name": bc["name"], "energy_kwh": round(s["kwh"]), "waste_kwh": round(s["waste_kwh"]),
                        "waste_share_pct": round(100 * s["waste_kwh"] / max(s["kwh"], 1), 1),
                        "water_kl": round(s["water_l"] / 1000, 1), "leak_kl": round(s["leak_l"] / 1000, 1)}
    top_rooms = sorted(engine.src.rooms.items(), key=lambda kv: kv[1]["waste_kwh_total"], reverse=True)[:5]
    issues = list(engine.issues.values())
    verified = [i for i in issues if i["status"] == "verified"]
    mttr = None
    if verified:
        mins = [(datetime.fromisoformat(i["verified_at"]) - datetime.fromisoformat(i["created_at"])).total_seconds() / 60
                for i in verified]
        mttr = round(sum(mins) / len(mins))
    rec = await asyncio.to_thread(whatif.run, {"auto_off_minutes": 10, "led_retrofit": True, "fix_leaks": True})
    no_show_slots = sum(1 for r in engine.campus["rooms"] for s in r.get("timetable", []) if s["no_show"])
    return {
        "report": kind, "period": {"from": daily[0]["date"] if daily else None, "to": daily[-1]["date"] if daily else None,
                                   "days": len(daily)},
        "campus": engine.campus["name"],
        "energy": {"total_kwh": round(tot["kwh"]), "bill_inr": round(tot["kwh"] * t), "waste_kwh": round(tot["waste_kwh"]),
                   "waste_inr": round(tot["waste_kwh"] * t), "waste_share_pct": round(100 * tot["waste_kwh"] / max(tot["kwh"], 1), 1),
                   "co2_kg": round(tot["kwh"] * ef), "avoidable_co2_kg": round(tot["waste_kwh"] * ef),
                   "waste_events": int(tot["waste_events"])},
        "water": {"total_kl": round(tot["water_l"] / 1000, 1), "leak_kl": round(tot["leak_l"] / 1000, 1),
                  "leak_inr": round(tot["leak_l"] / 1000 * w), "leak_share_pct": round(100 * tot["leak_l"] / max(tot["water_l"], 1), 1),
                  "leak_events": int(tot["leak_events"])},
        "waste": {"bins_monitored": len(engine.bin_cfg), "overflow_events": int(tot["overflow_events"]),
                  "overflow_hours": round(tot["overflow_min"] / 60, 1), "segregation_streams": ["wet (food)", "dry (mixed)"]},
        "space": {"underused_bookings_per_week": no_show_slots},
        "buildings": buildings,
        "top_waste_rooms": [{"room": r, "name": engine.name(r), "waste_kwh": round(v["waste_kwh_total"])} for r, v in top_rooms],
        "campuspulse_session": {"issues_detected": len(issues), "issues_verified_fixed": len(verified),
                                "saved_inr": round(engine.saved["inr"]), "avg_minutes_to_verified_fix": mttr,
                                "citizen_reports": sum(1 for i in issues if "citizen" in i["detected_by"])},
        "recommendation": {"policy": "Auto-off after 10 min + LED retrofit + leak alerts",
                           "monthly_saving_inr": rec["monthly_saving_inr"], "annual_saving_inr": rec["annual_saving_inr"],
                           "capex_inr": rec["capex_total_inr"], "payback_months": rec["payback_months"],
                           "co2_saved_kg_per_month": rec["delta_per_month"]["co2_kg"]},
        "constants": {"tariff_inr_per_kwh": t, "tariff_source": cfg.TARIFF_SOURCE, "water_inr_per_kl": w,
                      "water_source": cfg.WATER_SOURCE, "grid_ef_kg_per_kwh": ef, "grid_ef_source": cfg.GRID_EF_SOURCE},
    }


def _fallback(kind: str, f: dict) -> dict:
    e, wt, ws, r = f["energy"], f["water"], f["waste"], f["recommendation"]
    if kind == "weekly":
        return {
            "executive_summary": f"Over {f['period']['days']} days the campus used {e['total_kwh']} kWh (₹{e['bill_inr']}). "
                                 f"{e['waste_kwh']} kWh ({e['waste_share_pct']}%) was consumed in empty rooms, and "
                                 f"{wt['leak_kl']} kL of water was lost to leaks.",
            "highlights": [f"{f['campuspulse_session']['issues_verified_fixed']} issues fixed and verified, saving ₹{f['campuspulse_session']['saved_inr']}.",
                           f"{ws['bins_monitored']} bins monitored with {ws['overflow_events']} overflow events."],
            "concerns": [f"Top wasteful room: {f['top_waste_rooms'][0]['name']} ({f['top_waste_rooms'][0]['waste_kwh']} kWh).",
                         f"{wt['leak_events']} leak events ({wt['leak_share_pct']}% of water)."],
            "actions": [f"{r['policy']}: saves ₹{r['monthly_saving_inr']} per month, payback {r['payback_months']} months."],
        }
    return {
        "7.1.2": f"The institution monitors electricity continuously through CampusPulse. In the period, {e['total_kwh']} kWh "
                 f"was consumed; {e['waste_kwh']} kWh ({e['waste_share_pct']}%) was identified as avoidable use in unoccupied rooms "
                 f"and acted upon. Planned measure: {r['policy']} (₹{r['monthly_saving_inr']} per month, payback {r['payback_months']} months).",
        "7.1.3": f"{ws['bins_monitored']} bins with wet and dry streams are monitored for fill level; {ws['overflow_events']} "
                 "overflow events were recorded and cleared through work orders.",
        "7.1.4": f"Water use of {wt['total_kl']} kL was metered per washroom block; {wt['leak_events']} leak events "
                 f"({wt['leak_kl']} kL) were detected through night-flow analysis.",
        "7.1.5": f"Students report issues by photo; {f['campuspulse_session']['citizen_reports']} citizen reports were raised "
                 "in this session.",
        "7.1.6": f"A continuous energy and environment audit is maintained. Carbon footprint for the period: {e['co2_kg']} kg CO2, "
                 f"of which {e['avoidable_co2_kg']} kg was avoidable.",
        "summary": f"Continuous audit covering {f['period']['days']} days of energy, water and waste data.",
    }


async def generate(engine, kind: str) -> dict:
    facts = await build_facts(engine, kind)
    fallback = _fallback(kind, facts)
    sections, validation, model = dict(fallback), {}, None
    if llm.available():
        if kind == "weekly":
            spec = ('{"executive_summary": str (3 sentences), "highlights": [3 str], "concerns": [3 str], "actions": [3 str]}')
            role = "a weekly sustainability report for the college principal"
        else:
            spec = "{" + ", ".join(f'"{k}": str (one formal paragraph for NAAC metric {k} {v})' for k, v in cfg.NAAC_SECTIONS) + \
                   ', "summary": str (2 sentences)}'
            role = ("the environment section (Criterion 7.1) of a NAAC Self Study Report / green audit. "
                    "Formal, factual tone suitable for accreditation")
        sys = (f"You write {role}. Return JSON exactly in this shape: {spec}. Use ONLY the facts provided. "
               "Every number you write must appear in the facts (you may round to whole numbers). "
               "Do not compute new percentages or totals. Use ₹ for rupees. The 'recommendation' is a proposal that is "
               "NOT yet implemented: describe it as recommended/planned. Do not claim any facility (solar, sensors, "
               "composting) exists unless it is in the facts; CampusPulse monitoring, work orders and photo reporting do exist. "
               "Glossary: 'waste_kwh', 'waste_inr', 'waste_share_pct', 'waste_events' and 'top_waste_rooms' mean ELECTRICITY "
               "used in unoccupied rooms (avoidable energy use), not solid waste and not waste-to-energy. The 'waste' "
               "section is about solid-waste bins. There is no waste-to-energy plant.")
        try:
            out = await llm.chat_json([{"role": "system", "content": sys},
                                       {"role": "user", "content": json.dumps(facts, default=str)}], max_tokens=3000)
            allowed = facts_numbers(facts)
            for key in fallback:
                if key not in out:
                    validation[key] = "missing"
                    continue
                text = json.dumps(out[key], ensure_ascii=False)
                bad = check_numbers(text, allowed)
                if bad:
                    validation[key] = {"rejected_numbers": bad}
                else:
                    sections[key], validation[key] = out[key], "ok"
            model = "llm"
        except Exception as e:  # noqa: BLE001
            validation["error"] = str(e)[:200]
    return {"kind": kind, "generated_at": engine.src.now().isoformat(), "facts": facts, "sections": sections,
            "validation": validation, "source": model or "template",
            "naac_sections": cfg.NAAC_SECTIONS if kind == "naac" else None}
