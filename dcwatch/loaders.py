"""CSV loaders for rack telemetry and badge-access logs.

Telemetry CSV: timestamp,rack,metric,value
    metrics: temp_c, humidity_pct, power_kw, ups_battery_pct
Badge CSV:     timestamp,user,door,result
    result: granted | denied
Timestamps are ISO 8601 (e.g. 2026-10-11T02:40:00).
Malformed rows are skipped rather than crashing the run.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from typing import List

VALID_METRICS = {"temp_c", "humidity_pct", "power_kw", "ups_battery_pct"}


@dataclass(frozen=True)
class Reading:
    time: datetime
    rack: str
    metric: str
    value: float


@dataclass(frozen=True)
class BadgeEvent:
    time: datetime
    user: str
    door: str
    granted: bool


def load_telemetry(path: str) -> List[Reading]:
    out: List[Reading] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                metric = row["metric"].strip()
                if metric not in VALID_METRICS:
                    continue
                out.append(
                    Reading(
                        datetime.fromisoformat(row["timestamp"].strip()),
                        row["rack"].strip(),
                        metric,
                        float(row["value"]),
                    )
                )
            except (KeyError, ValueError, AttributeError):
                continue
    return sorted(out, key=lambda r: r.time)


def load_badge(path: str) -> List[BadgeEvent]:
    out: List[BadgeEvent] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                result = row["result"].strip().lower()
                if result not in ("granted", "denied"):
                    continue
                out.append(
                    BadgeEvent(
                        datetime.fromisoformat(row["timestamp"].strip()),
                        row["user"].strip(),
                        row["door"].strip(),
                        result == "granted",
                    )
                )
            except (KeyError, ValueError, AttributeError):
                continue
    return sorted(out, key=lambda e: e.time)
