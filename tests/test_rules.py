from datetime import datetime, timedelta

from dcwatch.loaders import BadgeEvent, Reading, load_badge, load_telemetry
from dcwatch.rules import (
    Thresholds,
    detect_after_hours_access,
    detect_badge_guessing,
    detect_humidity,
    detect_power_overload,
    detect_rapid_rise,
    detect_thermal,
    detect_ups_drain,
    run_all,
)

T0 = datetime(2026, 10, 11, 2, 0)
T = Thresholds()


def series(metric, values, rack="R01", step=5):
    return [Reading(T0 + timedelta(minutes=step * i), rack, metric, v) for i, v in enumerate(values)]


def test_thermal_sustained_triggers():
    alerts = detect_thermal(series("temp_c", [22, 28, 29, 30, 22]), T)
    assert len(alerts) == 1 and alerts[0].severity == "high"


def test_thermal_critical_on_peak():
    alerts = detect_thermal(series("temp_c", [28, 30, 33]), T)
    assert alerts[0].severity == "critical"


def test_thermal_ignores_short_blip():
    assert detect_thermal(series("temp_c", [22, 30, 22, 30, 22]), T) == []


def test_rapid_rise_detected():
    alerts = detect_rapid_rise(series("temp_c", [22, 22.5, 28.5]), T)
    assert len(alerts) == 1 and alerts[0].rule == "rapid_temp_rise"


def test_slow_rise_not_flagged():
    assert detect_rapid_rise(series("temp_c", [22, 23, 24, 25, 26, 27], step=10), T) == []


def test_humidity_dry():
    alerts = detect_humidity(series("humidity_pct", [45, 15, 14, 16, 45]), T)
    assert len(alerts) == 1 and "dry" in alerts[0].description


def test_power_overload_severity():
    alerts = detect_power_overload(series("power_kw", [5, 9.5, 9.6, 9.4]), T)
    assert alerts and alerts[0].severity == "high"


def test_ups_levels():
    assert detect_ups_drain(series("ups_battery_pct", [100, 60], "UPS"), T) == []
    assert detect_ups_drain(series("ups_battery_pct", [100, 45], "UPS"), T)[0].severity == "high"
    assert detect_ups_drain(series("ups_battery_pct", [100, 15], "UPS"), T)[0].severity == "critical"


def badge(minute, user="u", door="D", granted=True, hour=2):
    return BadgeEvent(datetime(2026, 10, 11, hour, minute), user, door, granted)


def test_after_hours_flagged_only_when_granted():
    evs = [badge(0, granted=True), badge(1, granted=False), badge(0, hour=9)]
    assert len(detect_after_hours_access(evs, T)) == 1


def test_badge_guessing_critical_when_granted_after():
    evs = [badge(0, granted=False), badge(1, granted=False), badge(2, granted=False), badge(4)]
    alerts = detect_badge_guessing(evs, T)
    assert len(alerts) == 1 and alerts[0].severity == "critical"


def test_badge_guessing_high_without_grant():
    evs = [badge(0, granted=False), badge(1, granted=False), badge(2, granted=False)]
    assert detect_badge_guessing(evs, T)[0].severity == "high"


def test_two_denials_not_enough():
    assert detect_badge_guessing([badge(0, granted=False), badge(1, granted=False)], T) == []


def test_run_all_sorted_by_severity():
    readings = series("ups_battery_pct", [100, 10], "UPS") + series("humidity_pct", [15, 15, 15])
    alerts = run_all(readings)
    assert alerts[0].severity == "critical"


def test_loaders_skip_bad_rows(tmp_path):
    tel = tmp_path / "t.csv"
    tel.write_text("timestamp,rack,metric,value\n2026-10-11T02:00:00,R1,temp_c,22\nbad,row,here,x\n2026-10-11T02:05:00,R1,junk,1\n")
    bad = tmp_path / "b.csv"
    bad.write_text("timestamp,user,door,result\n2026-10-11T02:00:00,a,D,GRANTED\nnope,a,D,maybe\n")
    assert len(load_telemetry(str(tel))) == 1
    assert load_badge(str(bad))[0].granted is True
