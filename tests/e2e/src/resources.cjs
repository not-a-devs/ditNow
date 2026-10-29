'use strict';

const { randomBytes } = require('node:crypto');

const KINDS = Object.freeze(['anonymous_post', 'recruitment', 'saved_opportunity']);
const MAX_RESOURCES = 20;
const MAX_CLEANUP_REQUESTS = 40;
const LIST_LIMIT = 50;

function newRunMarker() {
  return `E2EP0-${randomBytes(4).toString('hex')}`;
}

/**
 * Resources created by this run, kept only in process memory. IDs never reach the report:
 * `toJSON()` exposes counts per kind/state.
 */
class ResourceRegistry {
  #items = new Map();
  #onSecret;

  constructor({ onSecret = () => {} } = {}) {
    this.#onSecret = onSecret;
  }

  register(kind, id, { revision = null, viewport = null } = {}) {
    if (!KINDS.includes(kind)) throw new TypeError('unknown resource kind');
    if (typeof id !== 'string' || !id) throw new TypeError('resource id required');
    const key = `${kind}:${id}`;
    if (!this.#items.has(key)) {
      if (this.#items.size >= MAX_RESOURCES) throw new RangeError('resource registry full');
      this.#onSecret(id);
      this.#items.set(key, { kind, id, revision, viewport, state: 'active' });
    } else if (revision !== null) {
      this.#items.get(key).revision = revision;
    }
    return this.#items.get(key);
  }

  has(kind, id) {
    return this.#items.has(`${kind}:${id}`);
  }

  get(kind, id) {
    return this.#items.get(`${kind}:${id}`) ?? null;
  }

  mark(kind, id, state) {
    const item = this.#items.get(`${kind}:${id}`);
    if (item) item.state = state;
  }

  pending() {
    return [...this.#items.values()].filter((item) => item.state === 'active');
  }

  counts() {
    const out = {};
    for (const item of this.#items.values()) {
      const bucket = (out[item.kind] ??= {});
      bucket[item.state] = (bucket[item.state] ?? 0) + 1;
    }
    return out;
  }

  toJSON() {
    return this.counts();
  }

  [Symbol.for('nodejs.util.inspect.custom')]() {
    return `ResourceRegistry ${JSON.stringify(this.counts())}`;
  }
}

/**
 * Deletes only resources this run registered (or discovers as `is_mine` + run marker), re-reading
 * each one first. Closed recruitments are left as reported residue because the contract forbids
 * deleting them. Bounded by MAX_CLEANUP_REQUESTS; never issues list-wide or DB-level resets.
 */
async function cleanupResources({ api, token, registry, marker }) {
  const summary = { attempted: 0, deleted: 0, already_gone: 0, skipped_not_owned_marker: 0, residual_closed: 0, failed: 0, budget_exhausted: false };
  if (!token) {
    summary.failed = registry.pending().length;
    return summary;
  }
  let budget = MAX_CLEANUP_REQUESTS;
  const call = async (label, method, path, options) => {
    if (budget <= 0) {
      summary.budget_exhausted = true;
      return null;
    }
    budget -= 1;
    try {
      return await api.request(label, method, path, { token, ...options });
    } catch {
      return null;
    }
  };

  // Discover marker items whose create succeeded but whose ID was never captured.
  for (const [kind, path] of [['anonymous_post', '/anonymous-posts'], ['recruitment', '/recruitments']]) {
    const list = await call(`cleanup list ${kind}`, 'GET', `${path}?limit=${LIST_LIMIT}`);
    for (const item of list?.data?.items ?? []) {
      if (item && item.is_mine === true && typeof item.title === 'string' && item.title.includes(marker)) {
        try {
          registry.register(kind, item.id, { revision: item.revision });
        } catch {
          summary.failed += 1;
        }
      }
    }
  }

  for (const item of registry.pending()) {
    summary.attempted += 1;
    let done = false;
    for (let attempt = 0; attempt < 2 && !done; attempt += 1) {
      done = await cleanupOne(item, { call, registry, marker, summary });
    }
    if (!done) summary.failed += 1;
  }
  return summary;
}

async function cleanupOne(item, { call, registry, marker, summary }) {
  const ref = encodeURIComponent(item.id);
  if (item.kind === 'saved_opportunity') {
    const list = await call('cleanup saved list', 'GET', '/me/saved-opportunities');
    if (!list || list.status !== 200) return false;
    const saved = (list.data?.items ?? []).find((s) => s.opportunity_id === item.id);
    if (!saved) {
      registry.mark(item.kind, item.id, 'gone');
      summary.already_gone += 1;
      return true;
    }
    const res = await call('cleanup saved delete', 'DELETE', `/me/saved-opportunities/${ref}`, {
      headers: { 'If-Match': String(saved.revision) },
    });
    if (res?.status === 200) {
      registry.mark(item.kind, item.id, 'deleted');
      summary.deleted += 1;
      return true;
    }
    return false;
  }

  const path = item.kind === 'anonymous_post' ? '/anonymous-posts' : '/recruitments';
  const current = await call(`cleanup get ${item.kind}`, 'GET', `${path}/${ref}`);
  if (!current) return false;
  if (current.status === 404) {
    registry.mark(item.kind, item.id, 'gone');
    summary.already_gone += 1;
    return true;
  }
  if (current.status !== 200 || !current.data) return false;
  const owned = current.data.is_mine === true && String(current.data.title ?? '').includes(marker);
  if (!owned) {
    registry.mark(item.kind, item.id, 'skipped');
    summary.skipped_not_owned_marker += 1;
    return true;
  }
  if (item.kind === 'recruitment' && current.data.status !== 'open') {
    registry.mark(item.kind, item.id, 'residual');
    summary.residual_closed += 1;
    return true;
  }
  const res = await call(`cleanup delete ${item.kind}`, 'DELETE', `${path}/${ref}?revision=${current.data.revision}`);
  if (res?.status === 200 || res?.status === 404) {
    registry.mark(item.kind, item.id, 'deleted');
    summary.deleted += 1;
    return true;
  }
  return false;
}

module.exports = { KINDS, MAX_CLEANUP_REQUESTS, MAX_RESOURCES, ResourceRegistry, cleanupResources, newRunMarker };
