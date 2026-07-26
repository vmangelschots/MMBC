# MMBC — Multiple Marstek Battery Controller
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fvmangelschots%2Fmmbc-blue?logo=docker)](https://github.com/users/vmangelschots/packages/container/package/mmbc)
---
**MMBC** is a modular Python-based controller for Marstek Venus E batteries. It reads live power data from a HomeWizard P1 meter and intelligently controls one or more batteries over Modbus TCP to keep your electricity meter as close to zero as possible (*nul op de meter*).

> ⚠️ **Actively Developed**  
> MMBC is used in a real setup and currently supports **multiple batteries**. It is functional, but still evolving.

---

## 🚀 What It Does

- Reads net power from a HomeWizard P1 smart meter (via its API)
- Controls one or more Venus E batteries using Modbus TCP (RS485-to-Ethernet adapter)
- Coordinates charging and discharging intelligently to match grid power flow
- Publishes aggregated battery data over **MQTT** for easy integration with **Home Assistant**

---
## 📦 Quick Start (Docker)

```bash
docker run --env-file .env --restart unless-stopped ghcr.io/vmangelschots/mmbc:latest
```

Make sure to configure your `.env` file with:

```env
P1_HOST=http://192.168.x.x
MQTT_HOST=192.168.x.x
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=mmbc/virtual
BATTERY_1_IP=192.168.1.101
BATTERY_1_ADDRESS=1
BATTERY_2_IP=192.168.1.102
BATTERY_2_ADDRESS=1
```

---
## ⚙️ Control Logic

- If the **adjusted net power** (meter power + battery output) is within **±30W**, all batteries are set to **idle**.

- If the **absolute power is under 2500W**:
  - Only a **single battery** is used, to maximize inverter efficiency and reduce switching.
  - The selection is based on **State of Charge (SoC)**:
    - **Charging** → battery with the **lowest SoC**
    - **Discharging** → battery with the **highest SoC**
  - This selection is **cached** for 5 minutes to minimize switching, unless the chosen battery becomes ineligible (e.g., SoC out of bounds).

- If the **power exceeds 2500W**:
  - The load is **split across multiple eligible batteries**, capped at 2500W per battery.

- A battery is considered **eligible** when:
  - **Charging** → SoC < 100%
  - **Discharging** → SoC > 11%

- Battery priority is **reevaluated**:
  - Automatically every **5 minutes**
  - Or **immediately** if a selected battery becomes **ineligible**


---

## ⚡ Grid Import Limit (Capacity Tariff)

Belgian households pay a grid fee based on the **highest 15-minute average import** of the month (*capaciteitstarief*). Charging a battery from the grid can easily push that peak up.

Set the optional `GRID_MAX_IMPORT_WATTS` to keep MMBC below your target:

```env
GRID_MAX_IMPORT_WATTS=8000
```

MMBC then measures what the house is consuming **excluding the batteries** and only charges with the power that is left over:

| House consumption | Limit  | Battery charge power | Grid import |
|-------------------|--------|----------------------|-------------|
| 5000 W            | 8000 W | 3000 W               | 8000 W      |
| 1000 W            | 8000 W | 5000 W (2 batteries at max) | 6000 W |
| 8500 W            | 8000 W | 0 W (batteries idle) | 8500 W      |
| −2000 W (solar surplus) | 8000 W | 5000 W         | 3000 W      |

Notes:

- Leave it **unset for no limit** — that is the previous behaviour.
- The limit is checked every cycle (3 s) against the **instantaneous** import, which is stricter than the 15-minute average the grid operator actually bills. Same approach as EVCC.
- It mainly affects **Charge** mode, where the batteries are force-charged from the grid. In Normal and Hold mode charging only happens from surplus, which never increases grid import.
- The available power is spread **evenly across all batteries**, capped at 2500 W each.
- Requires `P1_HOST`. Without a meter the house consumption is unknown, so only the total battery charge power is capped at the limit.

---

## 🌐 MQTT Integration

This section describes all MQTT topics used by MMBC for integration with Home Assistant, EVCC, and external systems.

| **Topic**                                | **Direction** | **Description**                                                  | **Payload**                             | **Retained** |
|------------------------------------------|---------------|------------------------------------------------------------------|------------------------------------------|---------------|
| `mmbc/virtual/soc`                       | 🔼 Publish    | State of charge (%) for EVCC                                     | float (e.g. `64.2`)                      | Yes           |
| `mmbc/virtual/power`                     | 🔼 Publish    | Battery power (W); positive = charging, negative = discharging   | integer (e.g. `-1200`)                   | Yes           |
|                                          |               |                                                                  |                                          |               |
| `mmbc/control/batterymode`              | 🔽 Subscribe  | Battery mode override (label format)                             | `"Normal"`, `"Hold"`, `"Charge"`, `"Selfcontrol"` | No  |
| `mmbc/status/batterymode`               | 🔼 Publish    | Current battery mode (label format)                              | `"Normal"`, `"Hold"`, `"Charge"`, `"Selfcontrol"` | Yes |
|                                          |               |                                                                  |                                          |               |
| `mmbc/virtual/charged_energy`           | 🔼 Publish    | Total energy charged into the battery (kWh)                      | float (e.g. `123.456`)                   | No            |
| `mmbc/virtual/discharged_energy`        | 🔼 Publish    | Total energy discharged from the battery (kWh)                   | float (e.g. `98.765`)                    | No            |


You can easily ingest this into **Home Assistant**, **Node-RED**, or any MQTT-compatible dashboard.

---
### Battery Mode Labels

The `batterymode` control and status topics use the following labels:

- `"Normal"`: Battery can charge and discharge based on grid power
- `"Hold"`: Battery can charge from excess solar, but discharging is blocked
- `"Charge"`: Battery is forced to charge at full power, regardless of grid import/export
- `"Selfcontrol"`: MMBC releases Modbus control and lets the battery manage itself (default on startup)
- `"Evcc"`: MMBC follows the suggestions of the EVCC optimizer (only offered when `EVCC_HOST` is set)

---

## 🔌 EVCC Mode

[EVCC](https://evcc.io) has an experimental optimizer that plans battery charging and discharging against dynamic energy prices and a solar forecast. MMBC can follow those plans.

```env
EVCC_HOST=http://192.168.1.60:7070
EVCC_BATTERY_NAME=db:14      # optional, defaults to the first controllable battery
EVCC_POLL_SECONDS=30         # optional
```

MMBC reads `<EVCC_HOST>/api/state` and picks up the `suggestion` of your battery device:

```json
{"name": "db:14", "title": "Combined Marstek", "controllable": true,
 "suggestion": {"action": "hold", "charge": 0, "discharge": 0, "actionable": true}}
```

`EVCC_BATTERY_NAME` matches either the `name` (`db:14`) or the `title` (`Combined Marstek`).

| Suggestion  | What MMBC does |
|-------------|----------------|
| `charge`    | Charges at the suggested power, from the grid if needed — but never below the solar surplus that is already available |
| `hold`      | Never discharges, **but a solar surplus is still used to charge** |
| `discharge` | Covers house consumption up to the suggested power. Never discharges into the grid |
| anything else, `actionable: false`, or no answer from EVCC | Behaves like **Normal** mode |

Notes:

- The optimizer plans in 15-minute slots, so the state is fetched every 30 s by default and reused in between.
- If EVCC becomes unreachable the last suggestion is kept for 10 minutes, after which MMBC falls back to Normal mode. It never leaves the batteries stranded on stale advice.
- `GRID_MAX_IMPORT_WATTS` still applies: a `charge` suggestion is throttled to stay under your capacity tariff limit.
- Requires EVCC's experimental optimizer (`experimental: true`) to be enabled — without it there is no `suggestion` field and MMBC logs a warning.

---
## 🧰 Requirements

- Python 3.11+
- Marstek Venus battery with RS485 over Ethernet (e.g. [Waveshare adapter](https://www.amazon.com.be/-/en/Waveshare-Industrial-Rail-Mount-Electrical-Isolation/dp/B0BGBQJH21/ref=sr_1_1?sr=8-1))
- P1 smart meter from HomeWizard with API access
- Docker (optional but recommended)

---



## 🌟 Roadmap / Wishlist

- [x] Multiple battery support
- [x] MQTT publishing for Home Assistant
- [x] MQTT command input (block discharge)
- [ ] Automatic P1 discovery
- [ ] Improved algorithm
- [ ] Live metrics through Influxdb

---

## 📬 Feedback & Contributions

MMBC is developed based on a real dual-battery setup. If you have a Marstek battery and are looking for more flexibility than the standard software, this project might be for you.

Feedback, feature requests and pull requests are welcome:

🔗 [https://github.com/vmangelschots/MMBC](https://github.com/vmangelschots/MMBC)