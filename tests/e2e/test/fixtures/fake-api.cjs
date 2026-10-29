'use strict';

// Offline fixture for harness self-tests only. It is NOT the product API and its responses are
// never evidence of browser E2E behaviour; it exists to drive config/redaction/cleanup paths.
const FIXTURE_PASSWORD = 'fixture-pw-Zq81';
const FIXTURE_TOKEN = 'fixtureTokenAAAA.bbbb.cccc';
const OPPORTUNITY_ID = '0b9c1f3e-6a51-4c2e-9d0a-111122223333';

function baseEnv(overrides = {}) {
  return {
    P0_E2E_RUN: '1',
    P0_E2E_WEB_URL: 'http://127.0.0.1:5173',
    P0_E2E_API_URL: 'http://127.0.0.1:8000/api/v1',
    P0_E2E_STUDENT_A_ID: 'demoA0001',
    P0_E2E_STUDENT_A_PASSWORD: FIXTURE_PASSWORD,
    P0_E2E_STUDENT_B_ID: 'demoB0002',
    P0_E2E_STUDENT_B_PASSWORD: `${FIXTURE_PASSWORD}-b`,
    P0_E2E_OPPORTUNITY_ID: OPPORTUNITY_ID,
    ...overrides,
  };
}

function json(status, data) {
  return {
    status,
    headers: { get: (name) => (name.toLowerCase() === 'cache-control' ? 'private, no-store' : null) },
    json: async () => (data === undefined ? {} : { success: status < 400, data }),
  };
}

/** In-memory fetch replacement. `posts`/`recruitments` rows: {id,title,is_mine,revision,status}. */
function createFakeApi({ recordSource = 'DEMO', posts = [], recruitments = [], saved = [], failDeletes = false } = {}) {
  const calls = [];
  const state = { posts: new Map(posts.map((p) => [p.id, { ...p }])), recruitments: new Map(recruitments.map((r) => [r.id, { ...r }])), saved: [...saved], revoked: new Set() };
  async function fetchImpl(url, init = {}) {
    const u = new URL(url);
    const p = u.pathname.replace(/^\/api\/v1/, '');
    const method = init.method ?? 'GET';
    calls.push({ method, path: p });
    if (p === '/auth/login' && method === 'POST') {
      const body = JSON.parse(init.body);
      const who = body.student_id.startsWith('demoA') ? 'A' : 'B';
      return json(200, { token: `${FIXTURE_TOKEN}${who}`, token_type: 'Bearer', student_id: body.student_id, name: `가상학생${who}`, record_source: recordSource });
    }
    if (p === '/auth/me') {
      if (state.revoked.has(init.headers.Authorization)) return json(401);
      const who = init.headers.Authorization.endsWith('A') ? 'A' : 'B';
      return json(200, { user_id: `10000000-0000-4000-8000-00000000000${who === 'A' ? '1' : '2'}`, display_name: `가상학생${who}`, record_source: recordSource, department_id: '20000000-0000-4000-8000-000000000001', department_code: 'CS', academic_year: 2, community_access: true });
    }
    if (p === '/auth/logout') { state.revoked.add(init.headers.Authorization); return json(200, { status: 'ok' }); }
    if (p === `/opportunities/${OPPORTUNITY_ID}`) return json(200, { id: OPPORTUNITY_ID, title: '가상 장학 공고', source_kind: 'DEMO' });
    if (p === '/me/saved-opportunities' && method === 'GET') return json(200, { items: state.saved });
    if (p.startsWith('/me/saved-opportunities/') && method === 'DELETE') {
      if (failDeletes) return json(409);
      state.saved = state.saved.filter((s) => s.opportunity_id !== decodeURIComponent(p.split('/')[3]));
      return json(200, { deleted: true });
    }
    for (const [prefix, table] of [['/anonymous-posts', state.posts], ['/recruitments', state.recruitments]]) {
      if (p === prefix && method === 'GET') return json(200, { items: [...table.values()] });
      if (p.startsWith(`${prefix}/`)) {
        const id = decodeURIComponent(p.slice(prefix.length + 1));
        const row = table.get(id);
        if (!row) return json(404);
        if (method === 'GET') return json(200, row);
        if (method === 'DELETE') {
          if (failDeletes) return json(409);
          table.delete(id);
          return json(200, { id, deleted: true });
        }
      }
    }
    return json(404);
  }
  return { fetchImpl, calls, state };
}

module.exports = { FIXTURE_PASSWORD, FIXTURE_TOKEN, OPPORTUNITY_ID, baseEnv, createFakeApi };
