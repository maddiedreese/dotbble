# Working in Dotbble

If the user asks to **set this up**, read `README.md` and `SETUP.md` and carry out the agent setup runbook. Do not treat a setup request as a request to redesign or deploy a relay service. Creating an account connection still follows the user's authorization and the host's approval rules.

If the user asks to **develop or review code**, use `npm ci`, `npm test`, and `npm run check:dist`. Python requires 3.11+; Node requires 20.19+. Commit generated `dist/` artifacts with source changes. Preserve the plugin UUID, source instance identity, and storage keys for compatible upgrades.

Never read or print private signing credentials unnecessarily. `.private/` and `MY-PHONE-PAIRING*.json` are private machine state, not project source. Do not include them in commits, issues, screenshots, examples, or chat. Automated tests use synthetic values and mocked transport.

Document the setup as working on the confirmed Pebble app version, 1.15.0.1. State actual verification results and specific compatibility limits. Do not claim tests on a device or app version you did not test.
