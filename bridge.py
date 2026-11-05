#!/usr/bin/env python3
"""MCP subscription persistence, callback verification, and signing utilities."""
import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

EVENT = "ring.message"
EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
TOOL = {
    "name": "ring_phone_pairing_status", "title": "Dotbble pairing status",
    "description": "Read pairing status without credentials or transcripts.",
    "inputSchema": EMPTY,
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
}

def iso(timestamp=None):
    return datetime.fromtimestamp(time.time() if timestamp is None else timestamp, timezone.utc).isoformat()

def write_private(path, data):
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def setup(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    config = directory / "config.json"
    if not config.exists():
        write_private(config, {"path_token": secrets.token_urlsafe(32)})
    return json.loads(config.read_text())

def load_subs(directory):
    path = directory / "subscriptions.json"
    return json.loads(path.read_text()) if path.exists() else {}

def save_subs(directory, subscriptions):
    write_private(directory / "subscriptions.json", subscriptions)

def secret_bytes(secret):
    if not isinstance(secret, str) or not secret.startswith("whsec_"):
        raise ValueError("Invalid webhook secret")
    try:
        key = base64.b64decode(secret[6:], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid webhook secret") from exc
    if not 24 <= len(key) <= 64:
        raise ValueError("Invalid webhook secret size")
    return key

def signed_headers(sub, event_id, body, now=None):
    stamp = str(int(time.time() if now is None else now))
    message = event_id.encode() + b"." + stamp.encode() + b"." + body
    signature = base64.b64encode(hmac.new(secret_bytes(sub["secret"]), message, hashlib.sha256).digest()).decode()
    return {"Content-Type": "application/json", "webhook-id": event_id,
            "webhook-timestamp": stamp, "webhook-signature": "v1," + signature,
            "X-MCP-Subscription-Id": sub["id"]}

def callback_target(url):
    if not isinstance(url, str) or len(url) > 4096:
        raise ValueError("Invalid callback URL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Callback must be HTTPS without credentials or fragment")
    if parsed.port not in (None, 443):
        raise ValueError("Pairing supports HTTPS port 443 only")
    host = parsed.hostname.encode("idna").decode("ascii")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Callback DNS failed")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast or (getattr(ip, "ipv4_mapped", None) and not ip.ipv4_mapped.is_global):
            raise ValueError("Callback must resolve only to public addresses")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return host, path, addresses

def safe_post(url, body, headers):
    """Resolve, validate and pin address; verify original TLS host. Never redirect."""
    host, path, addresses = callback_target(url)
    family, socktype, proto, _, sockaddr = addresses[0]
    raw = socket.socket(family, socktype, proto)
    raw.settimeout(10)
    connection = http.client.HTTPSConnection(host, 443, timeout=10)
    try:
        raw.connect(sockaddr)
        connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError("Callback response too large")
        return response.status, payload
    finally:
        connection.close()
        raw.close()

def verify_callback(sub, post=safe_post):
    challenge = secrets.token_urlsafe(32)
    event_id = "verify_" + uuid.uuid4().hex
    body = json.dumps({"type": "verification", "challenge": challenge}, separators=(",", ":")).encode()
    status, payload = post(sub["url"], body, signed_headers(sub, event_id, body))
    if not 200 <= status < 300:
        raise ValueError("Callback verification HTTP failure")
    echoed = json.loads(payload).get("challenge")
    if not isinstance(echoed, str) or not hmac.compare_digest(echoed, challenge):
        raise ValueError("Callback challenge failed")


def dispatch(directory, method, params, post=safe_post, *, event_name=EVENT, allow_nonexpiring=False, default_ttl_ms=3600000):
    if not isinstance(params, dict):
        raise ValueError("Params must be an object")
    if method == "server/discover":
        return {"resultType": "complete", "supportedVersions": ["2026-07-28"],
                "serverInfo": {"name": "dotbble", "version": "1.0.0"},
                "capabilities": {"tools": {}, "events": {}}}
    if method == "initialize":
        return {"protocolVersion": "2026-07-28", "serverInfo": {"name": "dotbble", "version": "1.0.0"},
                "capabilities": {"tools": {}, "events": {}},
                "instructions": "Dotbble pairing server. Subscriptions require an explicit user request."}
    if method == "ping":
        return {}
    if method in ("resources/list", "resources/templates/list", "prompts/list"):
        key = {"resources/list": "resources", "resources/templates/list": "resourceTemplates", "prompts/list": "prompts"}[method]
        return {key: []}
    if method in ("events/subscribe", "events/unsubscribe"):
        if params.get("name") != event_name or params.get("arguments", {}) != {}:
            raise ValueError("Unknown event or nonempty filter")
        delivery = params.get("delivery", {})
        if not isinstance(delivery, dict) or delivery.get("mode") != "webhook":
            raise ValueError("Webhook delivery required")
        url = delivery.get("url")
        if not isinstance(url, str):
            raise ValueError("Missing callback URL")
        # A private state directory identifies one owner; tunnel access authenticates calls.
        owner = setup(directory)["path_token"]
        identity = json.dumps([owner, url, event_name, {}], separators=(",", ":"))
        sub_id = "sub_" + hashlib.sha256(identity.encode()).hexdigest()[:32]
        subscriptions = load_subs(directory)
        if method == "events/unsubscribe":
            subscriptions.pop(sub_id, None)
            save_subs(directory, subscriptions)
            return {}
        secret = delivery.get("secret")
        secret_bytes(secret)
        ttl = params.get("ttlMs", default_ttl_ms)
        nonexpiring = ttl is None and allow_nonexpiring
        if ttl is None and not nonexpiring:
            ttl = 3600000
        if not nonexpiring and (isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0):
            raise ValueError("Invalid ttlMs")
        expires = None if nonexpiring else time.time() + min(ttl / 1000, 3600)
        sub = {"id": sub_id, "url": url, "secret": secret, "expires": expires, "name": event_name}
        active = {k: v for k, v in subscriptions.items() if v["expires"] is None or v["expires"] > time.time()}
        if sub_id not in active and len(active) >= 4:
            raise ValueError("Pairing subscription limit reached")
        try:
            verify_callback(sub, post)
        except Exception as exc:
            raise CallbackError() from exc
        active[sub_id] = sub
        save_subs(directory, active)
        return {"id": sub_id, "refreshBefore": None if nonexpiring else iso(expires), "cursor": None, "truncated": False}
    raise LookupError("Method not supported")

class CallbackError(Exception):
    pass
