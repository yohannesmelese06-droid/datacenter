"""Detection rules for datacenter telemetry and physical access.

Defaults loosely follow ASHRAE TC 9.9 class A1 guidance (simplified):
recommended inlet temperature 18-27 C, allowable up to 32 C.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Sequence

from .loaders import BadgeEvent, Reading

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Thresholds:
    temp_warn: float = 27.0
    temp_crit: float = 32.0
    sustained: int = 3  # consecutive readings required
    rise_c: float = 5.0
    rise_window: timedelta = timedelta(minutes=10)
    hum_min: float = 20.0
    hum_max: float = 80.0
    rack_kw_limit: float = 8.0
    ups_warn: float = 50.0
    ups_crit: float = 20.0
    biz_start_hour: int = 6
    biz_end_hour: int = 20
    denied_threshold: int = 3
    denied_window: timedelta = timedelta(minutes=10)


@dataclass
class Alert:
    rule: str
    severity: str
    subject: str
    description: str
    time: datetime
    details: Dict[str, object] = field(default_factory=dict)


def _series(readings: Sequence[Reading], metric: str) -> Dict[str, List[Reading]]:
    grouped: Dict[str, List[Reading]] = defaultdict(list)
    for r in readings:
        if r.metric == metric:
            grouped[r.rack].append(r)
    for rs in grouped.values():
        rs.sort(key=lambda r: r.time)
    return grouped


def _runs(series: Sequence[Reading], pred: Callable[[float], bool], min_len: int) -> List[List[Reading]]:
    runs, cur = [], []
    for r in series:
        if pred(r.value):
            cur.append(r)
        else:
            if len(cur) >= min_len:
                runs.append(cur)
            cur = []
    if len(cur) >= min_len:
        runs.append(cur)
    return runs


def detect_thermal(readings: Sequence[Reading], t: Thresholds) -> List[Alert]:
    alerts = []
    for rack, rs in _series(readings, "temp_c").items():
        runs = _runs(rs, lambda v: v > t.temp_warn, t.sustained)
        if not runs:
            continue
        worst = max(runs, key=lambda run: max(r.value for r in run))
        peak = max(r.value for r in worst)
        alerts.append(
            Alert(
                "thermal_hotspot",
                "critical" if peak >= t.temp_crit else "high",
                rack,
                f"Inlet temp above {t.temp_warn:g} C for {len(worst)} readings (peak {peak:.1f} C)",
                worst[0].time,
                {"peak_c": peak, "readings": len(worst)},
            )
        )
    return alerts


def detect_rapid_rise(readings: Sequence[Reading], t: Thresholds) -> List[Alert]:
    """Fast temperature climb: a likely cooling (CRAC/CRAH) failure."""
    alerts = []
    for rack, rs in _series(readings, "temp_c").items():
        found = False
        for i, cur in enumerate(rs):
            for prev in rs[:i]:
                if timedelta(0) < cur.time - prev.time <= t.rise_window and cur.value - prev.value >= t.rise_c:
                    alerts.append(
                        Alert(
                            "rapid_temp_rise",
                            "high",
                            rack,
                            f"+{cur.value - prev.value:.1f} C in {int((cur.time - prev.time).total_seconds() // 60)} min: suspect cooling failure",
                            cur.time,
                            {"from_c": prev.value, "to_c": cur.value},
                        )
                    )
                    found = True
                    break
            if found:
                break
    return alerts


def detect_humidity(readings: Sequence[Reading], t: Thresholds) -> List[Alert]:
    alerts = []
    for rack, rs in _series(readings, "humidity_pct").items():
        runs = _runs(rs, lambda v: v < t.hum_min or v > t.hum_max, t.sustained)
        if runs:
            run = runs[0]
            kind = "dry (ESD risk)" if run[0].value < t.hum_min else "humid (condensation risk)"
            alerts.append(
                Alert(
                    "humidity_out_of_range",
                    "medium",
                    rack,
                    f"Relative humidity {kind}, {len(run)} readings, min {min(r.value for r in run):.0f}% / max {max(r.value for r in run):.0f}%",
                    run[0].time,
                    {"readings": len(run)},
                )
            )
    return alerts


def detect_power_overload(readings: Sequence[Reading], t: Thresholds) -> List[Alert]:
    alerts = []
    for rack, rs in _series(readings, "power_kw").items():
        runs = _runs(rs, lambda v: v > t.rack_kw_limit, t.sustained)
        if runs:
            run = max(runs, key=lambda r_: max(x.value for x in r_))
            peak = max(r.value for r in run)
            alerts.append(
                Alert(
                    "power_overload",
                    "high" if peak >= t.rack_kw_limit * 1.1 else "medium",
                    rack,
                    f"Draw above {t.rack_kw_limit:g} kW limit for {len(run)} readings (peak {peak:.1f} kW)",
                    run[0].time,
                    {"peak_kw": peak},
                )
            )
    return alerts


def detect_ups_drain(readings: Sequence[Reading], t: Thresholds) -> List[Alert]:
    alerts = []
    for ups, rs in _series(readings, "ups_battery_pct").items():
        low = min(rs, key=lambda r: r.value)
        if low.value <= t.ups_crit:
            sev = "critical"
        elif low.value <= t.ups_warn:
            sev = "high"
        else:
            continue
        alerts.append(
            Alert("ups_battery_low", sev, ups, f"UPS battery fell to {low.value:.0f}%", low.time, {"min_pct": low.value})
        )
    return alerts


def detect_after_hours_access(events: Sequence[BadgeEvent], t: Thresholds) -> List[Alert]:
    return [
        Alert(
            "after_hours_access",
            "medium",
            f"{e.user}@{e.door}",
            f"Badge granted outside {t.biz_start_hour:02d}:00-{t.biz_end_hour:02d}:00",
            e.time,
            {"user": e.user, "door": e.door},
        )
        for e in events
        if e.granted and not (t.biz_start_hour <= e.time.hour < t.biz_end_hour)
    ]


def detect_badge_guessing(events: Sequence[BadgeEvent], t: Thresholds) -> List[Alert]:
    """Repeated denials for one badge; critical if followed by a grant."""
    by_user: Dict[str, List[BadgeEvent]] = defaultdict(list)
    for e in events:
        by_user[e.user].append(e)
    alerts = []
    for user, evs in by_user.items():
        evs.sort(key=lambda e: e.time)
        denied = [e for e in evs if not e.granted]
        for i in range(len(denied)):
            window = [d for d in denied[i:] if d.time - denied[i].time <= t.denied_window]
            if len(window) >= t.denied_threshold:
                last = window[-1]
                grant = next(
                    (e for e in evs if e.granted and last.time <= e.time <= last.time + t.denied_window),
                    None,
                )
                alerts.append(
                    Alert(
                        "badge_guessing",
                        "critical" if grant else "high",
                        user,
                        f"{len(window)} denied attempts in {int(t.denied_window.total_seconds() // 60)} min"
                        + (f", then GRANTED at {grant.door}" if grant else ""),
                        window[0].time,
                        {"denied": len(window), "granted_after": bool(grant)},
                    )
                )
                break
    return alerts


def run_all(
    readings: Sequence[Reading], badge: Sequence[BadgeEvent] = (), t: Thresholds | None = None
) -> List[Alert]:
    t = t or Thresholds()
    alerts = (
        detect_thermal(readings, t)
        + detect_rapid_rise(readings, t)
        + detect_humidity(readings, t)
        + detect_power_overload(readings, t)
        + detect_ups_drain(readings, t)
        + detect_after_hours_access(badge, t)
        + detect_badge_guessing(badge, t)
    )
    return sorted(alerts, key=lambda a: (SEVERITY_ORDER[a.severity], a.time, a.subject))
