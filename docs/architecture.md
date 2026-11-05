# Architecture

## Pairing and daily delivery are separate

During setup, OpenAI's `tunnel-client` launches `pairing.py` over stdio. The tunnel authenticates access; there is no public Python HTTP listener. Each private state directory belongs to one owner and accepts one active dot callback. The server advertises `ring.message` and the read-only `ring_phone_pairing_status` tool.

When ChatGPT subscribes, it supplies a callback URL and signing secret. The pairing server:

1. Requires an HTTPS OpenAI callback on port 443, with no user information or fragment.
2. Resolves and rejects non-public addresses, pins the connection to a validated address, and verifies TLS against the original hostname.
3. Sends a fresh signed challenge and requires the correct echoed challenge before persisting the grant.
4. Stores subscription state with private filesystem permissions.
5. Records the granted expiration separately from credentials.

`finish_pairing.py` exports a version-2 configuration only after the recorded local runtime stops and exactly one non-expiring subscription exists. A matching existing export is retained to avoid resetting message identity. The phone imports this configuration; no Mac service participates in delivery afterward.

## Non-expiring subscriptions

The working configuration grants `refreshBefore: null` and exports `expires: null`. `pairing.py` uses a non-expiring default when the subscription request omits `ttlMs`, and also accepts an explicit `ttlMs: null`. Explicit finite requests remain finite, capped at one hour for compatibility with earlier pairings.

OpenAI's [MCP Events documentation](https://developers.openai.com/plugins/build/mcp-events) describes both server defaults for omitted TTLs and explicit-null requests for non-expiring grants. Dotbble's observed ChatGPT setup omitted the field, so the implementation records `ttl_explicit`, `requested_ttl_ms`, and `used_nonexpiring_default` in the local grant audit. It verifies the actual grant rather than relying on a chat description or editing an expiration afterward.

No scheduled expiry means no routine renewal; it does not prevent the user or service from revoking a connection. Rotation and unsubscribe calls require the pairing server to be online. The phone stops using credentials on HTTP 410. See the README for disconnecting and replacing a pairing.

## Phone delivery

Pebble's local assistant invokes the plugin's `create_note` action with the transcript. Cloud speech recognition happens before this action. The plugin advertises `notes/configured` and `notes/destination`; it becomes available as a destination only when paired and ready.

The sender adds this instruction to every transcript:

> Act on my spoken request below now and send your response in this dot conversation. Do not wait for another message asking you to check for events. Complete in-chat requests only, following normal safety and approval requirements.
>
> My spoken request:

This is intentional behavior for the owner's voice-command workflow. The transcript follows unchanged. The subscription instruction authorizes responding to these events; per-message instructions do not grant access to tools or override approvals.

The event contains `eventId`, `name: "ring.message"`, `timestamp`, `data`, and `cursor: null`. `data` contains the prefixed text, `receipt_id`, `recorded_at`, `received_at`, `is_test: false`, and `trigger: "pebble-plugin"`. Both data timestamps currently represent the time the plugin receives the action, not the original audio capture time. The plugin cannot identify whether the text originated from the ring or the phone microphone.

The event ID combines a random device identifier generated on the Mac with a persistent phone counter. The body is serialized once, persisted before sending, and signed using Standard Webhooks HMAC-SHA256. The sender includes `Content-Type`, `webhook-id`, `webhook-timestamp`, `webhook-signature`, and `X-MCP-Subscription-Id` headers.

The tested Pebble runtime provides `fetch` and local storage but not the Web Crypto primitives needed here. The plugin bundles `@noble/hashes` and a tested UTF-8 implementation. No crypto service or text relay is involved.

## Delivery state and limits

- One pending request at a time. New actions fail clearly until an unconfirmed delivery is resolved.
- Manual retries preserve the body and event ID and create a fresh signature. Maximum three attempts within five minutes; there is no background retry scheduler or durable multi-message outbox.
- A 2xx response clears pending text and stores a receipt. It confirms HTTP acceptance; the dot processes the event asynchronously.
- Most 4xx responses clear pending state. HTTP 408 and 429 retain it for retry; 410 also clears the connection. HTTP 413 is not retried.
- Input is limited to 8,000 UTF-16 code units and serialized events to 256 KiB.
- Legacy version-1 pairings retain a one-hour maximum and ten-message cap. Version-2 pairings require a null expiry and have no ten-message cap.
- Diagnostics retain only the last 40 stages. They do not detect lock state or log transcripts, credentials, callback URLs, or transport exception details.

## Storage and transport boundaries

The phone uses ordinary plugin `localStorage`, not Keychain storage. An unconfirmed message remains there until resolved or disconnected. The Mac's `.private/` directory includes signing credentials and must stay private. The API runtime key is entered through `getpass` and passed to the tunnel client through an environment reference; the launcher does not save it.

The phone validates callback domains against `openai.com` and `chatgpt.com` and requests `redirect: "error"`. The native fetch implementation in the tested Pebble runtime does not enforce all browser fetch options. Unlike the Python challenge verifier, the plugin cannot pin DNS resolution or independently enforce transport redirect policy. Its internet permission and URL validation restrict the intended destination to OpenAI; this is not a generic webhook sender.

## Compatibility and testing

The setup was confirmed on Pebble 1.15.0.1. Newer Pebble plugin API versions need their own compatibility checks. The public plugin retains the original UUID, notes instance identity, and storage keys so existing installations can update without deliberately resetting a pairing.

Tests cover signing against Node's HMAC, Unicode encoding, callback restrictions, verification failures, private exports, persisted identities, retries, revocation responses, and non-expiring state after a simulated 90-day clock advance. The clock simulation is a unit test, not a claim of a 90-day live soak test. Automated tests do not exercise Bluetooth, phone background scheduling, or a real OpenAI account.

## Protocol references

- [OpenAI MCP Events](https://developers.openai.com/plugins/build/mcp-events)
- [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Pebble plugin API](https://developer.repebble.com/guides/plugins/preview/)
