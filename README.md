# DCWatch 🏢🌡️

A lightweight, dependency-free **datacenter anomaly detector**. It analyzes rack telemetry (temperature, humidity, power, UPS battery) together with **physical badge-access logs** to catch cooling failures, power problems, and suspicious door access: the overlap between facility operations and security.

Built as a portfolio project for infrastructure / SOC / datacenter operations roles.

## What it detects

| Rule | Severity | Description |
|------|----------|-------------|
| `thermal_hotspot` | high/critical | Inlet temperature above 27 °C for N consecutive readings (critical at ≥ 32 °C) |
| `rapid_temp_rise` | high | ≥ 5 °C rise within 10 min, a likely CRAC/CRAH cooling failure |
| `humidity_out_of_range` | medium | Sustained RH below 20% (ESD risk) or above 80% (condensation risk) |
| `power_overload` | medium/high | Rack draw above its kW limit for N consecutive readings |
| `ups_battery_low` | high/critical | UPS battery at ≤ 50% (high) or ≤ 20% (critical), i.e. a mains outage |
| `after_hours_access` | medium | Successful badge entry outside business hours |
| `badge_guessing` | high/critical | Repeated denied swipes for one badge; critical if followed by a grant |

Defaults loosely follow simplified ASHRAE TC 9.9 class A1 guidance. All thresholds live in the `Thresholds` dataclass in `dcwatch/rules.py`.

## Quick start

```bash
git clone https://github.com/<your-username>/dcwatch.git
cd dcwatch

python samples/generate_sample.py        # creates samples/telemetry.csv + badge.csv
python -m dcwatch samples/telemetry.csv --badge samples/badge.csv
python -m dcwatch samples/telemetry.csv --badge samples/badge.csv --format json
```

Requires Python 3.9+. No third-party packages.

### Example output

```
DCWatch report: 250 telemetry readings, 9 badge events, 8 alert(s)

[CRIT] 02:20 badge_guessing         temp_badge7            4 denied attempts in 10 min, then GRANTED at DC-Cage3
[CRIT] 02:45 thermal_hotspot        R02                    Inlet temp above 27 C for 16 readings (peak 38.3 C)
[CRIT] 04:00 ups_battery_low        UPS-A                  UPS battery fell to 15%
[HIGH] 02:45 rapid_temp_rise        R02                    +7.2 C in 10 min: suspect cooling failure
[HIGH] 03:15 power_overload         R03                    Draw above 8 kW limit for 5 readings (peak 9.6 kW)
[MED ] 02:28 after_hours_access     temp_badge7@DC-Cage3   Badge granted outside 06:00-20:00
[MED ] 02:41 after_hours_access     contractor_x@DC-Main   Badge granted outside 06:00-20:00
[MED ] 03:00 humidity_out_of_range  R01                    Relative humidity dry (ESD risk), 5 readings, min 14% / max 16%
```

The exit code is `1` when a high/critical alert exists, so it works in cron jobs and CI.

## Input formats

**Telemetry CSV**: `timestamp,rack,metric,value`

```
2026-10-11T02:00:00,R01,temp_c,22.3
2026-10-11T02:00:00,UPS-A,ups_battery_pct,100
```

Metrics: `temp_c`, `humidity_pct`, `power_kw`, `ups_battery_pct`.

**Badge CSV**: `timestamp,user,door,result` where result is `granted` or `denied`.

Malformed rows are skipped instead of crashing the run.

## Project structure

```
dcwatch/
├── dcwatch/
│   ├── loaders.py   # CSV parsing into typed Reading / BadgeEvent objects
│   ├── rules.py     # detection rules + tunable thresholds
│   └── cli.py       # command-line interface (text / JSON)
├── samples/generate_sample.py   # deterministic synthetic incident
└── tests/test_rules.py          # pytest unit tests
```

## Running tests

```bash
pip install pytest
pytest -v
```

## The sample incident

The generator creates a realistic overnight scenario: a cooling failure in rack R02 starting 02:40, dry air in R01, a power spike on R03, a mains outage draining the UPS, and, while ops is distracted, a temporary badge that guesses its way into Cage 3. Correlating physical and environmental events is the point of the project.

## Ideas for extension

- Live ingestion from SNMP / Modbus / Redfish / IPMI sensors
- Prometheus exporter and Grafana dashboard
- Correlation rule: access events during an active thermal or power incident
- PUE (Power Usage Effectiveness) tracking and trend reports
- Alert delivery via email / Slack / PagerDuty webhooks

## Disclaimer

For educational and portfolio use. Sample data is entirely synthetic. Thresholds are simplified; tune them to your facility's actual specifications.

## License

MIT
