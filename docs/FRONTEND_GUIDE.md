# CampusPulse frontend guide

Everything a frontend developer needs to understand, change or rebuild the CampusPulse UI. Read it together with the code in `frontend/src/`.

---

## 1. What the UI is

A single-page app that shows a **live 3D digital twin of a campus** (Dayananda Sagar University, Harohalli; real building outlines from OpenStreetMap) and everything around it:

| Route | Page | Purpose |
|---|---|---|
| `/` | `TwinPage` | 3D campus, live KPIs, issue pins, side panel (Issues / Trends / Activity, or room details) |
| `/issues` | `IssuesPage` | Work-order board in 4 columns: Dispatched → In progress → Verifying → Verified/closed |
| `/cameras` | `CamerasPage` | Live webcam → server-side YOLO detection → effect on the twin |
| `/whatif` | `WhatIfPage` | Policy toggles → 30-day simulated savings, payback, chart |
| `/reports` | `ReportsPage` | Auto-generated NAAC green audit / weekly report, printable |
| `/report` | `ReportPage` | **Mobile page for students**: photo report of a problem at a location (opened from a QR code). No app shell. |

Global overlays: **Copilot drawer** ("Ask campus"), **Staff messages drawer** (Telegram/WhatsApp feed + in-app reply), **Demo controls** (Ctrl+D).

---

## 2. Stack

| Concern | Choice |
|---|---|
| Build | **Vite 8** (Rolldown), React 19, plain JS (`.jsx`), no TypeScript |
| Styling | **Tailwind CSS v4** via `@tailwindcss/vite`, plus custom classes in `src/index.css` |
| 3D | **three.js**, `@react-three/fiber` v9, `@react-three/drei` v10 |
| Charts | Recharts |
| State | Zustand (`src/store.js`) |
| Routing | react-router-dom v7 |
| Icons | lucide-react (**no emojis anywhere**; see §6) |
| QR | qrcode.react |
| Fonts | Manrope (UI), JetBrains Mono (IDs, clock), from Google Fonts in `index.html` |

---

## 3. Run it

```bash
# backend (needed: the UI is empty without live data)
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt        # or requirements-render.txt (slim, no PyTorch)
cp .env.example .env                   # GROQ_API_KEY optional for AI features
uvicorn app.main:app --port 8002

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

- In **dev**, Vite proxies `/api` and `/ws` to `BACKEND_URL` (default `http://localhost:8002`); see `vite.config.js`. All fetches use **relative URLs**.
- In **production**, the backend serves `frontend/dist` itself (same origin). Unknown paths fall back to `index.html`, so client-side routes like `/report?loc=E-1WR` work.
- `npm run build` → `dist/`. Vendor chunks are split (`three`, `charts`, `react`) and pages are `React.lazy`-loaded, so non-3D pages don't download three.js.
- The dev server listens on the LAN (`host: true`), so phones on the same Wi-Fi can open `http://<laptop-ip>:5173`.

---

## 4. File map

```
frontend/
├─ index.html            fonts, theme-color, title
├─ vite.config.js        proxy, chunk splitting
└─ src/
   ├─ main.jsx           router: /report (bare) vs /* (App shell)
   ├─ App.jsx            header, desktop nav, mobile bottom tab bar, lazy routes, drawers
   ├─ index.css          design tokens + glass / btn / chip / input / well classes
   ├─ api.js             fetch helpers, wsUrl(), inr()/num()/hhmm() formatters
   ├─ store.js           Zustand store, WebSocket, STATUS_COLOR, TYPE_META
   ├─ components/
   │  ├─ Twin3D.jsx      the 3D scene (see §8)
   │  ├─ IssueCard.jsx   issue + work order card (used on Twin, Work orders)
   │  ├─ Icons.jsx       TypeIcon, RoleIcon, PriorityChip, SourceChip
   │  ├─ PhonePanel.jsx  staff messages drawer
   │  ├─ CopilotDrawer.jsx
   │  └─ DemoPanel.jsx
   └─ pages/             TwinPage, IssuesPage, CamerasPage, WhatIfPage, ReportsPage, ReportPage
```

---

## 5. Data: where everything comes from

### 5.1 Startup (`store.init`)
1. `GET /api/campus`: static campus description (retried every 1.5 s until the backend is up).
2. Open `WebSocket /ws/state`: the backend pushes a full **snapshot** every second. Auto-reconnects after 1.5 s.

All live UI renders from `useStore(s => s.snap)`. Select the narrowest slice you need (`useStore(s => s.snap?.kpis)`) to avoid re-rendering on every tick.

