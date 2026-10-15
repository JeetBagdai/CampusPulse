"""Generates the campus twin (data/campus.json) from real OpenStreetMap outlines of
Dayananda Sagar University, Harohalli (data/osm_dsu.json, © OpenStreetMap contributors, ODbL).

Buildings, floors, roads and pitches are real; rooms, fixtures, timetables and all
sensor data are simulated and placed inside each building's footprint.
Deterministic: same seed, same campus.  Run from backend/:  python scripts/gen_campus.py
"""
import json
import math
import random
from pathlib import Path

rng = random.Random(42)
DATA = Path(__file__).resolve().parent.parent / "data"
OSM = json.loads((DATA / "osm_dsu.json").read_text(encoding="utf-8"))
OUT = DATA / "campus.json"

FLOOR_H = 6.0  # metres per floor (slightly exaggerated so floors read clearly in 3D)

FIXTURES = {
    "classroom": [("tube_light", 12), ("fan", 6), ("projector", 1)],
    "lab": [("tube_light", 16), ("fan", 4), ("ac", 2), ("pc", 30)],
    "staff_room": [("led_light", 8), ("fan", 4), ("ac", 1)],
    "reading_hall": [("led_light", 30), ("ac", 4)],
    "seminar_hall": [("led_light", 24), ("ac", 4), ("projector", 1)],
    "canteen": [("tube_light", 20), ("fan", 10)],
    "common_room": [("led_light", 10), ("fan", 4)],
    "washroom": [("led_light", 4), ("exhaust", 1)],
}
CAPACITY = {"classroom": 60, "lab": 30, "staff_room": 12, "reading_hall": 120, "seminar_hall": 150,
            "canteen": 200, "common_room": 40, "washroom": 0}
SCHEDULE = {"classroom": "timetable", "lab": "timetable", "staff_room": "office", "reading_hall": "library",
            "seminar_hall": "event", "canteen": "canteen", "common_room": "hostel", "washroom": "washroom"}
NAMES = {"classroom": "Classroom", "lab": "Lab", "staff_room": "Staff Room", "reading_hall": "Library",
         "seminar_hall": "Seminar Hall", "canteen": "Dining Hall", "common_room": "Common Room", "washroom": "Washroom"}
COURSES = ["Data Structures", "Thermodynamics", "Digital Electronics", "Engg. Maths III", "Machine Learning",
           "Operating Systems", "Fluid Mechanics", "Signals & Systems", "DBMS", "Computer Networks",
           "Anatomy", "Physiology", "Pharmacology", "Biochemistry", "Nursing Foundations", "Pharmaceutics"]


def academic(wr):
    return ["classroom", "classroom", "lab", "washroom" if wr else "classroom"]


# Monitored buildings: OSM name -> (code, display name, floors if OSM has none, colour, per-floor room plan)
PLAN = {
    "DSU School of Engineering": ("E", "School of Engineering", 5, "#38bdf8", {
        1: ["staff_room", "classroom", "lab", "washroom"], 2: academic(False), 3: academic(True),
        4: academic(False), 5: ["seminar_hall", "lab", "classroom", "washroom"]}),
    "School of Health Sciences": ("H", "School of Health Sciences", 4, "#2dd4bf", {
        1: ["reading_hall", "lab", "washroom"], 2: ["classroom", "lab", "classroom"],
        3: ["classroom", "lab", "washroom"], 4: ["classroom", "lab", "classroom"]}),
    "Nursing sciences": ("N", "School of Nursing Sciences", 3, "#34d399", {
        1: ["classroom", "lab", "washroom"], 2: ["classroom", "lab"], 3: ["classroom", "staff_room"]}),
    "Pharamacy Department": ("P", "Department of Pharmacy", 3, "#a3e635", {
        1: ["lab", "classroom", "washroom"], 2: ["lab", "lab"], 3: ["classroom", "staff_room"]}),
    "Hostel Mess": ("M", "Hostel Mess", 1, "#fb923c", {1: ["canteen", "washroom"]}),
    "Tummy Trails": ("T", "Tummy Trails Food Court", 1, "#fb923c", {1: ["canteen"]}),
}
HOSTEL_PLAN = {1: ["common_room", "washroom"], 2: ["common_room"], 3: ["common_room"]}
HOSTELS = [  # (osm name, approx centre to pick the right outline, code, display name)
    ("Boys Hostels", (-345, 182), "B1", "Boys Hostel 1"),
    ("Boys Hostels", (-408, 267), "B2", "Boys Hostel 2"),
    ("Girls Hostel", (-261, 127), "G1", "Girls Hostel 1"),
    ("Girsls Hostel 2", (-451, 211), "G2", "Girls Hostel 2"),
]
SKIP = [("Boys Hostels", (-428, 242))]  # duplicate outline in OSM, overlaps its neighbours
CONTEXT_NAMES = {"CD Simer": "CD Simer", "CD Simer Hospital": "CD Simer Hospital",
                 "CD Simer Staff Quarter": "Staff Quarters", "Animal House and Laundry": "Animal House & Laundry",
                 "Construction": "Under construction"}


