"""Generate a deterministic synthetic incident: cooling failure, power spike,
dry air, UPS drain and a badge-guessing intrusion. Run from the repo root:

    python samples/generate_sample.py
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

rng = random.Random(42)
OUT = Path(__file__).parent
START = datetime(2026, 10, 11, 2, 0)
STEPS = 25  # every 5 minutes -> 2 hours

rows = []
for i in range(STEPS):
    t = START + timedelta(minutes=5 * i)
    ts = t.isoformat()
    for rack in ("R01", "R02", "R03"):
        temp = 22 + rng.uniform(-0.6, 0.6)
        if rack == "R02" and i >= 8:  # cooling failure begins 02:40
            temp = min(38.0, 23 + (i - 7) * 2.8) + rng.uniform(-0.3, 0.3)
        rows.append((ts, rack, "temp_c", round(temp, 1)))

        hum = 45 + rng.uniform(-3, 3)
        if rack == "R01" and 12 <= i <= 16:  # dry air
            hum = 15 + rng.uniform(-1, 1)
        rows.append((ts, rack, "humidity_pct", round(hum, 1)))

        kw = 5.5 + rng.uniform(-0.5, 0.5)
        if rack == "R03" and 15 <= i <= 19:  # power spike
            kw = 9.4 + rng.uniform(-0.2, 0.2)
        rows.append((ts, rack, "power_kw", round(kw, 2)))

    batt = 100 if i < 14 else max(15, 100 - (i - 13) * 8)  # mains loss at 03:10
    rows.append((ts, "UPS-A", "ups_battery_pct", batt))

with open(OUT / "telemetry.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["timestamp", "rack", "metric", "value"])
    w.writerows(rows)

badge = [
    ("2026-10-10T08:05:00", "alice", "DC-Main", "granted"),
    ("2026-10-10T17:30:00", "alice", "DC-Main", "granted"),
    ("2026-10-11T02:20:00", "temp_badge7", "DC-Cage3", "denied"),
    ("2026-10-11T02:22:00", "temp_badge7", "DC-Cage3", "denied"),
    ("2026-10-11T02:24:00", "temp_badge7", "DC-Cage3", "denied"),
    ("2026-10-11T02:26:00", "temp_badge7", "DC-Cage3", "denied"),
    ("2026-10-11T02:28:00", "temp_badge7", "DC-Cage3", "granted"),
    ("2026-10-11T02:41:00", "contractor_x", "DC-Main", "granted"),
    ("2026-10-11T09:00:00", "bob", "DC-Main", "granted"),
]
with open(OUT / "badge.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["timestamp", "user", "door", "result"])
    w.writerows(badge)

print(f"Wrote {len(rows)} telemetry rows and {len(badge)} badge events to {OUT}")
