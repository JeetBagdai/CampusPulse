"""'Ask your campus' copilot: LLM with tool calling over live twin state.
Answers may only use numbers returned by the tools (checked by the validator)."""
import asyncio
import json
import re

from .. import whatif
from . import llm
from .validator import check_numbers, facts_numbers

SYSTEM = ("You are CampusPulse Copilot, assistant to a college estate manager. Answer ONLY from tool results; "
          "call tools to get data. Cite IDs (ISS-12, WO-3, E-201, BIN-05). Use ₹ for money. Never invent numbers: "
          "every number you write must come from a tool result. Be concise: at most 120 words, use short bullets. Do not use emojis.")

TOOLS = [
    {"type": "function", "function": {"name": "get_campus_summary", "description":
        "Today's KPIs, building scores, open issues by type, top wasteful rooms and fullest bins.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_issues", "description": "List issues.", "parameters": {
        "type": "object", "properties": {
            "status": {"type": "string", "enum": ["open", "all"]},
            "type": {"type": "string", "enum": ["ENERGY_WASTE", "WATER_LEAK", "BIN_OVERFLOW", "UNDERUSED_BOOKING", "LITTER"]},
            "building": {"type": "string", "description": "A, L or C"}}}}},
    {"type": "function", "function": {"name": "get_room", "description": "Live state, timetable and issues of one room or washroom.",
                                      "parameters": {"type": "object", "properties": {"room_id": {"type": "string"}},
                                                     "required": ["room_id"]}}},
    {"type": "function", "function": {"name": "get_history", "description": "Daily energy / water / waste totals per building.",
                                      "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "run_whatif", "description":
        "Simulate 30 days with a policy and return monthly savings, CO2 and payback.",
        "parameters": {"type": "object", "properties": {
            "auto_off_minutes": {"type": "integer"}, "led_retrofit": {"type": "boolean"},
            "fix_leaks": {"type": "boolean"}, "consolidate": {"type": "boolean"}}}}},
]


def campus_summary(engine) -> dict:
    snap_rooms = engine.last["rooms"]
    top = sorted(snap_rooms.items(), key=lambda kv: kv[1]["waste_kwh_today"], reverse=True)[:5]
    by_type: dict[str, int] = {}
    for iid in engine.open_by_key.values():
        t = engine.issues[iid]["type"]
        by_type[t] = by_type.get(t, 0) + 1
    bins = sorted(engine.last["bins"].items(), key=lambda kv: kv[1]["fill"], reverse=True)[:3]
    return {"clock": engine.src.now().isoformat(timespec="minutes"), "kpis": engine.kpis(),
            "buildings": {b: {"name": engine.bld_cfg[b]["name"], **s} for b, s in engine.scores().items()},
            "open_issues_by_type": by_type,
            "top_waste_rooms_today": [{"room": r, "name": engine.name(r), "waste_kwh": v["waste_kwh_today"]} for r, v in top],
            "fullest_bins": [{"bin": b, "name": engine.name(b), "fill_pct": v["fill"]} for b, v in bins]}


def _issues(engine, status="open", type=None, building=None) -> list:
    out = []
    for i in engine.issues.values():
        if status == "open" and i["status"] in ("verified", "auto_closed", "closed"):
            continue
        if type and i["type"] != type or building and i["building"] != building:
            continue
        out.append({k: i[k] for k in ("id", "type", "target", "target_name", "status", "priority", "rate_inr_hr", "wo")}
                   | {"loss_inr": round(i["loss_inr"], 1)})
    return out[-25:]


def _room(engine, room_id: str) -> dict:
    rid = room_id.upper()
    cfg_ = engine.room_cfg.get(rid)
    if not cfg_:
        return {"error": f"unknown room {room_id}"}
    dow = engine.src.now().weekday()
    live = engine.last["rooms"].get(rid) or engine.last["washrooms"].get(rid)
    return {"id": rid, "name": cfg_["name"], "type": cfg_["type"], "capacity": cfg_["capacity"],
            "location": engine.location(rid), "fixtures": cfg_["fixtures"], "live": live,
            "timetable_today": [s for s in cfg_.get("timetable", []) if s["day"] == dow],
            "issues": [i for i in _issues(engine, "all") if i["target"] == rid]}


def _history(engine, days: int = 7) -> list:
    return engine.src.daily[-max(1, min(days, 30)):]


async def _call(engine, name: str, args: dict):
    if name == "get_campus_summary":
        return campus_summary(engine)
    if name == "list_issues":
        return _issues(engine, args.get("status", "open"), args.get("type"), args.get("building"))
    if name == "get_room":
        return _room(engine, args.get("room_id", ""))
    if name == "get_history":
        return _history(engine, int(args.get("days", 7)))
    if name == "run_whatif":
        return await asyncio.to_thread(whatif.run, args)
    return {"error": f"unknown tool {name}"}


async def ask(engine, messages: list[dict]) -> dict:
    convo = [{"role": "system", "content": SYSTEM}] + [{"role": m["role"], "content": m["content"]} for m in messages[-8:]]
    results, calls = [], []
    for _ in range(5):
        msg = await llm.chat(convo, tools=TOOLS, max_tokens=1500)
        tcs = msg.get("tool_calls") or []
        if not tcs:
            answer = re.sub(r"\s*【([^】]*)】", r" (\1)", msg["content"])
            bad = check_numbers(answer, facts_numbers(results + [c["args"] for c in calls])) if results else []
            return {"reply": answer, "tools": calls, "verified": not bad, "unverified_numbers": bad, "model": msg["model"]}
        convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
        for tc in tcs:
            fn = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            res = await _call(engine, fn, args)
            results.append(res)
            calls.append({"name": fn, "args": args})
            convo.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res, default=str)[:12000]})
    return {"reply": "I couldn't finish that analysis. Please try a narrower question.", "tools": calls,
            "verified": False, "unverified_numbers": []}
