"""DCWatch command-line interface."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .loaders import load_badge, load_telemetry
from .rules import Alert, run_all

ICON = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED ]", "low": "[LOW ]"}


def format_text(alerts: list[Alert], n_readings: int, n_badge: int) -> str:
    lines = [
        f"DCWatch report: {n_readings} telemetry readings, {n_badge} badge events, {len(alerts)} alert(s)",
        "",
    ]
    for a in alerts:
        lines.append(f"{ICON[a.severity]} {a.time:%H:%M} {a.rule:<22} {a.subject:<22} {a.description}")
    if not alerts:
        lines.append("All clear: no anomalies detected.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dcwatch", description="Datacenter telemetry & access anomaly detector.")
    p.add_argument("telemetry", help="Telemetry CSV (timestamp,rack,metric,value)")
    p.add_argument("--badge", help="Badge access CSV (timestamp,user,door,result)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    args = p.parse_args(argv)

    readings = load_telemetry(args.telemetry)
    badge = load_badge(args.badge) if args.badge else []
    alerts = run_all(readings, badge)

    if args.format == "json":
        print(json.dumps([{**asdict(a), "time": a.time.isoformat()} for a in alerts], indent=2))
    else:
        print(format_text(alerts, len(readings), len(badge)))
    return 1 if any(a.severity in ("critical", "high") for a in alerts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
