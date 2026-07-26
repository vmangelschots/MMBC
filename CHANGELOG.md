# Changelog

## [2.0.0] - 2026-07-26

### Added
- **Grid import limit** (`GRID_MAX_IMPORT_WATTS`, optional): caps total charge power so house consumption plus battery charging stays below the configured number of watts. Aimed at the Belgian capacity tariff. Unset means no limit, which is the previous behaviour.
- **Evcc mode** (numeric `5`, MQTT label `"Evcc"`): follows the battery suggestions of EVCC's experimental optimizer, read from `<EVCC_HOST>/api/state`. Configured with `EVCC_HOST`, `EVCC_BATTERY_NAME` and `EVCC_POLL_SECONDS`. A `hold` suggestion still charges from solar surplus, `charge` charges at the suggested power (never below the available surplus), and `discharge` covers house consumption capped at the suggested power without exporting. Falls back to Normal whenever no usable suggestion is available. The mode is only offered when `EVCC_HOST` is set.

- **EVCC MQTT entities**: what EVCC asks for is published as `evcc/action`, `evcc/charge`, `evcc/discharge` and `evcc/actionable`, plus `evcc/following` which tells you whether MMBC is acting on it. Published in every mode whenever `EVCC_HOST` is set.
- **Resulting action entities**: `target_action` and `target_power` publish what the controller last told the batteries to do, in every mode. Comparing `target_power` with `power` shows whether the batteries follow their setpoint.

### Fixed
- **Charge mode** no longer idles when the grid happens to be balanced (within ±30W); it now charges regardless of grid flow as documented
- Documented sign convention of `mmbc/virtual/power` corrected in the README: it is positive when discharging, not when charging
- MMBC now reports the battery mode it actually runs over MQTT instead of the one that was requested, so a mode the controller refuses no longer shows up as active
- `_write_if_changed` no longer caches a register value when the Modbus write fails — failed writes are retried on the next cycle
- `set_battery_mode` now uses `==` instead of `is` for integer comparison

## [1.1.2]

### Changed
- **Hold mode** now allows charging from excess solar/grid but blocks discharging (previously blocked both)
- **Normal mode** re-added after being removed in 1.1.0
- Numeric mode values (`1`–`4`) are now accepted over MQTT in addition to string labels
- Invalid MQTT mode input now defaults to `selfcontrol` instead of crashing

### Added
- `"Selfcontrol"` added as an explicit MQTT battery mode option (numeric `4`)

### Fixed
- Default on invalid MQTT mode input no longer silently sets wrong mode

## [1.1.1]

### Added
- MQTT username/password authentication support

### Fixed
- Typo in `BATTERY_3_ADDRESS` environment variable name

## [1.1.0]

### Added
- Support for a third battery (`BATTERY_3_*`)
- P1 meter is now optional — MMBC runs without it (net power defaults to 0)
- Battery self-control mode set as default on startup
- Extra MQTT logging

### Changed
- Normal mode removed (re-added in 1.1.2)
- Write deduplication: registers are only written when the value changes

## [1.0.0]

### Added
- Initial release
- HomeWizard P1 meter integration
- Modbus TCP control for Marstek Venus E batteries
- Multiple battery support with SoC-based priority selection
- MQTT publishing with Home Assistant auto-discovery
- Battery modes: Hold, Charge, Selfcontrol
- Home Assistant add-on config support (`/data/options.json`)
