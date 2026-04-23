# Changelog

All notable changes to this add-on are documented in this file.

## 2.5.2

- Synced runtime GitHub version-check parsing with nested `github.*` options in `config.json`.
- Updated tests and docs to use `github.version_check`, `github.repo`, and `github.check_timeout`.

## 2.5.1

- Aligned telemetry runtime behavior with nested `telemetry.enabled` and `telemetry.interval` options.

## 2.5.0

- Added GitHub version check options (`github_version_check`, `github_repo`, `github_check_timeout`).
- Added startup update payload fields `latest_version`, `update_available`, and `update_source`.
- Added tests for version resolution and update event payload enrichment.

## 2.4.0

- Added MQTT update event topic `mirarus/max7219/tele/update`.
- Added startup/shutdown update event publishing with add-on version payload.
- Added runtime option resolution to include add-on version.
- Added tests for update event payload and runtime version injection.

## 2.3.3

- Added repository-level `.gitignore` for Python cache/test artifacts.

## 2.3.2

- Removed `web_port` option/schema and used fixed internal web port with addon port mapping.

## 2.3.1

- Added `ports_description` and optional `8099/tcp` exposure pattern.

## 2.3.0

- Added Supervisor MQTT service auto-credential flow (`mqtt.auto` + `services: ["mqtt:want"]`).
- Added `credential_source` status metadata.

## 2.2.1

- Aligned MQTT code with nested `config.json` schema (`mqtt.*`) while keeping legacy fallback keys.

## 2.2.0

- Added Home Assistant MQTT Discovery support for text/mode/effect/brightness/status entities.