### 5.2 `GET /api/campus` (static)
```js
{
  name, short_name, attribution, disclaimer,
  floor_height: 6,                 // metres per floor in the scene
  live_room: "E-201",              // room watched by the webcam by default
  view: { target: [x,0,z], camera: [x,y,z] },   // default camera
  buildings: [{ id: "E", name, floors, color, monitored: true,
                footprint: [[x,z], ...], center: [x,z] }],
  rooms: [{ id: "E-201", name, type, building, floor, capacity, schedule,
            pos: [x, y, z],        // centre (x,z) and floor base y
            size: [w, h, d], rot,  // rot = rotation about Y (radians)
            fixtures: [{ type, count }], timetable?: [{ day, hour, course, fill, no_show }] }],
  bins: [{ id: "BIN-01", name, building, floor, pos: [x,0,z], capacity_l, kind }],
  staff: [{ role, name, link, lang }],
  map: { boundary: [[x,z]], context: [{ name, floors, footprint }],
         roads: [{ type, line: [[x,z]] }], paths: [...], pitches: [{ footprint }] },
  constants: { tariff_inr_per_kwh, water_inr_per_kl, grid_ef_kg_per_kwh, ...sources }
}
```
Coordinates are **metres** in a local frame: x = east, z = south (so north is −z), y = up. Room types: `classroom, lab, staff_room, reading_hall, seminar_hall, canteen, common_room, washroom`. IDs: `E-201` = building E, floor 2, room 01; `B1-1WR` = Boys Hostel 1, floor 1 washroom.

### 5.3 WebSocket snapshot (every 1 s)
```js
{
  clock: "2026-10-15T10:42:00", speed: 1, paused: false,
  kpis: { wasted_inr_today, kwh_today, waste_kwh_today, water_l_today, leak_l_today,
          co2_kg_today, waste_co2_kg_today, open_issues, saved_inr, saved_kwh, saved_l, saved_co2, score },
  buildings: { E: { score, energy_eff, water_eff, open_issues, kwh, waste_kwh, water_l, leak_l } },
  rooms: {
    "E-201": { occ, power_w, on: { tube_light: true, fan: false, ... }, lights_on, fans_on,
               scheduled, course, empty_min, kwh_today, waste_kwh_today, cv_live,
               status, issue },               // status: see §6.3; issue: open issue id or null
    "E-1WR": { flow_lpm, floor_occ, lights, status, issue }   // washrooms
  },
  bins: { "BIN-01": { fill, status, minutes_to_full, issue } },
  issues: [Issue],             // active first, then the 20 most recent closed
  workorders: { "WO-3": WorkOrder },
  feed: [Message],             // last 40 staff messages (in + out)
  events: [{ t, kind, text }], // activity log, newest first
  cv: { bindings: { "cam-live": "E-201" }, live: { "cam-live": {...latest detection} } },
  channel: "telegram" | "whatsapp-meta" | "whatsapp-twilio" | "console",
  wa_mode: "demo" | "all" | "off",
  llm: true,
  bot: { username, linked: ["electrician", ...] }
}
```
**Issue:** `id, type, target, target_name, building, location, title, status, priority (P1|P2|P3), created_at, rate_inr_hr, loss_inr, loss_kwh, loss_l, loss_co2, evidence{...}, detected_by[], demo, photo (url|null), reports_count, escalated, saved_inr, wo`.
Types: `ENERGY_WASTE, WATER_LEAK, BIN_OVERFLOW, LITTER, UNDERUSED_BOOKING`.
Statuses: `open → assigned → in_progress → resolved (verifying) → verified`, or `auto_closed` / `closed`.

**WorkOrder:** `id, issue_id, role, assignee, lang, content: { en: {title, summary, steps[], safety_note}, hi?, kn? }, source ("llm"|"template"), status`.

**Message (feed):** `id, ts, dir ("in"|"out"), role, text, channel, status, wo, buttons[]`.

### 5.4 REST endpoints used by the UI
| Method & path | Used by |
|---|---|
| `GET /api/campus` | store init |
| `GET /api/history?hours=1` → `{ hourly, daily }` | Trends chart |
| `POST /api/issues/{id}/resolve`, `POST /api/workorders/{id}/ack` | IssueCard |
| `GET /api/workorders/{id}?lang=en\|hi\|kn` → `{ ...wo, message }` | IssueCard language preview |
| `POST /api/cv/frame` (multipart `file`, `cam_id`) → detection + `annotated` (data-URL JPEG) | Cameras |
| `POST /api/cv/bind {cam_id, target}`, `POST /api/cv/calibrate?cam_id&state=on\|off`, `GET /api/cv/calibration` | Cameras |
| `POST /api/whatif {auto_off_minutes, led_retrofit, fix_leaks, consolidate}` | What-if |
| `POST /api/copilot {messages}` → `{ reply, tools[], verified, unverified_numbers }` | Copilot |
| `GET /api/reports/{naac\|weekly}` (cached per sim-day), `POST` same path (regenerate) | Reports |
| `POST /api/citizen-reports` (multipart `photo, loc, note`), `GET /api/citizen-reports/{ticket}`, `GET /api/locations` | `/report` page |
| `POST /api/wa/simulate {role, text, button_id}` | Messages drawer (in-app replies) |
| `POST /api/demo/inject {scenario, target}`, `/api/demo/speed?x=&paused=`, `/api/demo/jump?hour=`, `/api/demo/wa-mode?mode=`, `/api/demo/reset` | Demo controls |

