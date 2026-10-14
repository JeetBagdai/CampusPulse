"""MockSource: a deterministic campus simulator that stands in for real sensors.

Models occupancy from timetables and usage profiles, fixtures that people forget
to switch off, washroom water flow with leaks, and bin fill levels. Also keeps
hourly history so baselines, charts and reports have 30 days of data.
"""
import json
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import DATA_DIR, FIXTURE_WATTS
from .base import DataSource

# chance each fixture is left on when a room empties (tuned for a ~65-room campus)
FORGET_P = {"tube_light": 0.08, "led_light": 0.08, "fan": 0.07, "ac": 0.05, "projector": 0.12, "pc": 0.10, "exhaust": 0.0}
LIGHTS = ("tube_light", "led_light")
CV_FRESH_S = 10  # CV observations older than this (real seconds) are ignored

LIBRARY_PROFILE = {8: .1, 9: .25, 10: .4, 11: .55, 12: .45, 13: .3, 14: .45, 15: .55, 16: .5, 17: .35, 18: .25, 19: .15}
CANTEEN_PROFILE = {8: .15, 9: .2, 10: .45, 11: .3, 12: .6, 13: .8, 14: .4, 15: .3, 16: .55, 17: .35, 18: .2, 19: .15}
PICKUPS = [(8, 0), (17, 0)]
EXTRA_PICKUP = (12, 30)


@dataclass
class Policy:
    """Interventions evaluated by the what-if engine. Defaults = today's behaviour."""
    auto_off_minutes: int | None = None
    led_retrofit: bool = False
    leak_cap_hours: float | None = None
    release_no_shows: bool = False
    extra_pickup: bool = False


def _r(*key) -> float:
    """Stable pseudo-random number in [0,1) for a key (same across runs)."""
    return (zlib.crc32(repr(key).encode()) % 100000) / 100000


def load_campus() -> dict:
    return json.loads((DATA_DIR / "campus.json").read_text(encoding="utf-8"))


def _blank_totals() -> dict:
    return {"kwh": 0.0, "waste_kwh": 0.0, "water_l": 0.0, "leak_l": 0.0, "overflow_min": 0.0,
            "waste_events": 0, "leak_events": 0, "overflow_events": 0}


