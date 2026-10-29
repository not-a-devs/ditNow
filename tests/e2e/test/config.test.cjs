'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { inspect } = require('node:util');
const { loadConfig } = require('../src/config.cjs');
const { FIXTURE_PASSWORD, baseEnv } = require('./fixtures/fake-api.cjs');

test('without exact opt-in nothing else is read and status is NOT_RUN', () => {
  for (const run of [undefined, '', '0', 'true', 'yes', ' 1']) {
    const env = baseEnv({ P0_E2E_RUN: run });
    const proxy = new Proxy(env, {
      get(target, key) {
        assert.equal(key, 'P0_E2E_RUN', `read ${String(key)} before opt-in`);
        return target[key];
      },
    });
    assert.deepEqual(loadConfig(proxy), { status: 'NOT_RUN', reason: 'OPT_IN_MISSING' });
  }
});

test('ready config keeps loopback origins and hides credentials from serialisation', () => {
  const result = loadConfig(baseEnv({ P0_E2E_API_URL: 'http://localhost:8000/api/v1/' }));
  assert.equal(result.status, 'READY');
  const { config } = result;
  assert.equal(config.webUrl, 'http://127.0.0.1:5173');
  assert.equal(config.apiUrl, 'http://localhost:8000/api/v1');
  assert.deepEqual(config.viewports.map((v) => v.width), [390, 1280]);
  assert.equal(config.screenshots, false);
  assert.equal(config.includeClose, false);
  assert.equal(config.studentA.password, FIXTURE_PASSWORD);
  for (const dump of [JSON.stringify(config), inspect(config, { depth: 5 }), JSON.stringify({ ...config.studentA })]) {
    assert.ok(!dump.includes(FIXTURE_PASSWORD));
    assert.ok(!dump.includes('demoA0001'));
  }
});

test('remote, credentialed or malformed URLs are refused', () => {
  const cases = [
    ['P0_E2E_WEB_URL', 'https://ditnow.example.com', 'NOT_LOOPBACK'],
    ['P0_E2E_API_URL', 'http://10.0.0.5:8000/api/v1', 'NOT_LOOPBACK'],
    ['P0_E2E_API_URL', 'http://user:pw@127.0.0.1:8000/api/v1', 'INVALID_URL'],
    ['P0_E2E_WEB_URL', 'http://127.0.0.1:5173/?next=x', 'INVALID_URL'],
    ['P0_E2E_WEB_URL', 'file:///C:/x', 'INVALID_URL'],
    ['P0_E2E_WEB_URL', 'not a url', 'INVALID_URL'],
  ];
  for (const [variable, value, code] of cases) {
    const result = loadConfig(baseEnv({ [variable]: value }));
    assert.equal(result.status, 'INVALID');
    assert.deepEqual(result.problems, [{ variable, code }]);
  }
});

test('invalid config reports variable names only, never values', () => {
  const result = loadConfig(
    baseEnv({
      P0_E2E_STUDENT_A_PASSWORD: '',
      P0_E2E_STUDENT_B_ID: 'demoA0001',
      P0_E2E_OPPORTUNITY_ID: 'not-a-uuid',
      P0_E2E_TIMEOUT_MS: '5',
    }),
  );
  assert.equal(result.status, 'INVALID');
  assert.deepEqual(result.problems, [
    { variable: 'P0_E2E_STUDENT_A_PASSWORD', code: 'MISSING' },
    { variable: 'P0_E2E_OPPORTUNITY_ID', code: 'INVALID_FORMAT' },
    { variable: 'P0_E2E_TIMEOUT_MS', code: 'OUT_OF_RANGE' },
  ]);
  const same = loadConfig(baseEnv({ P0_E2E_STUDENT_B_ID: 'demoA0001' }));
  assert.deepEqual(same.problems, [{ variable: 'P0_E2E_STUDENT_B_ID', code: 'SAME_AS_STUDENT_A' }]);
  assert.ok(!JSON.stringify(result).includes('not-a-uuid'));
});

test('screenshots and close sample stay off unless exactly "1"', () => {
  assert.equal(loadConfig(baseEnv({ P0_E2E_SCREENSHOTS: 'true' })).config.screenshots, false);
  const on = loadConfig(baseEnv({ P0_E2E_SCREENSHOTS: '1', P0_E2E_INCLUDE_CLOSE: '1' })).config;
  assert.equal(on.screenshots, true);
  assert.equal(on.includeClose, true);
});