def centroid(pts):
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return sum(xs) / len(xs), sum(zs) / len(zs)


def obb(pts):
    """Oriented bounding box via PCA: centre, length (main axis), width, angle (radians, in the x-z plane)."""
    pts = pts[:-1] if pts[0] == pts[-1] else pts
    cx, cz = centroid(pts)
    sxx = sum((x - cx) ** 2 for x, _ in pts)
    szz = sum((z - cz) ** 2 for _, z in pts)
    sxz = sum((x - cx) * (z - cz) for x, z in pts)
    a = 0.5 * math.atan2(2 * sxz, sxx - szz)
    ca, sa = math.cos(a), math.sin(a)
    us = [(x - cx) * ca + (z - cz) * sa for x, z in pts]
    vs = [-(x - cx) * sa + (z - cz) * ca for x, z in pts]
    mu, mv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    return (cx + mu * ca - mv * sa, cz + mu * sa + mv * ca), max(us) - min(us), max(vs) - min(vs), a


def local_to_world(c, a, u, v):
    return [round(c[0] + u * math.cos(a) - v * math.sin(a), 2), round(c[1] + u * math.sin(a) + v * math.cos(a), 2)]


def clip_rect(poly, u0, u1, v0, v1):
    """Sutherland-Hodgman: clip a polygon (local u,v coords) to the rectangle [u0,u1] x [v0,v1]."""
    def clip(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_u(k):
        return lambda p, q: (k, p[1] + (q[1] - p[1]) * (k - p[0]) / (q[0] - p[0]))

    def at_v(k):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (k - p[1]) / (q[1] - p[1]), k)

    pts = list(poly)
    for inside, cross in ((lambda p: p[0] >= u0, at_u(u0)), (lambda p: p[0] <= u1, at_u(u1)),
                          (lambda p: p[1] >= v0, at_v(v0)), (lambda p: p[1] <= v1, at_v(v1))):
        if not pts:
            break
        pts = clip(pts, inside, cross)
    return pts


def area(pts):
    return abs(sum(pts[i - 1][0] * p[1] - p[0] * pts[i - 1][1] for i, p in enumerate(pts))) / 2


def equal_area_cuts(poly, n, axis, lo, hi, band=None):
    """Positions along `axis` (0 = u, 1 = v) splitting the polygon into n slices of equal area.
    `band` limits the other axis to (b0, b1)."""
    big = 1e6
    b0, b1 = band or (-big, big)

    def part(k):
        if axis == 0:
            return area(clip_rect(poly, lo, k, b0, b1) or [(0, 0)] * 3)
        return area(clip_rect(poly, -big, big, lo, k) or [(0, 0)] * 3)

    total = part(hi)
    cuts = [lo]
    for i in range(1, n):
        want, a, b = total * i / n, cuts[-1], hi
        for _ in range(40):  # bisection
            m = (a + b) / 2
            a, b = (m, b) if part(m) < want else (a, m)
        cuts.append((a + b) / 2)
    return cuts + [hi]


