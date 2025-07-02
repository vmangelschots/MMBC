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
P1_API_URL=http://192.168.x.x/api/v1/data
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

## 🌐 MQTT Integration

This section describes all MQTT topics used by MMBC for integration with Home Assistant, EVCC, and external systems.

| **Topic**                                | **Direction** | **Description**                                                  | **Payload**                             | **Retained** |
|------------------------------------------|---------------|------------------------------------------------------------------|------------------------------------------|---------------|
| `mmbc/virtual/soc`                       | 🔼 Publish    | State of charge (%) for EVCC                                     | float (e.g. `64.2`)                      | Yes           |
| `mmbc/virtual/power`                     | 🔼 Publish    | Battery power (W); positive = charging, negative = discharging   | integer (e.g. `-1200`)                   | Yes           |
|                                          |               |                                                                  |                                          |               |
| `mmbc/control/batterymode`              | 🔽 Subscribe  | Battery mode override (label format)                             | `"Normal"`, `"Hold"`, `"Charge"` | No            |
| `mmbc/status/batterymode`               | 🔼 Publish    | Current battery mode (label format)                              | `"Normal"`, `"Hold"`, `"Charge"` | Yes           |
|                                          |               |                                                                  |                                          |               |
| `mmbc/virtual/charge_total_wh`          | 🔼 Publish    | Total energy charged into the battery (Wh)                       | unsigned int                             | Yes           |
| `mmbc/virtual/discharge_total_wh`       | 🔼 Publish    | Total energy discharged from the battery (Wh)                    | unsigned int                             | Yes           |


You can easily ingest this into **Home Assistant**, **Node-RED**, or any MQTT-compatible dashboard.

---
### Battery Mode Labels

The `batterymode` control and status topics use the following labels:

- `"Normal"`: Battery can charge and discharge (default behavior)
- `"Hold"`: Battery can charge, but discharging is disabled
- `"Charge"`: Battery is forced to charge, regardless of grid import/export
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