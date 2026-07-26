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
Optional: `BATTERY_2_*`, `BATTERY_3_*`, `P1_HOST`, `MQTT_*`, `SELF_CONTROL_AVAILABLE`, `GRID_MAX_IMPORT_WATTS`, `EVCC_HOST`, `EVCC_BATTERY_NAME`, `EVCC_POLL_SECONDS`

## Architecture

The system has three layers connected through abstract interfaces:

**Interfaces** (`interfaces/`)
- `BatteryInterface` — abstract base for all battery implementations (`get_soc`, `get_current_wattage`, `charge`, `discharge`, `idle`, `get_total_charged_kwh`, `get_total_discharged_kwh`)
- `MeterInterface` — abstract base for meter implementations (`get_net_power`)
- `OptimizerInterface` — abstract base for external optimizers (`get_suggestion` → `Suggestion(action, charge, discharge, actionable)` or `None`)

**Implementations**
- `batteries/venus_battery.py` — Modbus TCP driver for the Marstek Venus E. Manages connection (with exponential backoff), write deduplication via `last_written_values`, control mode acquisition/release (`0x55aa`/`0x55bb` to register 42000), and signed 32-bit power reads (two registers at 32202).
- `batteries/fake_battery.py` — stub for development
- `meters/homewizard_p1_meter.py` — polls the HomeWizard P1 REST API
- `meters/fake_meter.py` — stub for development
- `optimizers/evcc_optimizer.py` — polls EVCC's `/api/state` and extracts the `suggestion` of a battery device under `battery.devices`. Caches for `poll_interval` (default 30s), keeps the last suggestion for `max_age` (default 600s) when EVCC is unreachable, then returns `None`.

**Core**
- `core/controller.py` — main control loop (3s interval). Reads meter power, adds current battery output to get `adjusted_power`, then decides charge/discharge/idle. Modes: `BATTERY_NORMAL` (1), `BATTERY_HOLD` (2), `BATTERY_CHARGE` (3), `BATTERY_SELFCONTROL` (4, default), `BATTERY_EVCC` (5). Each mode dispatches to a `_run_*` helper; `_run_normal`/`_run_hold` apply the ±30W deadband, the forced-charge paths deliberately do not. Battery priority list is cached for 5 minutes and invalidated early if a selected battery becomes ineligible (SoC limits: discharge min 11%, charge max 100%). Power above 2500W splits across multiple batteries.
- **Grid import limit** (optional, `GRID_MAX_IMPORT_WATTS`): `_charge_headroom()` returns how much charge power still fits under the limit given the house consumption (`adjusted_power`, which already excludes battery power). `_cap_charge_power()` applies it on the NORMAL/HOLD charge paths (where it never binds, since those only charge from surplus) and `_charge_all()` applies it in BATTERY_CHARGE mode, splitting the headroom evenly across all batteries. `None` means no limit. Without a meter the house consumption is unknown, so the headroom is just the limit itself.
- `core/mqtt_publisher.py` — runs in a daemon thread, publishes aggregated and per-battery metrics every 3s, subscribes to `mmbc/control/batterymode` for mode changes, and publishes Home Assistant MQTT discovery configs on startup. Also publishes the controller's last decision (`target_action`/`target_power`, from `controller.last_action`) and, when an optimizer is configured, the EVCC suggestion under `evcc/*` as a separate HA device. Sensors marked `combined_only` in `publish_discovery_config()` are skipped for per-battery devices.
- `core/config_loader.py` — config resolution (options.json → env)

**Entry point**: `mmbc.py` — reads env, instantiates meter + batteries + controller + MQTT publisher, starts MQTT thread, then calls `controller.run_forever()`.

## Key Implementation Notes

- **Control mode**: On startup, `VenusBattery` writes `0x55aa` to register 42000 to take Modbus control. `release()` writes `0x55bb`. The control mode register is re-checked every 60 seconds and reapplied if lost (battery may reset it after a power cycle).
- **Power sign convention**: `get_current_wattage()` returns positive for discharge, negative for charge. The meter's `get_net_power()` returns positive when importing from the grid.
- **BATTERY_SELFCONTROL mode**: MMBC releases Modbus control and lets the battery manage itself. This is the default on startup. Any other mode takes Modbus control of all batteries.
- **BATTERY_EVCC mode**: `_run_evcc()` maps EVCC's suggestion onto the existing behaviours — `charge` → `_charge(max(suggested, surplus))`, `hold` → `_run_hold()` (deliberately still charges from surplus), `discharge` → `_run_normal(max_discharge=suggested)` (never exports). Anything else, a non-actionable suggestion, or `None` falls back to `_run_normal()`. The mode is refused (falls back to Normal) when no optimizer is configured, mirroring `self_control_available`.
- **Adding a new meter, battery or optimizer type**: Implement the relevant interface in `interfaces/`, place the file in `meters/`, `batteries/` or `optimizers/`, and wire it up in `mmbc.py`.
- **Adding a mode**: add the constant in `core/controller.py`, dispatch it in `run_forever()`, and add it to `MODE_LABELS` in `core/mqtt_publisher.py` (`MODE_VALUES` and the HA discovery options derive from it). Modes that can be unavailable are refused in `set_battery_mode()` and hidden from the HA select.
