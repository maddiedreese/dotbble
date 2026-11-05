# Security

Never include `.private/`, pairing JSON, runtime API keys, callback URLs, or real transcripts in public issues, pull requests, screenshots, or logs.

For a suspected credential exposure, stop phone delivery with **Disconnect and clear**, disable the corresponding ChatGPT event subscription, and revoke/replace affected credentials in the owning service. Clearing local storage alone cannot revoke copies of a credential. Restart the pairing server only when needed for subscription maintenance.

Report a vulnerability using this repository's **Security → Report a vulnerability** option if available. If it is unavailable, open an issue asking for a private contact channel without publishing the exploit or sensitive details.

Please include the affected Dotbble and Pebble versions, a description of impact, and a reproduction using synthetic data. The [architecture guide](docs/architecture.md) documents credential storage, native fetch limitations, and the offline pairing server's lifecycle boundaries.
