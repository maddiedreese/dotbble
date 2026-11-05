# Agent setup guide

Use this runbook when the user asks Codex or a dot to set up Dotbble for them. Carry out the steps with available tools; do not merely summarize the README. The user has requested setup of their own ring-to-dot connection, including temporary pairing. Follow the host's authorization rules and request only approvals that are actually required.

## Desired result

The user's Pebble Index recording is cloud-transcribed on the Pebble side, delivered directly from the phone plugin to OpenAI, and acted on in the intended dot conversation. Every message includes the act-now instruction. The subscription has no scheduled expiration. The Mac and tunnel client are stopped after pairing and are not used for daily delivery.

Read [README.md](README.md) first. Use its exact phone settings and manual steps. The tested Pebble app version is **1.15.0.1**. Do not change a working phone configuration or upgrade the app merely to perform setup.

## 1. Establish the target and available tools

- Identify the user's intended dot, ChatGPT workspace, and Platform organization from available context. Ask one concise question only if the target is ambiguous. Do not subscribe the setup conversation if the intended dot is elsewhere.
- Check whether you have terminal/file access on the user's Mac and browser access to their signed-in OpenAI account. A remote sandbox is not automatically their Mac. If a capability is absent, tell the user the specific step they need to do, then continue independent work.
- Check access to Platform tunnels, custom MCP plugins, and MCP Events in the target account. Do not claim these are available to every ChatGPT account. If account access is missing, stop the dependent account setup and report the missing capability.
- Reuse a suitable existing Dotbble connection in the user's account. Inspect only nonsecret status first. Do not clear app data, revoke a working subscription, or create duplicate subscriptions as a shortcut.

## 2. Prepare a clean local checkout

Clone this repository into a new folder on the Mac, or use an existing clean checkout. Inspect local instructions. Keep all generated pairing state in `.private/`; do not place it in a shared folder or commit it. Use a different checkout/state directory for a different owner.

Check `python3 --version` (3.11+). No Python dependencies are required. Use the committed `dist/dotbble.pbw` for phone installation; Node.js is needed only for development. If building, run `npm ci`, `npm test`, and `npm run check:dist`.

Help the user enable Pebble plugins and open the PBW in Pebble. Confirm the settings page loads before spending time on account pairing. Installing this plugin uses Pebble's plugin import; it does not require building or sideloading a custom iPhone application.

## 3. Prepare the temporary OpenAI connection

Follow the current official [Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) and the installed client's help when needed.

1. Create or select the user's **Dotbble Pairing** tunnel in [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels).
2. Verify the Platform organization and target ChatGPT workspace associations. Creating a tunnel requires **Read + Manage**; running it and selecting it requires **Read + Use**.
3. Download the official macOS client from the Platform download link or [official releases](https://github.com/openai/tunnel-client/releases/latest). Choose the correct CPU architecture and keep companion files together. Do not fetch binaries from third-party mirrors or disable platform protections to run them.
4. Have the user create/select a runtime key with **Tunnels Read + Use**. Do not request the literal key in chat, read it from unrelated files, put it on the command line, or copy it into a document.
5. Start `python3 start_pairing.py` in the checkout. The launcher must run in an interactive user-accessible Terminal because its key prompt is hidden. If you cannot provide that private entry surface, open a Terminal or give the user the command and wait for confirmation that it is running. Do not work around the hidden prompt by writing the key into a script.

Keep the launcher running through subscription setup. It runs `doctor`, launches the stdio pairing server through the tunnel, and records lifecycle state under `.private/`. The program never ingests phone transcripts.

## 4. Install the private ChatGPT plugin and subscribe the right dot

Use [ChatGPT Plugins](https://chatgpt.com/plugins) → **+ → Add custom MCP server**. Name it **Dotbble Pairing**, select **Connection: Tunnel**, and choose the user's tunnel. The stdio server needs **No authentication** beyond private tunnel access. Review the connection and install the plugin in the intended account/workspace.

Check that discovery exposes:

- Event: `ring.message`
- Read-only tool: `ring_phone_pairing_status`

In the **intended dot**, use the subscription prompt from README step 4. If you cannot interact with that dot, give the user that exact prompt to paste there. Do not silently substitute an ordinary chat, new dot, or Responses API conversation.

Request a persistent subscription with empty arguments and no end date or polling task. Use `ttlMs: null` if the calling surface exposes it; never place a transport TTL in the event's filter arguments. This server uses a non-expiring default for omitted TTLs.

Verify the actual outcome rather than accepting a natural-language success claim. The status tool must show:

```json
{
  "active_subscriptions": 1,
  "nonexpiring_subscriptions": 1
}
```

Inspect only the safe grant audit `.private/state/last_subscription_grant.json` to confirm `callback_verified: true` and `refresh_before: null`. Do not print `.private/state/subscriptions.json` or its secret. Do not manually edit a finite grant into a non-expiring one.

The status tool's `phone_delivery_verified: false` is intentional: this setup server has no transcript access and cannot verify phone delivery. That evidence comes from the final phone-to-dot test.

## 5. Stop the runtime, then pair the phone

Have the user press **Control-C** in the launcher (or stop that specific launcher through its controlling terminal), and wait for its stopped message. Do not kill unrelated processes. Run:

```sh
python3 finish_pairing.py
```

It creates `.private/MY-PHONE-PAIRING.json` after checking the runtime has stopped and a non-expiring subscription exists. Repeat runs preserve a matching export's device identity. If an old, conflicting export exists, explain it and help the user move that old file to private backup before exporting the replacement; do not erase a working pairing.

Direct the user to privately transfer the JSON to their phone and paste it into **Dotbble → Settings → Private pairing JSON → Pair connection**. Never ask them to attach the JSON to the chat, put its contents in a QR code shown in chat, or publish it. In Finder, **Command-Shift-period** reveals `.private/`.

Have them report only the safe status fields: `ready: true`, `pairingMode: "non-expiring"`, `expires: null`. Do not ask them to share the pairing field itself. A version-1/one-hour pairing is not completion.

## 6. Set the phone routing

Help the user select **cloud speech recognition**, the **local assistant**, **Notes** as the capture action, and **Dotbble** as the notes destination. Keep cloud backup off for this configuration. Dotbble does not need Pebble's separate webhook feature, a Shortcut, another relay, or a permanent Mac process.

Use Pebble's ring onboarding for Bluetooth/background permissions. Do not assume cloud transcription is disabled just because the assistant is local: these are separate stages.

## 7. Verify and hand off

Use harmless, distinctive in-chat requests, such as “Write a two-sentence story about a blue kite.”

1. Turn off the Mac; send through the ring. Confirm a spontaneous reply in the intended dot.
2. Restart the phone, unlock once and open Pebble, then send again without re-pairing.
3. Lock the phone, leave it idle for several minutes, and send through the ring. Confirm delivery before unlocking using another device or reliable timestamps. A response seen only after reopening Pebble does not establish locked-phone delivery.

If a hardware step needs the user's participation, mark it pending and ask for that result. Do not invent completion or silently substitute mocked tests. The project is a working setup; the verification checks this user's installation.

Finish with a short handoff listing:

- The dot and plugin connected, plus the local checkout path.
- Non-expiring grant confirmed and temporary runtime stopped.
- Which direct-delivery, restart, and locked-phone checks actually passed.
- How to open Dotbble status and disconnect; remind them the pairing file is private.

No routine Mac startup or re-pairing is needed. For connection replacement or lifecycle troubleshooting, use the README and [architecture guide](docs/architecture.md). Preserve the user's private state for maintenance.
