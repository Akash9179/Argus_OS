#!/usr/bin/env python3
"""The Engineering Knowledge Graph compiler.

Reads docs/architecture/graph/*.yaml, validates every cross-reference against the
repository, answers queries, and generates STATUS.md. CI runs validate and
checks STATUS.md for drift, so the graph cannot silently rot (law 18) and no
component can claim hardware evidence it does not have (law 17).

Usage:
    argus_graph.py validate
    argus_graph.py status [--write]
    argus_graph.py incomplete | blockers | untested | hardware-unvalidated
    argus_graph.py component <id>
    argus_graph.py impact <id>
    argus_graph.py decisions [--open]
    argus_graph.py risks
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
GRAPH_DIR = REPO / "docs" / "architecture" / "graph"
STATUS_PATH = REPO / "STATUS.md"

STATUSES = [
    "planned", "scaffolded", "simulated", "software_verified",
    "hardware_integrated", "field_validated", "deprecated",
]
DISPOSITIONS = ["keep", "refactor", "replace", "archive", "new"]
TYPES = [
    "Component", "Service", "Interface", "Driver", "Adapter", "Application",
    "Fixture", "Firmware", "Hardware", "Domain", "Tooling",
]
REL_TYPES = [
    "USES", "CONSUMES", "IMPLEMENTS", "EXPOSES", "PRODUCES", "TESTED_BY",
    "RUNS_ON", "SUPERSEDES", "PART_OF", "GOVERNED_BY", "BLOCKED_BY",
    "SYNC_WITH",
]
# Maturities that require hardware evidence to claim (law 17).
NEEDS_HARDWARE_EVIDENCE = {"hardware_integrated", "field_validated"}
# Every top-level code directory must be owned by at least one component, so
# new code cannot appear without the graph knowing about it.
COVERED_DIRS = [
    "link", "track", "c2", "gateway", "voice", "drive", "sim", "bodies",
    "scripts", "docs", "tests",
]

PLANE_TITLES = [
    ("platform", "Platform (ground station and services)"),
    ("edge", "Edge (the machine)"),
    ("core", "Core (the cognitive architecture, target)"),
    ("domain", "Domain execution layers"),
    ("hardware", "Hardware bodies"),
    ("learning", "Learning plane"),
    ("operations", "Operations"),
    ("engineering", "Engineering"),
]


def _load(name: str) -> dict:
    path = GRAPH_DIR / name
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: top level must be a mapping")
    return data


def load_graph() -> dict:
    return {
        "components": _load("components.yaml").get("components", []),
        "relationships": _load("relationships.yaml").get("relationships", []),
        "decisions": _load("decisions.yaml").get("decisions", []),
        "risks": _load("risks.yaml").get("risks", []),
        "research": _load("research.yaml").get("research", []),
        "laws": _load("laws.yaml").get("laws", []),
    }


def validate(graph: dict) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()

    for c in graph["components"]:
        cid = c.get("id")
        if not cid:
            errors.append(f"component without id: {c!r}")
            continue
        if cid in ids:
            errors.append(f"duplicate component id: {cid}")
        ids.add(cid)
        for field in ("name", "type", "role", "status", "disposition", "plane"):
            if not c.get(field):
                errors.append(f"{cid}: missing required field {field!r}")
        if c.get("status") not in STATUSES:
            errors.append(f"{cid}: unknown status {c.get('status')!r}")
        if c.get("disposition") not in DISPOSITIONS:
            errors.append(f"{cid}: unknown disposition {c.get('disposition')!r}")
        if c.get("type") not in TYPES:
            errors.append(f"{cid}: unknown type {c.get('type')!r}")
        if c.get("plane") not in [p for p, _ in PLANE_TITLES]:
            errors.append(f"{cid}: unknown plane {c.get('plane')!r}")

        path = c.get("path")
        if path is not None and not (REPO / path).exists():
            errors.append(f"{cid}: path does not exist: {path}")
        if path is None and c.get("status") not in ("planned", "deprecated"):
            errors.append(f"{cid}: status {c.get('status')} but no path; only planned/deprecated components may have none")
        if c.get("status") == "planned" and path is not None:
            errors.append(f"{cid}: planned components must not claim a path (it would imply code exists)")

        if c.get("status") in NEEDS_HARDWARE_EVIDENCE:
            runs = (c.get("evidence") or {}).get("hardware_runs") or []
            if not runs:
                errors.append(f"{cid}: status {c['status']} requires evidence.hardware_runs (law 17)")

        for t in c.get("tests", []) or []:
            if not (REPO / t).exists():
                errors.append(f"{cid}: test path does not exist: {t}")

    for c in graph["components"]:
        sup = c.get("superseded_by")
        if sup and sup not in ids:
            errors.append(f"{c['id']}: superseded_by unknown component {sup!r}")
        if c.get("disposition") == "replace" and not sup:
            errors.append(f"{c['id']}: disposition replace requires superseded_by naming the successor")

    for r in graph["relationships"]:
        for end in ("from", "to"):
            if r.get(end) not in ids:
                errors.append(f"relationship {r.get('from')} -{r.get('type')}-> {r.get('to')}: unknown component in {end!r}")
        if r.get("type") not in REL_TYPES:
            errors.append(f"relationship {r.get('from')} -> {r.get('to')}: unknown type {r.get('type')!r}")

    seen_dec: set[str] = set()
    for d in graph["decisions"]:
        did = d.get("id", "?")
        if did in seen_dec:
            errors.append(f"duplicate decision id: {did}")
        seen_dec.add(did)
        if d.get("status") not in ("decided", "decided_convention", "open"):
            errors.append(f"decision {did}: unknown status {d.get('status')!r}")
        if d.get("status") == "decided" and not d.get("date"):
            errors.append(f"decision {did}: decided but no date")
        for cid in d.get("affects", []) or []:
            if cid not in ids:
                errors.append(f"decision {did}: affects unknown component {cid!r}")

    for r in graph["risks"]:
        for cid in r.get("affects", []) or []:
            if cid not in ids:
                errors.append(f"risk {r.get('id')}: affects unknown component {cid!r}")

    for r in graph["research"]:
        for cid in r.get("influences", []) or []:
            if cid not in ids:
                errors.append(f"research {r.get('id')}: influences unknown component {cid!r}")

    for law in graph["laws"]:
        for e in law.get("enforcement", []) or []:
            if e not in ("review", "gap") and not (REPO / e).exists():
                errors.append(f"law {law.get('id')}: enforcement path does not exist: {e}")

    owned = {p for c in graph["components"] if c.get("path") for p in [c["path"].split("/")[0]]}
    for d in COVERED_DIRS:
        if (REPO / d).is_dir() and d not in owned:
            errors.append(f"top-level directory {d}/ is not owned by any component; add it to components.yaml")

    return errors


def render_status(graph: dict) -> str:
    comps = graph["components"]
    lines: list[str] = []
    lines.append("# ARGUS - build status")
    lines.append("")
    lines.append("Generated from the Engineering Knowledge Graph. Do not edit by hand;")
    lines.append("edit `docs/architecture/graph/*.yaml`, then run")
    lines.append("`.venv/bin/python scripts/argus_graph.py status --write`.")
    lines.append("CI fails if this file drifts from the graph.")
    lines.append("")
    lines.append("Maturity (law 17): `planned` < `scaffolded` < `simulated` <")
    lines.append("`software_verified` < `hardware_integrated` < `field_validated`.")
    lines.append("`simulated` means proven only against simulated hardware or fixtures.")
    n_field = sum(1 for c in comps if c["status"] == "field_validated")
    n_hw = sum(1 for c in comps if (c.get("evidence") or {}).get("hardware_runs"))
    field_clause = (
        "Nothing here has been field validated"
        if n_field == 0
        else f"{n_field} component{'s are' if n_field > 1 else ' is'} field validated"
    )
    hw_clause = (
        "no component has ever run on real hardware"
        if n_hw == 0
        else f"{n_hw} component{'s have' if n_hw > 1 else ' has'} hardware evidence (listed below)"
    )
    lines.append(f"{field_clause}, and {hw_clause}.")
    lines.append("Disposition is the 18 Aug 2026 reconciliation")
    lines.append("verdict: keep / refactor / replace / archive / new.")
    lines.append("")

    for plane, title in PLANE_TITLES:
        rows = [c for c in comps if c.get("plane") == plane]
        if not rows:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Component | Maturity | Disposition | Notes |")
        lines.append("|---|---|---|---|")
        for c in rows:
            gaps = len(c.get("known_gaps") or [])
            blocked = len(c.get("blockers") or [])
            note_bits = []
            if blocked:
                note_bits.append(f"BLOCKED ({blocked})")
            if gaps:
                note_bits.append(f"{gaps} known gap{'s' if gaps > 1 else ''}")
            if c.get("superseded_by"):
                note_bits.append(f"succeeded by `{c['superseded_by']}`")
            lines.append(
                f"| {c['name']} (`{c['id']}`) | {c['status']} | {c['disposition']} | {'; '.join(note_bits) or '-'} |"
            )
        lines.append("")

    blocked = [c for c in comps if c.get("blockers")]
    if blocked:
        lines.append("## Blockers")
        lines.append("")
        for c in blocked:
            for b in c["blockers"]:
                lines.append(f"- `{c['id']}`: {b}")
        lines.append("")

    hw = [c for c in comps if (c.get("evidence") or {}).get("hardware_runs")]
    lines.append("## Hardware evidence (everything else is Mac and CI containers)")
    lines.append("")
    if hw:
        for c in hw:
            for run in c["evidence"]["hardware_runs"]:
                lines.append(f"- `{c['id']}`: {run}")
    else:
        lines.append("- none")
    lines.append("")

    open_dec = [d for d in graph["decisions"] if d.get("status") == "open"]
    lines.append("## Open decisions (founder-gated; details in docs/architecture/graph/decisions.yaml)")
    lines.append("")
    for d in open_dec:
        lines.append(f"- {d['id']}: {d['title']}")
    lines.append("")
    lines.append("Roadmap and critical path: NEXT-STEPS.md. Target architecture: ARCHITECTURE.md.")
    lines.append("")
    return "\n".join(lines)


def cmd_component(graph: dict, cid: str) -> int:
    comp = next((c for c in graph["components"] if c["id"] == cid), None)
    if not comp:
        print(f"unknown component: {cid}", file=sys.stderr)
        return 1
    print(yaml.safe_dump(comp, sort_keys=False, allow_unicode=True))
    rels = [r for r in graph["relationships"] if cid in (r.get("from"), r.get("to"))]
    if rels:
        print("relationships:")
        for r in rels:
            print(f"  {r['from']} -{r['type']}-> {r['to']}")
    for key, items, field in (
        ("decisions", graph["decisions"], "affects"),
        ("risks", graph["risks"], "affects"),
        ("research", graph["research"], "influences"),
    ):
        hits = [i for i in items if cid in (i.get(field) or [])]
        if hits:
            print(f"{key}:")
            for h in hits:
                print(f"  {h['id']}: {h['title']}")
    return 0


def cmd_impact(graph: dict, cid: str) -> int:
    if not any(c["id"] == cid for c in graph["components"]):
        print(f"unknown component: {cid}", file=sys.stderr)
        return 1
    # Who depends on cid: incoming USES/CONSUMES/IMPLEMENTS edges, transitively.
    dependents: set[str] = set()
    frontier = {cid}
    while frontier:
        nxt: set[str] = set()
        for r in graph["relationships"]:
            if r["to"] in frontier and r["type"] in ("USES", "CONSUMES", "IMPLEMENTS", "PART_OF"):
                if r["from"] not in dependents:
                    nxt.add(r["from"])
        dependents |= nxt
        frontier = nxt
    if dependents:
        print(f"changing {cid} may affect:")
        for d in sorted(dependents):
            print(f"  {d}")
    else:
        print(f"nothing in the graph depends on {cid}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    graph = load_graph()
    errors = validate(graph)
    cmd = argv[0]

    if cmd == "validate":
        for e in errors:
            print(f"GRAPH ERROR: {e}")
        print("graph valid" if not errors else f"{len(errors)} error(s)")
        return 1 if errors else 0

    if errors:
        for e in errors:
            print(f"GRAPH ERROR: {e}", file=sys.stderr)
        return 1

    if cmd == "status":
        content = render_status(graph)
        if "--write" in argv:
            STATUS_PATH.write_text(content, encoding="utf-8")
            print(f"wrote {STATUS_PATH}")
        else:
            print(content)
        return 0

    if cmd == "incomplete":
        for c in graph["components"]:
            if c["status"] in ("planned", "scaffolded", "simulated") or c.get("known_gaps"):
                print(f"{c['id']:34s} {c['status']:20s} gaps={len(c.get('known_gaps') or [])}")
        return 0

    if cmd == "blockers":
        for c in graph["components"]:
            for b in c.get("blockers") or []:
                print(f"{c['id']}: {b}")
        return 0

    if cmd == "untested":
        for c in graph["components"]:
            if c["status"] not in ("planned", "deprecated") and not c.get("tests"):
                print(f"{c['id']:34s} {c['status']}")
        return 0

    if cmd == "hardware-unvalidated":
        for c in graph["components"]:
            if c["status"] in ("simulated", "software_verified"):
                print(f"{c['id']:34s} {c['status']}")
        return 0

    if cmd == "decisions":
        want_open = "--open" in argv
        for d in graph["decisions"]:
            if want_open and d["status"] != "open":
                continue
            print(f"{d['id']:8s} {d['status']:20s} {d['title']}")
        return 0

    if cmd == "risks":
        for r in graph["risks"]:
            print(f"{r['id']:6s} {r.get('severity', '?'):8s} {r['title']}")
        return 0

    if cmd == "component" and len(argv) > 1:
        return cmd_component(graph, argv[1])

    if cmd == "impact" and len(argv) > 1:
        return cmd_impact(graph, argv[1])

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
