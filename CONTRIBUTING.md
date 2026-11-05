# Contributing

Bug reports, documentation fixes, and compatibility updates are welcome. Include your Dotbble and Pebble app versions, the expected behavior, and the observed behavior. Use synthetic phrases and redact callback identities and credentials.

For a code change:

1. Install Node.js 20.19+ and Python 3.11+.
2. Run `npm ci` and `npm test`.
3. Commit source changes and the regenerated `dist/dotbble.pbw` and `dist/SHA256SUMS.txt`.
4. Describe what you tested. Distinguish unit tests from actual phone/ring tests; note whether the Mac was off and whether the phone stayed locked.

Preserve the plugin UUID and storage keys for compatible updates. Do not reset the pairing counter or reuse a device ID across phones. Never add real pairing fixtures, logs, API keys, or `.private/` to a commit. Network calls in automated tests should be mocked.

The default message instruction limits actions to the dot conversation. Changes that broaden behavior or alter credentials, delivery identity, retries, or subscription lifetime should be explicit in the pull request and documented for users.