def poly_centroid(pts):
    a = sum(pts[i - 1][0] * p[1] - p[0] * pts[i - 1][1] for i, p in enumerate(pts)) / 2
    if abs(a) < 1e-6:
        return centroid(pts)
    cx = sum((pts[i - 1][0] + p[0]) * (pts[i - 1][0] * p[1] - p[0] * pts[i - 1][1]) for i, p in enumerate(pts)) / (6 * a)
    cz = sum((pts[i - 1][1] + p[1]) * (pts[i - 1][0] * p[1] - p[0] * pts[i - 1][1]) for i, p in enumerate(pts)) / (6 * a)
    return cx, cz


def timetable():
    """Mon-Sat 9:00-16:00 hourly slots (13:00 lunch). ~70% booked, ~10% of bookings are no-shows."""
    slots = []
    for day in range(6):
        for hour in [9, 10, 11, 12, 14, 15, 16]:
            if day == 5 and hour >= 13:
                continue
            if rng.random() < 0.7:
                slots.append({"day": day, "hour": hour, "course": rng.choice(COURSES),
                              "fill": round(rng.uniform(0.55, 0.95), 2), "no_show": rng.random() < 0.1})
    return slots


def near(b, target, tol=12):
    c = centroid(b["footprint"])
    return abs(c[0] - target[0]) < tol and abs(c[1] - target[1]) < tol


buildings, rooms, bins, context = [], [], [], []
used = set()


def add_building(osm, code, name, floors, color, plan):
    used.add(osm["osm_id"])
    c, length, width, a = obb(osm["footprint"])
    floors = int(osm.get("levels") or floors)
    buildings.append({"id": code, "name": name, "floors": floors, "color": color, "monitored": True,
                      "footprint": osm["footprint"], "center": [round(c[0], 1), round(c[1], 1)]})
    # building outline in its own axis frame (u along the long side, v across)
    ring = osm["footprint"][:-1] if osm["footprint"][0] == osm["footprint"][-1] else osm["footprint"]
    ca, sa = math.cos(a), math.sin(a)
    local = [((x - c[0]) * ca + (z - c[1]) * sa, -(x - c[0]) * sa + (z - c[1]) * ca) for x, z in ring]
    L, W = length, width
    GAP = 0.8  # half the gap left between neighbouring rooms, so each room reads as its own block
    for floor in range(1, floors + 1):
        cells = plan.get(floor) or plan[max(plan)]
        rows = 2 if W > 40 and len(cells) >= 4 else 1
        cols = math.ceil(len(cells) / rows)
        cw, cd = L / cols, W / rows
        # divide the real outline so every room gets the same floor area (no slivers at odd corners)
        vcuts = equal_area_cuts(local, rows, 1, -W / 2, W / 2)
        ucuts = [equal_area_cuts(local, cols, 0, -L / 2, L / 2, (vcuts[r], vcuts[r + 1])) for r in range(rows)]
        n = 0
        for i, rtype in enumerate(cells):
            col, row = i % cols, i // cols
            u0, u1 = ucuts[row][col], ucuts[row][col + 1]
            v0, v1 = vcuts[row], vcuts[row + 1]
            cell = clip_rect(local, u0 + (GAP if col else 0.6), u1 - (GAP if col < cols - 1 else 0.6),
                             v0 + (GAP if row else 0.6), v1 - (GAP if row < rows - 1 else 0.6))
            if len(cell) < 3 or area(cell) < 4:  # outline doesn't reach this cell: fall back to a small box
                cell = [(u0 + cw * 0.3, v0 + cd * 0.3), (u1 - cw * 0.3, v0 + cd * 0.3),
                        (u1 - cw * 0.3, v1 - cd * 0.3), (u0 + cw * 0.3, v1 - cd * 0.3)]
            shape = [local_to_world(c, a, cu, cv) for cu, cv in cell]
            x, z = (round(q, 2) for q in poly_centroid(shape))
            if rtype == "washroom":
                rid = f"{code}-{floor}WR"
            else:
                n += 1
                rid = f"{code}-{floor}{n:02d}"
            room = {"id": rid, "name": f"{NAMES[rtype]} {floor}{n:02d}" if rtype in ("classroom", "lab") else NAMES[rtype],
                    "type": rtype, "building": code, "floor": floor, "capacity": CAPACITY[rtype],
                    "schedule": SCHEDULE[rtype], "pos": [x, (floor - 1) * FLOOR_H, z],
                    "size": [round(cw - 2, 1), FLOOR_H - 1.2, round(cd - 2, 1)], "rot": round(-a, 4),
                    "footprint": shape,
                    "fixtures": [{"type": t, "count": k} for t, k in FIXTURES[rtype]]}
            if rtype in ("classroom", "lab"):
                room["timetable"] = timetable()
            rooms.append(room)
    return c, length, width, a