class MockSource(DataSource):
    def __init__(self, campus: dict, start: datetime, seed: int = 7, policy: Policy | None = None,
                 record_history: bool = True):
        self.campus = campus
        self.t = start
        self.seed = seed
        self.policy = policy or Policy()
        self.record_history = record_history
        self.buildings = [b["id"] for b in campus["buildings"] if b.get("monitored", True)]
        self.room_cfg = {r["id"]: r for r in campus["rooms"]}
        self.tt = {r["id"]: {(s["day"], s["hour"]): s for s in r.get("timetable", [])} for r in campus["rooms"]}
        self.rooms = {}
        self.washrooms = {}
        for r in campus["rooms"]:
            if r["type"] == "washroom":
                self.washrooms[r["id"]] = {"leak_lpm": 0.0, "leak_until": None, "flow_lpm": 0.0, "lights": False}
            else:
                self.rooms[r["id"]] = {"occ": 0, "on": {f["type"]: False for f in r["fixtures"]}, "empty_since": start,
                                       "force_empty_until": None, "injected_slot": None, "cv": None,
                                       "guard_day": None, "slot": None, "power_w": 0.0,
                                       "kwh_today": 0.0, "waste_kwh_today": 0.0, "waste_kwh_total": 0.0}
        self.bins = {b["id"]: {"fill": 20.0 + 30 * _r(b["id"]), "overflow": False} for b in campus["bins"]}
        self.bin_cfg = {b["id"]: b for b in campus["bins"]}
        self.today = {b: _blank_totals() for b in self.buildings}
        self.hour_acc = {b: _blank_totals() for b in self.buildings}
        self.history: list[dict] = []   # hourly
        self.daily: list[dict] = []     # per day
        self.totals = {b: _blank_totals() for b in self.buildings}  # since start (whole run)

    # ------------------------------------------------------------------ helpers
    def now(self) -> datetime:
        return self.t

    def _rand(self, *key) -> float:
        return _r(self.seed, *key)

    def watts(self, ftype: str) -> float:
        if ftype == "tube_light" and self.policy.led_retrofit:
            return FIXTURE_WATTS["led_light"]
        return FIXTURE_WATTS[ftype]

    def _target(self, rid: str, t: datetime):
        """Expected occupancy and the scheduled slot (if any) for a room at time t."""
        cfg, st = self.room_cfg[rid], self.rooms[rid]
        cap, sched = cfg["capacity"], cfg["schedule"]
        dow, h, m = t.weekday(), t.hour, t.minute
        r = _r(rid, t.date().toordinal(), h)
        inj = st["injected_slot"]
        if inj and t < inj["until"]:
            return 3, inj
        if sched == "timetable":
            slot = self.tt[rid].get((dow, h))
            if not slot or m >= 50:
                return 0, None
            if slot["no_show"]:
                return (0, None) if self.policy.release_no_shows else (2 + int(r * 3), slot)
            ramp = min(1.0, (m + 1) / 5)
            return int(cap * slot["fill"] * (0.9 + 0.2 * r) * ramp), slot
        if sched == "office":
            return (2 + int(r * 5)) if dow < 6 and 9 <= h < 17 else 0, None
        if sched == "library":
            return (int(cap * LIBRARY_PROFILE[h] * (0.8 + 0.4 * r)) if dow < 6 and h in LIBRARY_PROFILE else 0), None
        if sched == "event":
            event_day = _r(rid, t.date().toordinal(), "event") < 0.3
            on = dow < 5 and event_day and h in (10, 11, 14, 15)
            return (int(cap * 0.7) if on else 0), ({"course": "Seminar / Event", "no_show": False} if on else None)
        if sched == "canteen":
            f = 0.6 if dow == 6 else 1.0
            return (int(cap * CANTEEN_PROFILE[h] * f * (0.8 + 0.4 * r)) if h in CANTEEN_PROFILE else 0), None
        if sched == "hostel":
            on = 18 <= h < 23 or (dow >= 5 and 10 <= h < 18)
            return (int(cap * (0.2 + 0.4 * r)) if on else 0), None
        return 0, None

    def _wanted(self, rid: str, slot) -> dict:
        cfg = self.room_cfg[rid]
        want = {}
        for f in cfg["fixtures"]:
            ft = f["type"]
            if ft == "projector":
                want[ft] = slot is not None
            elif ft == "pc":
                want[ft] = cfg["type"] != "lab" or slot is not None
            else:
                want[ft] = True
        return want

    def _cv(self, st):
        cv = st["cv"]
        return cv if cv and time.time() - cv["ts"] < CV_FRESH_S else None

    # --------------------------------------------------------------------- step
    def step(self, minutes: int = 1) -> None:
        dt = minutes
        prev_t = self.t
        self.t = self.t + timedelta(minutes=dt)
        t = self.t
        floor_occ: dict[tuple, int] = {}
        bld_occ = {b: 0 for b in self.buildings}
        bld_cap = {b: 1 for b in self.buildings}

        for rid, st in self.rooms.items():
            cfg = self.room_cfg[rid]
            b = cfg["building"]
            target, slot = self._target(rid, t)
            cv = self._cv(st)
            forced = st["force_empty_until"] and t < st["force_empty_until"]
            if forced:
                occ = 0
            elif cv and cv.get("people") is not None:
                occ = cv["people"]
            else:
                occ = target
            prev_occ = st["occ"]
            st["occ"], st["slot"] = occ, slot

            if occ > 0:
                st["on"].update(self._wanted(rid, slot))
                st["empty_since"] = None
            else:
                if prev_occ > 0:
                    st["empty_since"] = t
                    kept = False
                    for ft, on in st["on"].items():
                        if on:
                            keep = self._rand(rid, t, ft, "forget") < FORGET_P.get(ft, 0)
                            st["on"][ft] = keep
                            kept = kept or keep
                    if kept:
                        self._acc(b, "waste_events", 1)
                if t.hour == 21 and st["guard_day"] != t.date():
                    st["guard_day"] = t.date()
                    if self._rand(rid, t.date(), "guard") < 0.8:
                        st["on"] = {k: False for k in st["on"]}
                if (self.policy.auto_off_minutes and st["empty_since"]
                        and (t - st["empty_since"]).total_seconds() / 60 >= self.policy.auto_off_minutes):
                    st["on"] = {k: False for k in st["on"]}
            if cv:
                for ft in st["on"]:
                    if ft in LIGHTS and cv.get("lights_on") is not None:
                        st["on"][ft] = cv["lights_on"]
                    if ft == "fan" and cv.get("fans_on") is not None:
                        st["on"][ft] = cv["fans_on"]

            power = sum(f["count"] * self.watts(f["type"]) for f in cfg["fixtures"] if st["on"][f["type"]])
            st["power_w"] = power
            kwh = power * dt / 60 / 1000
            st["kwh_today"] += kwh
            self._acc(b, "kwh", kwh)
            if occ == 0 and power > 0:
                st["waste_kwh_today"] += kwh
                st["waste_kwh_total"] += kwh
                self._acc(b, "waste_kwh", kwh)
            key = (b, cfg["floor"])
            floor_occ[key] = floor_occ.get(key, 0) + occ
            bld_occ[b] += occ
            bld_cap[b] += cfg["capacity"]

        for wid, w in self.washrooms.items():
            cfg = self.room_cfg[wid]
            b = cfg["building"]
            focc = floor_occ.get((b, cfg["floor"]), 0)
            usage = focc * 0.02 * (0.6 + 0.8 * self._rand(wid, t, "use"))
            if w["leak_lpm"] == 0 and self._rand(wid, t, "leak") < dt / (25 * 1440):
                dur = 6 + 42 * self._rand(wid, t, "dur")
                if self.policy.leak_cap_hours:
                    dur = min(dur, self.policy.leak_cap_hours)
                w["leak_lpm"] = round(1.5 + 3.5 * self._rand(wid, t, "rate"), 1)
                w["leak_until"] = t + timedelta(hours=dur)
                self._acc(b, "leak_events", 1)
            if w["leak_until"] and t >= w["leak_until"]:
                w["leak_lpm"], w["leak_until"] = 0.0, None
            w["flow_lpm"] = usage + w["leak_lpm"]
            w["usage_lpm"] = usage
            w["floor_occ"] = focc
            self._acc(b, "water_l", w["flow_lpm"] * dt)
            self._acc(b, "leak_l", w["leak_lpm"] * dt)
            w["lights"] = 7 <= t.hour < 21 and focc > 0
            if w["lights"]:
                self._acc(b, "kwh", sum(f["count"] * self.watts(f["type"]) for f in cfg["fixtures"]) * dt / 60000)

        campus_act = sum(bld_occ.values()) / max(sum(bld_cap.values()), 1)
        pickups = PICKUPS + ([EXTRA_PICKUP] if self.policy.extra_pickup else [])
        for bid_, bn in self.bins.items():
            cfg = self.bin_cfg[bid_]
            b = cfg["building"]
            act = bld_occ[b] / bld_cap[b] if b in bld_occ else campus_act
            bn["fill"] = min(100.0, bn["fill"] + cfg["rate"] * 12 * (0.2 + 1.6 * act) * dt / 60)
            for ph, pm in pickups:
                pt = t.replace(hour=ph, minute=pm, second=0, microsecond=0)
                if prev_t < pt <= t:
                    bn["fill"] = 3.0
            full = bn["fill"] >= 100
            if full and not bn["overflow"]:
                self._acc(b if b in self.today else self.buildings[0], "overflow_events", 1)
            if full:
                self._acc(b if b in self.today else self.buildings[0], "overflow_min", dt)
            bn["overflow"] = full

        if t.hour != prev_t.hour:
            self._roll_hour(prev_t)
        if t.date() != prev_t.date():
            self._roll_day(prev_t)

    def _acc(self, b: str, key: str, v: float):
        self.today[b][key] += v
        self.hour_acc[b][key] += v
        self.totals[b][key] += v

    def _roll_hour(self, prev_t: datetime):
        if self.record_history:
            self.history.append({"t": prev_t.replace(minute=0, second=0, microsecond=0).isoformat(),
                                 "b": {b: {k: round(v, 3) for k, v in acc.items()} for b, acc in self.hour_acc.items()}})
            self.history = self.history[-24 * 35:]
        self.hour_acc = {b: _blank_totals() for b in self.buildings}

    def _roll_day(self, prev_t: datetime):
        if self.record_history:
            self.daily.append({"date": prev_t.date().isoformat(),
                               "b": {b: {k: round(v, 3) for k, v in acc.items()} for b, acc in self.today.items()}})
            self.daily = self.daily[-60:]
        self.today = {b: _blank_totals() for b in self.buildings}
        for st in self.rooms.values():
            st["kwh_today"] = st["waste_kwh_today"] = 0.0

    # ----------------------------------------------------------------- readings
    def readings(self) -> dict:
        t = self.t
        rooms = {}
        for rid, st in self.rooms.items():
            slot = st["slot"]
            rooms[rid] = {
                "occ": st["occ"], "power_w": round(st["power_w"]),
                "on": dict(st["on"]),
                "lights_on": any(v for k, v in st["on"].items() if k in LIGHTS),
                "fans_on": st["on"].get("fan", False),
                "scheduled": slot is not None, "course": slot["course"] if slot else None,
                "empty_min": int((t - st["empty_since"]).total_seconds() / 60) if st["empty_since"] else 0,
                "kwh_today": round(st["kwh_today"], 2), "waste_kwh_today": round(st["waste_kwh_today"], 2),
                "cv_live": self._cv(st) is not None,
            }
        washrooms = {wid: {"flow_lpm": round(w["flow_lpm"], 2), "floor_occ": w.get("floor_occ", 0),
                           "lights": w["lights"]} for wid, w in self.washrooms.items()}
        bins = {bid: {"fill": round(bn["fill"], 1)} for bid, bn in self.bins.items()}
        return {"rooms": rooms, "washrooms": washrooms, "bins": bins}

    # ------------------------------------------------------------------ actions
    def act(self, action: str, target: str) -> None:
        if action == "fix_room" and target in self.rooms:
            st = self.rooms[target]
            st["on"] = {k: False for k in st["on"]}
            st["force_empty_until"] = None
            st["injected_slot"] = None
        elif action == "fix_leak" and target in self.washrooms:
            self.washrooms[target].update(leak_lpm=0.0, leak_until=None)
        elif action == "empty_bin" and target in self.bins:
            self.bins[target]["fill"] = 3.0

    def inject(self, scenario: str, target: str) -> None:
        t = self.t
        if scenario == "lights_left_on" and target in self.rooms:
            st = self.rooms[target]
            st["force_empty_until"] = t + timedelta(hours=8)
            st["on"] = {k: True for k in st["on"]}
            st["occ"], st["empty_since"] = 0, t
        elif scenario == "leak" and target in self.washrooms:
            self.washrooms[target].update(leak_lpm=4.5, leak_until=None)
            self._acc(self.room_cfg[target]["building"], "leak_events", 1)
        elif scenario == "bin_spike" and target in self.bins:
            self.bins[target]["fill"] = 93.0
        elif scenario == "underused_class" and target in self.rooms:
            self.rooms[target]["injected_slot"] = {"course": "Guest Lecture (booked)", "no_show": True,
                                                   "until": t + timedelta(hours=1)}

    def set_cv_override(self, room_id, people, lights_on, fans_on) -> None:
        if room_id in self.rooms:
            self.rooms[room_id]["cv"] = {"people": people, "lights_on": lights_on, "fans_on": fans_on, "ts": time.time()}

    def fast_forward(self, until: datetime, step_minutes: int = 10) -> None:
        while self.t < until:
            self.step(min(step_minutes, max(1, int((until - self.t).total_seconds() // 60))))
