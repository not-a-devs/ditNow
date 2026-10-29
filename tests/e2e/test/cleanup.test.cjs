'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { inspect } = require('node:util');
const { createApiClient } = require('../src/api-client.cjs');
const { MAX_CLEANUP_REQUESTS, MAX_RESOURCES, ResourceRegistry, cleanupResources, newRunMarker } = require('../src/resources.cjs');
const { OPPORTUNITY_ID, createFakeApi } = require('./fixtures/fake-api.cjs');

const MARKER = 'E2EP0-deadbeef';
const api = (fake) => createApiClient({ apiUrl: 'http://127.0.0.1:8000/api/v1', fetchImpl: fake.fetchImpl, timeoutMs: 1000 });

test('marker is unique per run and registry exposes counts only', () => {
  assert.match(newRunMarker(), /^E2EP0-[0-9a-f]{8}$/);
  assert.notEqual(newRunMarker(), newRunMarker());
  const seen = [];
  const registry = new ResourceRegistry({ onSecret: (id) => seen.push(id) });
  registry.register('anonymous_post', 'post-secret-id', { revision: 1 });
  assert.deepEqual(seen, ['post-secret-id']);
  assert.ok(!JSON.stringify(registry).includes('post-secret-id'));
  assert.ok(!inspect(registry).includes('post-secret-id'));
  assert.throws(() => registry.register('users', 'x'), TypeError);
  for (let i = 1; i < MAX_RESOURCES; i += 1) registry.register('recruitment', `r${i}`);
  assert.throws(() => registry.register('recruitment', 'overflow'), RangeError);
});

test('cleanup deletes only own marker resources and leaves closed recruitments as residue', async () => {
  const fake = createFakeApi({
    posts: [
      { id: 'p-mine', title: `${MARKER} 익명 390`, is_mine: true, revision: 2 },
      { id: 'p-unmarked-mine', title: '사람이 쓴 글', is_mine: true, revision: 1 },
      { id: 'p-other', title: `${MARKER} 남의 글`, is_mine: false, revision: 1 },
      { id: 'p-discovered', title: `${MARKER} 익명 1280`, is_mine: true, revision: 1 },
    ],
    recruitments: [
      { id: 'r-open', title: `${MARKER} 모집`, is_mine: true, revision: 3, status: 'open' },
      { id: 'r-closed', title: `${MARKER} 마감표본`, is_mine: true, revision: 2, status: 'closed' },
    ],
    saved: [{ opportunity_id: OPPORTUNITY_ID, revision: 4, checks: [] }],
  });
  const registry = new ResourceRegistry();
  registry.register('anonymous_post', 'p-mine');
  registry.register('anonymous_post', 'p-unmarked-mine'); // registered by mistake: must be refused
  registry.register('anonymous_post', 'p-other');
  registry.register('anonymous_post', 'p-gone');
  registry.register('recruitment', 'r-open');
  registry.register('recruitment', 'r-closed');
  registry.register('saved_opportunity', OPPORTUNITY_ID);

  const summary = await cleanupResources({ api: api(fake), token: 'tok', registry, marker: MARKER });
  assert.deepEqual(summary, {
    attempted: 8,
    deleted: 4,
    already_gone: 1,
    skipped_not_owned_marker: 2,
    residual_closed: 1,
    failed: 0,
    budget_exhausted: false,
  });
  assert.deepEqual([...fake.state.posts.keys()].sort(), ['p-other', 'p-unmarked-mine']);
  assert.deepEqual([...fake.state.recruitments.keys()], ['r-closed']);
  assert.equal(fake.state.saved.length, 0);
  const deletes = fake.calls.filter((c) => c.method === 'DELETE').map((c) => c.path);
  assert.ok(deletes.every((p) => !/p-other|p-unmarked-mine|r-closed/.test(p)));
  assert.ok(deletes.some((p) => p.startsWith('/anonymous-posts/p-mine?revision=2')) || deletes.includes('/anonymous-posts/p-mine'));
  // Never list-wide or bulk deletes.
  assert.ok(deletes.every((p) => /^\/(anonymous-posts|recruitments|me\/saved-opportunities)\/[^/?]+$/.test(p)));
});

test('cleanup is bounded and reports failures instead of looping', async () => {
  const posts = Array.from({ length: 15 }, (_, i) => ({ id: `p${i}`, title: `${MARKER} ${i}`, is_mine: true, revision: 1 }));
  const fake = createFakeApi({ posts, failDeletes: true });
  const registry = new ResourceRegistry();
  const summary = await cleanupResources({ api: api(fake), token: 'tok', registry, marker: MARKER });
  assert.ok(fake.calls.length <= MAX_CLEANUP_REQUESTS);
  assert.equal(summary.budget_exhausted, true);
  assert.equal(summary.deleted, 0);
  assert.equal(summary.failed, 15);
});

test('without a token cleanup makes no requests and counts pending as failed', async () => {
  const fake = createFakeApi();
  const registry = new ResourceRegistry();
  registry.register('anonymous_post', 'p1');
  const summary = await cleanupResources({ api: api(fake), token: null, registry, marker: MARKER });
  assert.equal(fake.calls.length, 0);
  assert.equal(summary.failed, 1);
});
