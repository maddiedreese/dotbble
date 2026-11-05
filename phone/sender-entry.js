import { validateConfig, eventBody, signedRequest } from './core.js';

const STORE = 'ring_dot_direct_test_v1';
const TRACE_STORE = 'ring_dot_direct_trace_v1';
function traceEntries() {
  try { const value = JSON.parse(localStorage.getItem(TRACE_STORE) || '[]'); return Array.isArray(value) ? value : []; }
  catch (_) { return []; }
}
// Metadata only: never record transcripts, callback URLs, credentials, or exception text.
function trace(stage, httpStatus) {
  try {
    const entries = traceEntries();
    const entry = { at: new Date().toISOString(), stage };
    if (Number.isInteger(httpStatus)) entry.httpStatus = httpStatus;
    entries.push(entry);
    localStorage.setItem(TRACE_STORE, JSON.stringify(entries.slice(-40)));
  } catch (_) { /* Diagnostics must not prevent delivery. */ }
}
function read() {
  const raw = localStorage.getItem(STORE);
  if (raw === null || raw === undefined) return { config: null, count: 0, pending: null, last: null };
  return JSON.parse(raw);
}
function save(state) { localStorage.setItem(STORE, JSON.stringify(state)); }
function status() {
  const state = read();
  let ready = false;
  try { const config = validateConfig(state.config); ready = Number.isSafeInteger(state.count) && state.count >= 0 && state.count < (config.version === 1 ? 10 : Number.MAX_SAFE_INTEGER); } catch (_) {}
  return { version: '1.0.0', instructionMode: 'per-message', ready, count: state.count, pending: !!state.pending, last: state.last,
    pairingMode: !state.config ? 'unpaired' : state.config.version === 2 ? 'non-expiring' : 'one-hour-test',
    expires: state.config && state.config.expires !== null ? new Date(state.config.expires).toISOString() : null, diagnostics: traceEntries() };
}
async function deliver(state) {
  const config = validateConfig(state.config);
  const pending = state.pending;
  if (!pending) throw new Error('No pending message.');
  if (Date.now() - pending.createdAt > 300000) throw new Error('Pending message is too old. Disconnect to discard it.');
  if (pending.attempts >= 3) throw new Error('Three delivery attempts used. Disconnect to discard this message.');
  pending.attempts++;
  save(state);
  let response;
  trace('signing-start');
  const request = signedRequest(config, pending.body);
  trace('request-start');
  try { response = await fetch(config.url, request); }
  catch (_) { trace('transport-error'); throw new Error('Delivery unconfirmed. Check your dot before using Retry pending.'); }
  trace('http-response', response.status);
  const latest = read();
  if (!latest.config || latest.config.device_id !== config.device_id) throw new Error('Disconnected while delivery was in progress. Check your dot.');
  if (response.status >= 200 && response.status < 300) {
    latest.last = { id: pending.id, status: response.status, acceptedAt: new Date().toISOString() };
    latest.pending = null;
    save(latest);
    return pending.id;
  }
  if (response.status === 410 || response.status === 413 || (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429)) {
    latest.last = { id: pending.id, status: response.status };
    latest.pending = null;
    if (response.status === 410) latest.config = null;
    save(latest);
  }
  throw new Error('OpenAI returned HTTP ' + response.status + '. This is not a confirmed dot response.');
}

Pebble.registerSourceHandler(function (request, respond) {
  if (request.category !== 'notes' || ['configured', 'destination'].indexOf(request.item) < 0) {
    respond.error('PLUGIN_UNAVAILABLE', 'Unknown source.'); return;
  }
  let ready = false;
  try { ready = status().ready; } catch (_) {}
  respond.data({ validUntilMs: Date.now() + 1000, instances: [{ instanceId: 'ring-dot-direct-test',
    properties: { name: { shortText: { text: 'Dotbble' } }, configured: { boolean: { value: ready } } } }] });
});
Pebble.registerActionHandler(async function (request, respond) {
  if (request.action !== 'create_note') { respond.error('PLUGIN_UNAVAILABLE', 'Unknown action.'); return; }
  trace('action-start');
  try {
    const state = read();
    validateConfig(state.config);
    if (state.pending) throw new Error('A previous delivery is unconfirmed. Resolve it in plugin settings first.');
    const body = eventBody(request.args && request.args.text, state.config, state.count + 1);
    state.count++;
    state.pending = { id: JSON.parse(body).eventId, body, createdAt: Date.now(), attempts: 0 };
    save(state);
    trace('message-queued');
    const id = await deliver(state);
    trace('action-complete');
    respond.ok({ text: 'OpenAI accepted ' + id + '. Check your dot for its response.' });
  } catch (error) { trace('action-error'); respond.error('UNKNOWN', error.message || 'Could not deliver the message.'); }
});
Pebble.registerConfigHandler(async function (message, respond) {
  try {
    if (message.type === 'pair') {
      const state = read();
      if (state.config || state.pending) throw new Error('Disconnect the previous connection before pairing again.');
      state.config = validateConfig(JSON.parse(message.pairing));
      state.count = 0; state.last = null;
      save(state);
      Pebble.refreshSources(['notes/configured', 'notes/destination']);
    } else if (message.type === 'disconnect') {
      localStorage.removeItem(STORE);
      localStorage.removeItem(TRACE_STORE);
      Pebble.refreshSources(['notes/configured', 'notes/destination']);
    } else if (message.type === 'retry') {
      await deliver(read());
    } else if (message.type !== 'status') throw new Error('Unknown settings action.');
    respond(status());
  } catch (error) { respond({ error: error.message || 'Could not complete settings action.' }); }
});
