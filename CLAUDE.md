# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

MMBC (Multiple Marstek Battery Controller) is a Python daemon that reads live power from a HomeWizard P1 smart meter and controls one or more Marstek Venus E batteries over Modbus TCP to keep grid import/export near zero. It publishes aggregated battery state over MQTT with Home Assistant auto-discovery.

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env

# Run the controller
python mmbc.py


# Run via Docker
docker run --env-file .env --restart unless-stopped ghcr.io/vmangelschots/mmbc:latest
```

There are no automated tests in this project.

## Configuration

Config is loaded by `core/config_loader.py`, which first checks `/data/options.json` (Home Assistant add-on format) then falls back to environment variables. See `.env.example` for all available keys.

Required env vars: `BATTERY_1_IP`, `BATTERY_1_ADDRESS`  
Optional: `BATTERY_2_*`, `BATTERY_3_*`, `P1_HOST`, `MQTT_*`

## Architecture

The system has three layers connected through abstract interfaces:

**Interfaces** (`interfaces/`)
- `BatteryInterface` — abstract base for all battery implementations (`get_soc`, `get_current_wattage`, `charge`, `discharge`, `idle`, `get_total_charged_kwh`, `get_total_discharged_kwh`)
- `MeterInterface` — abstract base for meter implementations (`get_net_power`)

**Implementations**
- `batteries/venus_battery.py` — Modbus TCP driver for the Marstek Venus E. Manages connection (with exponential backoff), write deduplication via `last_written_values`, control mode acquisition/release (`0x55aa`/`0x55bb` to register 42000), and signed 32-bit power reads (two registers at 32202).
- `batteries/fake_battery.py` — stub for development
- `meters/homewizard_p1_meter.py` — polls the HomeWizard P1 REST API
- `meters/fake_meter.py` — stub for development

**Core**
- `core/controller.py` — main control loop (3s interval). Reads meter power, adds current battery output to get `adjusted_power`, then decides charge/discharge/idle. Modes: `BATTERY_NORMAL` (1), `BATTERY_HOLD` (2), `BATTERY_CHARGE` (3), `BATTERY_SELFCONTROL` (4, default). Battery priority list is cached for 5 minutes and invalidated early if a selected battery becomes ineligible (SoC limits: discharge min 11%, charge max 100%). Power above 2500W splits across multiple batteries.
- `core/mqtt_publisher.py` — runs in a daemon thread, publishes aggregated and per-battery metrics every 3s, subscribes to `mmbc/control/batterymode` for mode changes, and publishes Home Assistant MQTT discovery configs on startup.
- `core/config_loader.py` — config resolution (options.json → env)

**Entry point**: `mmbc.py` — reads env, instantiates meter + batteries + controller + MQTT publisher, starts MQTT thread, then calls `controller.run_forever()`.

## Key Implementation Notes

- **Control mode**: On startup, `VenusBattery` writes `0x55aa` to register 42000 to take Modbus control. `release()` writes `0x55bb`. The control mode register is re-checked every 60 seconds and reapplied if lost (battery may reset it after a power cycle).
- **Power sign convention**: `get_current_wattage()` returns positive for discharge, negative for charge. The meter's `get_net_power()` returns positive when importing from the grid.
- **BATTERY_SELFCONTROL mode**: MMBC releases Modbus control and lets the battery manage itself. This is the default on startup. Any other mode takes Modbus control of all batteries.
- **Adding a new meter or battery type**: Implement the relevant interface in `interfaces/`, place the file in `meters/` or `batteries/`, and wire it up in `mmbc.py`.
