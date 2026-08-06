# ARGUS — Design System & Brand Document

**Status:** v0.1, derived from the approved Figma direction (5 reference screens: Add Assets, ARGUS Intelligence, Alerts board, Alert detail modal, Camera wall). This is the single source of truth for ARGUS UI. Every module — including the Drive / teleoperation cockpit — inherits this system.

> A few exact values (brand-blue hex, the type family, precise radii) are **eyeballed from the screens and marked `‹confirm›`**. Replace them with the real Figma token values (or tell me the font + hex and I'll pin them).

---

## 1. What ARGUS is

ARGUS is a multi-asset security & surveillance **intelligence platform**. It ingests many sensors (CCTV, drones, ground robots/UTVs, naval), detects and tracks threats, and lets an operator understand and act — with an AI copilot ("Ask Argus") in the loop everywhere.

**Asset types (modules):** Air (Drones) · Ground (UTVs — this is where teleop/Drive lives) · Naval (Boats) · Fixed (CCTV).

**Design essence:** *Serious capability, calmly presented.* Defense-grade in what it does; commercial-product-grade in how it looks. Think Linear/Vercel restraint with an operations-center backbone — **not** a tactical camo HUD. Dark, calm, confident, legible, fast.

**Principles**
1. **Calm under load.** Dark canvas, generous space, one accent. Density is organized, never noisy. The operator scans, never hunts.
2. **One blue, used with discipline.** Argus Blue means *interactive / active / selected*. Status meaning is carried by the semantic palette, not by the brand color.
3. **Truth at a glance.** System vitals are always visible (top bar). Severity is unmistakable (color + dot + label, never color alone).
4. **AI is ambient.** "Ask Argus" is a persistent companion, not a separate place.
5. **Product, not dashboard-template.** Cards earn their place; no AI-slop card mosaics, no decoration competing with the data.

---

## 2. Color system

Dark-first. Surfaces step up a neutral ladder; depth comes from surface + 1px hairline (+ soft shadow on overlays only). Drop these into the Tailwind theme / CSS vars.

```css
:root{
  /* Canvas & surfaces (neutral, slightly cool charcoal) */
  --bg:            #0B0C0E;   /* app canvas (deepest) */
  --surface-1:     #121417;   /* top bar, left rail, base panels */
  --surface-2:     #16181C;   /* cards, list rows */
  --surface-3:     #1C1F24;   /* elevated: modals, popovers, hovered cards */
  --surface-inset: #0E0F12;   /* wells: chat thread bg, video letterbox */

  /* Hairlines / borders (no heavy borders) */
  --line:          rgba(255,255,255,0.07);   /* default 1px divider/border */
  --line-strong:   rgba(255,255,255,0.12);   /* group separators, header underline */

  /* Text */
  --text:          #F5F7FA;   /* primary, headings (near-white) */
  --text-2:        #A4ABB4;   /* secondary, labels */
  --text-3:        #6B727B;   /* tertiary, captions, disabled */

  /* Brand accent — Argus Blue (interactive/active/selected ONLY) */
  --accent:        #2E8FFF;   /* ‹confirm› primary blue */
  --accent-strong: #1E73E6;   /* pressed/hover-darken */
  --accent-weak:   rgba(46,143,255,0.14); /* tint bg: active nav, selected row, chips */
  --accent-ring:   rgba(46,143,255,0.45);  /* 2px focus ring */

  /* Semantic status (meaning — never the brand blue) */
  --critical:      #FF4D4D;   /* high risk, critical alerts, REC, E-STOP */
  --critical-weak: rgba(255,77,77,0.12);   /* critical card wash / pill bg */
  --warning:       #F5A623;   /* medium risk, warning */
  --warning-weak:  rgba(245,166,35,0.14);
  --info:          #3B9EFF;   /* low risk, info (a lighter blue than brand) */
  --info-weak:     rgba(59,158,255,0.14);
  --success:       #22C55E;   /* nominal, resolved, confirmed action */
  --success-weak:  rgba(34,197,94,0.14);
}
```

**Usage rules**
- **Argus Blue is for interaction only:** active nav icon, primary buttons (`Take Action`, `Send`), selected tab/row, focus ring, map "your asset" markers, links. It is never a status meaning and never decorative.
- **Status = semantic palette.** Critical red, Warning amber, Info blue, Success green. Always pair the color with a dot and a text label (`● Critical`, `● NOMINAL`) — color is never the only signal (red/green-deficient operators).
- **Severity card wash:** critical items may use `--critical-weak` as a faint background tint + a `--critical` accent edge; keep it subtle.
- **Red is reserved** for critical/alert/REC/E-STOP/destructive. Don't spend it elsewhere.
- Text never sits on a saturated fill except white-on-`--accent` (buttons) and white-on-`--critical` (E-STOP).

---

## 3. Typography

Two families: a clean grotesque for everything, a mono for metrics/IDs/timestamps. The screens read as a neutral geometric sans with confident bold headings and tracked uppercase micro-labels.

- **Primary (UI/Display):** `‹confirm Figma font›` — recommend **Geist** or **General Sans** (modern, neutral, free). Fallback: `-apple-system, "Segoe UI", system-ui, sans-serif`. *(Avoid plain Inter as the named brand face unless that's literally the Figma font.)*
- **Mono (data):** **Geist Mono** / **JetBrains Mono**, `tabular-nums`. Used for: top-bar metrics (`4.2ms`, `9/9`, `247`), camera timestamps (`04:51:56.446`), IDs (`CAM-01`, `TRK-0847`), coordinates, counts.

**Type scale** (px / line-height / weight / tracking)

| Token | Use | Spec |
|---|---|---|
| display | page hero ("Which Asset Type…") | 40 / 1.1 / 700 / -0.01em |
| h1 | page title ("ALERTS", "ARGUS Intelligence") | 24 / 1.2 / 600 / -0.005em |
| h2 | section ("New Alerts", "Daily Digests") | 17 / 1.3 / 600 |
| stat | big KPI numbers ("20", "8.9/10") | 30 / 1.0 / 700 / tabular |
| card-title | card / alert title | 15 / 1.4 / 600 |
| body | default text | 14 / 1.5 / 400 |
| body-strong | emphasis in body | 14 / 1.5 / 600 |
| label | UPPERCASE micro-labels ("AIR PLATFORM", "OPERATOR") | 11 / 1.2 / 600 / +0.10em / uppercase / `--text-2` |
| caption | timestamps, meta | 12 / 1.3 / 400 / `--text-3` |
| metric (mono) | top-bar + data values | 12 / 1.2 / 500 / tabular |

Weights: 400 / 500 / 600 / 700. Headings white (`--text`); labels muted (`--text-2`); never use color tint to create hierarchy (use weight + size).

---

## 4. Spacing, radius, elevation, grid

**Spacing** — 4px base: `2 · 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48`. Card padding 20–24. Row gaps 12–16. Page gutter 24–32.

**Radius**
```
--r-card:    16px;   /* cards, panels, modal */
--r-control: 10px;   /* buttons, inputs, dropdowns */
--r-chip:     6px;   /* severity pills, tags */
--r-pill:    999px;  /* status dots-pills, segmented toggle */
```
Nothing softer than 16. Consistent radius family = product feel; no uniform-bubbly-everything.

**Elevation** — surface ladder + hairline does the work. Shadows ONLY on true overlays (modal, popover, dropdown): `0 16px 48px rgba(0,0,0,0.55)`. Cards = `--surface-2` + `1px var(--line)`, no shadow. Hovered/active card = `--surface-3` + `1px var(--line-strong)`.

**App grid:** left nav rail `64px` fixed · main content fluid · optional right rail `~360px` (Ask Argus / digests). Top status bar `56px` fixed. Content max-width is generous/edge-to-edge for ops views (video wall, board); centered/max-width for focused flows (onboarding).

---

## 5. App shell

**Top status bar (56px, `--surface-1`, hairline bottom)**
- Left: **ARGUS** wordmark — 700, +0.06em tracking, white.
- Right: **system vitals cluster** — each is `LABEL` (mono, `--text-3`, uppercase) + value: `● 3 CAM ACTIVE` (info-weak pill, info dot — nominal status, **not** red; red is reserved per §2) · `● STATUS NOMINAL` (green) · `SENSORS 9/9` · `PIPELINE 4.2ms` · `DETECTIONS 247` (values in mono `--text`, no accent — accent is interactive-only per §2). Status words colored by semantic meaning. This bar is a brand signature — present on every screen.

**Left nav rail (64px, icon-only, `--surface-1`)**
- Vertical line-icons, ~20px, 1.75px stroke: Dashboard/grid · Alerts (triangle) · Tracks/routes · Assets (drone) · Targeting/scope · Ask Argus (chat +) · Settings (pinned bottom).
- **Active** = `--accent` icon (optionally a 2px left blue indicator + `--accent-weak` tile). Inactive = `--text-3`, hover `--text-2`. Tooltip on hover.

**Right rail (contextual, ~360px)** — "Ask Argus" copilot and/or digest panels. Persistent on ops screens (Alerts, Camera wall), collapsible.

**Page header** — `h1` title top-left, optional filters/segmented control on the right of the header row.

---

## 6. Component library

**Buttons**
- Primary: `--accent` fill, white text, `--r-control`, 600, 14px; hover `--accent-strong`; focus `--accent-ring`. ("Take Action", "Send", "New Chat").
- Secondary/ghost: transparent, `1px var(--line)`, `--text-2`; hover `--surface-3`. ("Dismiss").
- Destructive: `--critical` fill (or ghost with red text). E-STOP is the loudest variant.
- Icon button: 32–36px, `--text-2`, hover surface.

**Segmented control / tabs** — pill group on `--surface-2`; active segment `--surface-3` + white text (or `--accent-weak` + accent text). ("All / CCTV / Drones Cam").

**Dropdown / select** — `--surface-2`, hairline, `--r-control`, chevron, mono value if numeric. ("VIEW 2 ▾").

**Status chip / severity pill** — `--r-chip`, leading dot, label: `● Critical` (critical), `● Warning` (warning), `● Info` (info), `● Resolved` (success). Source tag `CAM-01` = mono on `--accent-weak`. Risk dot legend: High=red, Medium=amber, Low=info.

**KPI / stat card** — `--surface-2`, `--r-card`, padding 20: `label` (uppercase muted) + `stat` number, with a small **corner-bracket framed icon** top-right (the L-tick frame from the Alerts screen — a subtle nod to the operational heritage). Icon tinted by metric (red for High Risk, amber Medium, info Low).

**Asset-type card (onboarding)** — large `--surface-2` card, `--r-card`, big line-icon top-right, `label` (category, e.g. "AIR PLATFORM") + `card-title` name ("DRONES"). Hover/selected: `1px var(--accent)` border + `--accent-weak` wash.

**Alert card** — header row: severity pill + source tag + timestamp (right, caption). Title (`card-title`), location (`--text-2`). Footer: primary `Take Action` + ghost `Dismiss`. Critical = `--critical-weak` wash + subtle red edge. Lives in kanban columns: **New · Working On · Resolved** (column header + count).

**Action timeline** — vertical line with node markers: done = green check, active = spinner ring; each step = time (mono caption) + text. Used in "Performing Action" / "Working On".

**Chat ("Ask Argus")** — thread on `--surface-inset`. Operator message = `--accent-weak` bubble, right-aligned, white text. Argus reply = `--surface-2` bubble, `--text` with `--text-3` de-emphasis and `body-strong` highlights. **L-level alert message** (e.g. "L3 ALERT") = `--critical-weak` bubble, red edge, with the alert glyph. Composer: `--surface-2` input "Ask Argus anything…", mic icon, primary `Send`. Left chat list with "New Chat" + grouped history.

**Digest panel** — titled card ("Daily Digests", "Fleet Status") with a stat or list; sub-items use semantic chips ("Resolved in 5 min" info, "Suspect Fled" warning).

**Modal / detail sheet** — `--surface-3`, `--r-card`, overlay scrim `rgba(0,0,0,0.6)` + soft shadow. Header: title + close X. Body: media row (feed + map side by side) then a **meta-field row** — each field = `label` (muted) + value (`body-strong`), separated by vertical hairlines (`Channel No · Alert Location · Alert Intensity · Alert Occurred Time`) — then a description block.

**Camera tile** — `--surface-inset` frame, video fill. Overlays: `● REC` top-left (critical, blinking), timestamp top-right (mono), `••• ` menu, bottom label `CAM 01 - SECTOR 1` + status dot (green live / red issue). Detection boxes drawn on feed: 2px outline + small label chip (`DRONE`) — use `--info`/`--accent` for tracked, `--critical` for threat. Grid views with REC/live state per tile.

**Map panel** — dark/satellite map, `MAP` caption, zoom controls top-right. Markers: your assets = `--accent` pin, alerts = `--critical` pulse, others = `--info`. Labels in caption type. Used both as a full panel (camera wall) and inside the alert modal.

---

## 7. Iconography & motion

- **Icons:** consistent line set, ~1.75px stroke, rounded joins, 20–24px. Asset icons (drone/UTV/boat/cctv) are the friendly filled line-art from the onboarding screen. Active = `--accent`.
- **Motion:** calm and quick. 120–220ms, `ease-out` enter / `ease-in` exit; color/opacity/transform only. REC blink ~1s. Spinner for in-progress timeline nodes. Respect `prefers-reduced-motion`. No decorative ambient motion.

---

## 8. How modules inherit — the Drive / teleop cockpit

The teleop cockpit is the **Ground Platform** module, rebuilt in this system (this **supersedes** the earlier gold/cyan tactical mockups, which were the wrong language):

- Same top status bar + left nav (Assets/Ground active in `--accent`); optional right rail = Ask Argus + live telemetry digest.
- **Single large live feed** as the hero (the camera-wall tile language scaled up), with the **map panel** alongside and the **alerts/Ask-Argus** rails consistent with the app.
- HUD overlays stay **clean and product-grade** (not gun-camera reticle): detection boxes in `--info`/`--accent` (threat `--critical`), a slim telemetry readout in the top-bar style, latency surfaced in the vitals cluster.
- Driving controls (gear F/N/R, speed, drive mode, lights) = the app's button/chip/segmented components. **E-STOP** = the destructive/critical button, always visible, the one loud red element. Link-loss = a `--critical` takeover consistent with the alert language.
- Carry-overs worth keeping from exploration: confirmed-vs-commanded state (render as `--success`/`--accent` confirm + muted pending, **not** gold), and the latency-always-visible discipline (in the vitals bar).

The build plan's "design tokens" task (`web/src/design/tokens.css`) is now **this file's §2–§4**, not invented values.

---

## 9. To confirm against Figma
1. **Brand blue** exact hex (I used `#2E8FFF`).
2. **Primary type family** (Geist? General Sans? Inter? something custom?) + the mono.
3. **Card/control radius** exact values (I used 16 / 10).
4. Whether the corner-bracket framed icons (Alerts KPIs) are a system motif to reuse broadly or one-off.
5. Any tokens you can export from Figma (color/type styles) — I'll replace the `‹confirm›` values verbatim.
