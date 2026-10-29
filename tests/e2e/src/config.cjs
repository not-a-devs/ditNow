'use strict';

const ENV = Object.freeze({
  run: 'P0_E2E_RUN',
  webUrl: 'P0_E2E_WEB_URL',
  apiUrl: 'P0_E2E_API_URL',
  studentAId: 'P0_E2E_STUDENT_A_ID',
  studentAPassword: 'P0_E2E_STUDENT_A_PASSWORD',
  studentBId: 'P0_E2E_STUDENT_B_ID',
  studentBPassword: 'P0_E2E_STUDENT_B_PASSWORD',
  opportunityId: 'P0_E2E_OPPORTUNITY_ID',
  includeClose: 'P0_E2E_INCLUDE_CLOSE',
  screenshots: 'P0_E2E_SCREENSHOTS',
  timeoutMs: 'P0_E2E_TIMEOUT_MS',
});

// Same loopback set the web login uses to allow plain HTTP; anything else is refused so the
// harness can never be pointed at a remote/deployed environment.
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STUDENT_ID = /^[A-Za-z0-9_-]{1,32}$/;
const CONTROL = /[\u0000-\u001f\u007f]/;
const VIEWPORTS = Object.freeze([
  Object.freeze({ width: 390, height: 844 }),
  Object.freeze({ width: 1280, height: 800 }),
]);

/** Holds one DEMO credential. Values never appear in JSON.stringify, util.inspect or spreads. */
class Credential {
  #studentId;
  #password;

  constructor(studentId, password) {
    this.#studentId = studentId;
    this.#password = password;
  }

  get studentId() {
    return this.#studentId;
  }

  get password() {
    return this.#password;
  }

  toJSON() {
    return '[credential]';
  }

  [Symbol.for('nodejs.util.inspect.custom')]() {
    return '[credential]';
  }
}

function loopbackUrl(raw, { keepPath }) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    return { problem: 'INVALID_URL' };
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return { problem: 'INVALID_URL' };
  if (!LOOPBACK.has(url.hostname)) return { problem: 'NOT_LOOPBACK' };
  if (url.username || url.password || url.search || url.hash) return { problem: 'INVALID_URL' };
  const path = keepPath ? url.pathname.replace(/\/+$/, '') : '';
  return { value: `${url.origin}${path}` };
}

/**
 * Returns one of:
 *  - `{ status: 'NOT_RUN', reason: 'OPT_IN_MISSING' }` (default; nothing else is read)
 *  - `{ status: 'INVALID', problems: [{ variable, code }] }` (names only, never values)
 *  - `{ status: 'READY', config }`
 */
function loadConfig(env) {
  if (env[ENV.run] !== '1') return { status: 'NOT_RUN', reason: 'OPT_IN_MISSING' };
  const problems = [];
  const need = (key) => {
    const value = env[ENV[key]];
    if (typeof value !== 'string' || value.length === 0) {
      problems.push({ variable: ENV[key], code: 'MISSING' });
      return null;
    }
    return value;
  };
  const url = (key, keepPath) => {
    const raw = need(key);
    if (raw === null) return null;
    const result = loopbackUrl(raw, { keepPath });
    if (result.problem) problems.push({ variable: ENV[key], code: result.problem });
    return result.value ?? null;
  };
  const credential = (idKey, passwordKey) => {
    const id = need(idKey);
    const password = need(passwordKey);
    if (id !== null && !STUDENT_ID.test(id)) problems.push({ variable: ENV[idKey], code: 'INVALID_FORMAT' });
    if (password !== null && (password.length > 128 || CONTROL.test(password))) {
      problems.push({ variable: ENV[passwordKey], code: 'INVALID_FORMAT' });
    }
    return id !== null && password !== null ? new Credential(id, password) : null;
  };

  const webUrl = url('webUrl', false);
  const apiUrl = url('apiUrl', true);
  const studentA = credential('studentAId', 'studentAPassword');
  const studentB = credential('studentBId', 'studentBPassword');
  if (studentA && studentB && studentA.studentId === studentB.studentId) {
    problems.push({ variable: ENV.studentBId, code: 'SAME_AS_STUDENT_A' });
  }
  const opportunityId = need('opportunityId');
  if (opportunityId !== null && !UUID.test(opportunityId)) {
    problems.push({ variable: ENV.opportunityId, code: 'INVALID_FORMAT' });
  }
  let timeoutMs = 10_000;
  if (env[ENV.timeoutMs] !== undefined) {
    timeoutMs = Number(env[ENV.timeoutMs]);
    if (!Number.isInteger(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 60_000) {
      problems.push({ variable: ENV.timeoutMs, code: 'OUT_OF_RANGE' });
    }
  }
  if (problems.length) return { status: 'INVALID', problems };

  return {
    status: 'READY',
    config: Object.freeze({
      webUrl,
      apiUrl,
      studentA,
      studentB,
      opportunityId: opportunityId.toLowerCase(),
      includeClose: env[ENV.includeClose] === '1',
      screenshots: env[ENV.screenshots] === '1',
      timeoutMs,
      viewports: VIEWPORTS,
    }),
  };
}

module.exports = { ENV, LOOPBACK, VIEWPORTS, Credential, loadConfig };
