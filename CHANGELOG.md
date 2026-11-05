# Changelog

## 1.0.0

- First public Dotbble release, based on the working Ring Dot Direct Test 0.3.0 phone plugin and lasting-pairing setup.
- Renamed the phone UI and package to Dotbble while preserving the plugin UUID, source instance identity, and persistent storage keys.
- Retained direct signed delivery, non-expiring pairing, per-message instructions, bounded retries, and diagnostics.
- Removed “test” wording from the automatic instruction while preserving its in-chat scope. Events now identify normal use with `is_test: false` and `trigger: "pebble-plugin"`.
- Added portable Mac setup scripts, complete instructions, reproducible PBW packaging, and automated checks.
- Removed the unrelated desktop synthetic-event sender and HTTP server from the public pairing utilities.

The public packaging and naming changes are covered by automated tests. The README's real-device results refer to the working setup from which this release was prepared.
