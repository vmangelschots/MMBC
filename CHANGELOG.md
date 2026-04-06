# Changelog

## [Unreleased]

### Fixed
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