osm_b = OSM["buildings"]
placed = {}
for osm in osm_b:
    if osm["name"] in PLAN:
        code, name, floors, color, plan = PLAN[osm["name"]]
        placed[code] = add_building(osm, code, name, floors, color, plan)
for osm_name, target, code, name in HOSTELS:
    osm = next(b for b in osm_b if b["name"] == osm_name and near(b, target))
    placed[code] = add_building(osm, code, name, 3, "#fbbf24", HOSTEL_PLAN)
for osm in osm_b:
    if osm["osm_id"] in used or any(osm["name"] == n and near(osm, t) for n, t in SKIP):
        continue
    context.append({"name": CONTEXT_NAMES.get(osm["name"]) or osm["name"],
                    "floors": int(osm.get("levels") or 2), "footprint": osm["footprint"]})

# Bins: just outside each monitored building (two at food places)
BIN_PLAN = [("E", "front"), ("E", "back"), ("H", "front"), ("N", "front"), ("P", "front"), ("M", "front"),
            ("M", "back"), ("T", "front"), ("T", "back"), ("B1", "front"), ("G1", "front"), ("B2", "front")]
for i, (code, side) in enumerate(BIN_PLAN, start=1):
    c, length, width, a = placed[code]
    v = (width / 2 + 4) * (1 if side == "front" else -1)
    x, z = local_to_world(c, a, 0, v)
    bname = next(b["name"] for b in buildings if b["id"] == code)
    food = code in ("M", "T")
    bins.append({"id": f"BIN-{i:02d}", "name": f"{bname} {'(food waste)' if food and side == 'back' else side}",
                 "building": code, "floor": 1, "pos": [x, 0, z], "capacity_l": 120,
                 "rate": round((0.9 if food else 0.45) * rng.uniform(0.8, 1.2), 2),
                 "kind": "food" if food else "mixed"})

# Room watched by the live webcam during the demo
LIVE_ROOM = "E-201"
for r in rooms:
    if r["id"] == LIVE_ROOM:
        r["camera"] = "cam-live"

staff = [
    {"role": "electrician", "name": "Electrical In-charge", "link": "electrical", "lang": "kn"},
    {"role": "plumber", "name": "Water & Plumbing In-charge", "link": "water", "lang": "hi"},
    {"role": "housekeeping", "name": "Housekeeping & Waste In-charge", "link": "waste", "lang": "kn"},
    {"role": "estate_manager", "name": "Estate Manager", "link": "estate", "lang": "en"},
]

# Camera framing: centre on the monitored buildings
xs = [p[0] for b in buildings for p in b["footprint"]]
zs = [p[1] for b in buildings for p in b["footprint"]]
cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
campus = {
    "name": "Dayananda Sagar University, Harohalli",
    "short_name": "DSU Harohalli",
    "attribution": OSM["attribution"],
    "disclaimer": "Building outlines from OpenStreetMap; rooms, sensors and readings are simulated.",
    "floor_height": FLOOR_H, "live_room": LIVE_ROOM,
    "view": {"target": [round(cx), 0, round(cz)], "camera": [round(cx) + 60, 580, round(cz) + 730]},
    "buildings": buildings, "rooms": rooms, "bins": bins, "staff": staff,
    "map": {"boundary": OSM["boundary"], "context": context,
            "roads": [r for r in OSM["roads"] if r["type"] not in ("path", "track")],
            "paths": [r for r in OSM["roads"] if r["type"] in ("path", "track")],
            "pitches": OSM["pitches"]},
}
OUT.write_text(json.dumps(campus, indent=1), encoding="utf-8")
print(f"wrote {OUT.name}: {len(buildings)} monitored buildings, {len(rooms)} rooms "
      f"({sum(r['type'] == 'washroom' for r in rooms)} washrooms), {len(bins)} bins, {len(context)} context buildings")