---

## 6. Design system

### 6.1 Direction
Dark **teal-ink** base with soft blurred colour glows (teal, sky, emerald, amber) behind **frosted glass** panels. **No purple anywhere. No emojis**; all icons are lucide SVGs. Calm, data-dense, readable over a Zoom screen share.

### 6.2 Tokens (`index.css`, Tailwind v4 `@theme`)
| Token | Value | Use |
|---|---|---|
| `--color-ink` / body bg | `#06141a` | page background |
| `--color-accent` | `#2dd4bf` (teal-400) | primary accent, active nav, primary button (gradient to `#34d399`) |
| energy | `#fb7185` (rose) | energy waste |
| water | `#3b82f6` (blue) | water leak |
| waste | `#fbbf24` (amber) | bins, litter |
| underused | `#cbd5e1` (light steel) | underused booking |
| ok / fixed | `#34d399` (emerald) | verified, saved |
| `--color-line` | `rgba(255,255,255,0.10)` | borders (`border-line`) |
| text | `#e6f1f0`, secondary `slate-400`, muted `slate-500` | |

The background glow is `body::before` (fixed, blurred radial gradients).

### 6.3 Status colours (`STATUS_COLOR` in `store.js`), used by 3D rooms and legend
`idle #5b6b75` (empty/off), `active #2dd4bf` (occupied), `energy #fb7185`, `water #3b82f6`, `underused #cbd5e1`, `litter/waste #fbbf24`, `fixed/ok #34d399`. Washrooms use `#1d3b5c` when idle.

### 6.4 Surface classes (`index.css`)
| Class | Look | Where |
|---|---|---|
| `.glass` | white 9%→3% gradient, 1px white/12 border, inner top highlight, blur 18px | cards, KPI card, issue cards |
| `.glass-panel` | stronger frost, blur 26px, radius 22 | floating side panel, What-if controls, Reports toolbar, Cameras panel |
| `.glass-strong` | dark teal 80% + blur 24px | drawers, building labels, demo panel |
| `.glass-bar` | dark translucent + blur | header, mobile tab bar |
| `.well` | black 22% inset box | stat tiles inside glass |
| `.btn`, `.btn-primary`, `.btn-danger` | glass buttons; primary = teal→emerald gradient | |
| `.chip` | small pill | statuses, filters, tags |
| `.input` | dark translucent field, teal focus ring | |
| `.pulse-ring`, `.pop` | issue pin pulse, card fade-in | |

### 6.5 Important gotcha: custom classes beat Tailwind utilities
`.chip`, `.btn` and `.glass` are plain CSS defined **after** Tailwind, so they override utilities on the same element. `className="chip hidden"` does **not** hide the chip (this broke the mobile header once). Either:
- wrap: `<span className="hidden lg:inline-flex"><span className="chip">…</span></span>`, or
- use the important modifier: `!bg-teal-400/25`, `!py-1` (used throughout).

### 6.6 Icons (`components/Icons.jsx`)
`TypeIcon` (Zap, Droplets, Trash2, Sparkles, CalendarX per issue type, tinted by type colour), `RoleIcon` (Zap, Droplets, Trash2, Building2), `PriorityChip` (glowing dot: P1 rose, P2 orange, P3 amber), `SourceChip` (camera / student photo / sensor). Never render emoji characters; backend messages are emoji-free too.

---

## 7. Layout & responsiveness

- **Breakpoint `md` (768 px)** switches desktop ↔ phone.
- **Header** (`App.jsx`, h-14, glass-bar): logo + campus chip (≥lg) · nav pills (≥md) · clock (≥md) · live dot · demo · messages (with unread dot) · Ask campus (icon-only < sm).
- **Phones:** fixed **bottom tab bar** (5 icons); `main` gets `pb-[68px]`.
- **Twin page:** full-bleed 3D canvas. Desktop: floating `glass-panel` **side panel** on the right (`right-3 top-3 bottom-3 w-[380px]`). Phone: the same panel becomes a **bottom sheet** (`inset-x-2 bottom-2 h-[44%]`, drag-handle bar). KPI card top-left (full width on phones), Legend + Reset view bottom-left (Reset view moves top-right on phones).
- **Work orders:** 1 / 2 / 4 columns (`sm`, `xl`). **What-if:** stacked below `lg`. **Cameras:** feed + detections side by side ≥`lg`. **Reports:** tables scroll horizontally on phones.
- Drawers (Copilot, Messages) are full-screen on phones (`inset-2`) and floating cards on desktop. `html, body { overflow-x: hidden }` guards against sideways scroll.

