import { hmac } from '@noble/hashes/hmac.js';
import { sha256 } from '@noble/hashes/sha2.js';

const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export const MESSAGE_PREAMBLE = 'Act on my spoken request below now and send your response in this dot conversation. Do not wait for another message asking you to check for events. Complete in-chat requests only, following normal safety and approval requirements.\n\nMy spoken request:\n';
export function utf8(text) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    let c = text.codePointAt(i);
    if (c > 0xffff) i++;
    else if (c >= 0xd800 && c <= 0xdfff) c = 0xfffd;
    if (c < 128) out.push(c);
    else if (c < 2048) out.push(192 | c >> 6, 128 | c & 63);
    else if (c < 65536) out.push(224 | c >> 12, 128 | c >> 6 & 63, 128 | c & 63);
    else out.push(240 | c >> 18, 128 | c >> 12 & 63, 128 | c >> 6 & 63, 128 | c & 63);
  }
  return new Uint8Array(out);
}
export function base64(bytes) {
  let result = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const n = bytes[i] << 16 | (bytes[i + 1] || 0) << 8 | (bytes[i + 2] || 0);
    result += alphabet[n >>> 18 & 63] + alphabet[n >>> 12 & 63];
    result += i + 1 < bytes.length ? alphabet[n >>> 6 & 63] : '=';
    result += i + 2 < bytes.length ? alphabet[n & 63] : '=';
  }
  return result;
}
export function decodeKey(secret) {
  if (typeof secret !== 'string' || !secret.startsWith('whsec_')) throw new Error('Invalid signing key.');
  const text = secret.slice(6);
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(text)) throw new Error('Invalid signing key.');
  const out = [];
  let buffer = 0, bits = 0;
  for (const c of text.replace(/=+$/, '')) {
    buffer = buffer << 6 | alphabet.indexOf(c); bits += 6;
    if (bits >= 8) { bits -= 8; out.push(buffer >>> bits & 255); }
  }
  const key = new Uint8Array(out);
  if (key.length < 24 || key.length > 64 || base64(key) !== text) throw new Error('Invalid signing key.');
  return key;
}
export function validateConfig(value, now = Date.now()) {
  if (!value || ![1, 2].includes(value.version) || value.event !== 'ring.message') throw new Error('Invalid pairing format.');
  const match = typeof value.url === 'string' && value.url.match(/^https:\/\/([a-z0-9.-]+)(?::443)?(\/[^\s\\#]*)$/);
  if (!match || !/^(?:[a-z0-9-]+\.)*(?:openai\.com|chatgpt\.com)$/.test(match[1])) {
    throw new Error('Pairing must use an OpenAI HTTPS callback.');
  }
  if (!/^sub_[a-zA-Z0-9_-]{1,100}$/.test(value.id) || !/^[a-f0-9]{32}$/.test(value.device_id)) throw new Error('Invalid pairing identity.');
  decodeKey(value.secret);
  if (value.version === 2 ? value.expires !== null : (!Number.isFinite(value.expires) || value.expires <= now || value.expires > now + 3600000)) {
    throw new Error('Pairing expired or exceeds the one-hour test limit.');
  }
  return { version: value.version, event: value.event, url: value.url, id: value.id,
    device_id: value.device_id, secret: value.secret, expires: value.expires };
}
export function eventBody(text, config, sequence, now = Date.now()) {
  if (typeof text !== 'string' || !text.trim() || text.length > 8000) throw new Error('Text must contain 1–8000 characters.');
  if (!Number.isSafeInteger(sequence) || sequence < 1 || (config.version === 1 && sequence > 10)) throw new Error('The message sequence limit was reached.');
  const id = 'evt_' + config.device_id + '_' + sequence;
  const stamp = new Date(now).toISOString();
  return JSON.stringify({ eventId: id, name: 'ring.message', timestamp: stamp,
    data: { text: MESSAGE_PREAMBLE + text, receipt_id: id, recorded_at: stamp, received_at: stamp,
      is_test: false, trigger: 'pebble-plugin' }, cursor: null });
}
export function signedRequest(config, body, now = Date.now()) {
  validateConfig(config, now);
  if (utf8(body).length > 262144) throw new Error('Message exceeds the event size limit.');
  const event = JSON.parse(body);
  const stamp = String(Math.floor(now / 1000));
  const signature = base64(hmac(sha256, decodeKey(config.secret), utf8(event.eventId + '.' + stamp + '.' + body)));
  return { method: 'POST', redirect: 'error', body,
    headers: { 'Content-Type': 'application/json', 'webhook-id': event.eventId,
      'webhook-timestamp': stamp, 'webhook-signature': 'v1,' + signature,
      'X-MCP-Subscription-Id': config.id } };
}