---

## 8. The 3D twin (`components/Twin3D.jsx`)

### 8.1 Scene
- `<Canvas>` with transparent background (`gl.alpha`), so the CSS glow shows through. `dpr={[1, 1.5]}`.
- **Ground** plane + `gridHelper` (1500 m).
- **`StaticMap`** (memoised, never re-renders): campus boundary (dashed `Line`), sports pitches (flat shapes), **all roads as one `Line segments` draw call**, all paths as another, grey context buildings, and translucent coloured **building shells** (extruded footprints + `Edges`).
- **`RoomBox`** (memoised per room): a box at `pos` with `rotation.y = rot`, coloured by `status`; alert statuses pulse their emissive intensity in `useFrame`.
- **`Bin`**: open cylinder plus a fill cylinder coloured green/amber/rose by fill %.
- **`OrbitControls`** (`makeDefault`, ref used by **Reset view** → `controls.reset()`).

### 8.2 Footprints → 3D
A footprint `[[x,z],…]` becomes a `three.Shape` with points `(x, −z)`, extruded by `floors × floor_height`, then the mesh is rotated `−π/2` about X so the extrusion points up and the shape lands on the x/z ground plane.

### 8.3 Labels and pins are plain DOM, not drei `<Html>`
drei's `<Html>` creates a React root per element. With React 19 this produced "synchronously unmount a root" errors, made the first label render empty, and was slow with ~80 of them. Instead:
- building labels and issue pins are ordinary absolutely-positioned elements over the canvas, stored in `els` refs;
- **one `Projector` component** projects each anchor (`Vector3.project(camera)`) every frame and writes `transform: translate(...)` / `display` directly, with no React re-render;
- pins exist only for targets with an active issue.

### 8.4 Keeping the campus centred around the panel
`ViewOffset` calls `camera.setViewOffset(...)`: it shifts the rendered image **120 px left on desktop** (side panel) or **20% up on phones** (bottom sheet). It's applied to the projection, so it stays correct when the user orbits, and the label projection includes it automatically.

### 8.5 Hover
Room hover uses a plain DOM tooltip positioned from `pointer.offsetX/Y` (desktop only).

---

## 9. Page notes

- **IssueCard:** type icon tile, `PriorityChip`, status chip, location, ₹/h + loss or saved; full mode adds source chips, photo, the work order (assignee, "AI · numbers verified" vs template, EN/हिं/ಕನ್ನಡ preview fetched from `/api/workorders/{id}?lang=`), and actions **Noted** (ack) / **Mark done** / **Ask** (opens Copilot pre-filled).
- **Cameras:** `getUserMedia` → hidden `<video>` → every 500 ms draw to a hidden canvas → JPEG → `POST /api/cv/frame` (one request in flight at a time). The server returns an annotated JPEG (faces blurred, boxes drawn), which is what's displayed; raw video is never shown. Light calibration is saved server-side and shown as a badge.
- **What-if:** 250 ms debounce after toggles; results are cached server-side per policy.
- **Reports:** `GET` on open (cached per simulated day), **Regenerate** = `POST`; print CSS hides chrome (`.no-print`) and prints the white document.
- **`/report` (mobile):** location from `?loc=` (QR) or a picker; `<input type="file" accept="image/*" capture="environment">`; after submit, polls the ticket status every 3 s and shows a 4-step progress.
- **Demo controls (Ctrl+D):** inject `lights_left_on | underused_class | leak | bin_spike`, speed 1/5/15/60×, jump to 2 AM/8 AM/1 PM/9 PM, real-messaging mode, reset.

---

## 10. Performance rules (keep these)
1. Never put drei `<Html>` per item; use the DOM + `Projector` pattern.
2. Memoise static scene parts; pass primitive props (status string, fill number) to per-room components so `memo` works.
3. Batch line geometry (`Line segments`).
4. Disable Recharts animation (`isAnimationActive={false}`); the 1 Hz snapshot re-renders would restart it.
5. Keep pages lazy and vendor chunks split; don't import three.js outside `Twin3D`.
6. Subscribe to narrow store slices in components that don't need the whole snapshot.

---

## 11. Accessibility & polish to-dos (not done yet)
- Keyboard focus styles on glass buttons; `aria-label`s on icon-only buttons.
- Reduced-motion mode (pulse rings, pops).
- A text list alternative to the 3D view for screen readers.
- First 3D paint is slower on weak GPUs; consider a loading shimmer over the canvas.
