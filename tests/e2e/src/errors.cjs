'use strict';

// Static failure codes. Reports carry only these codes plus details written by this harness;
// raw error messages/stacks (which can echo fill values, response bodies or tokens) are dropped.
const CODES = Object.freeze([
  'TIMEOUT',
  'SELECTOR_MISSING',
  'HTTP_STATUS',
  'ASSERTION',
  'PRECONDITION',
  'NOT_DEMO',
  'NETWORK',
  'BROWSER_LAUNCH',
  'PLAYWRIGHT_MISSING',
  'DEPENDENCY_FAILED',
  'UNEXPECTED',
]);

class E2EError extends Error {
  constructor(code, detail) {
    super(detail);
    this.name = 'E2EError';
    this.code = CODES.includes(code) ? code : 'UNEXPECTED';
    this.detail = String(detail ?? '');
  }
}

function safeName(error) {
  const name = error && typeof error.name === 'string' ? error.name : '';
  return /^[A-Za-z]{1,40}$/.test(name) ? name : 'Error';
}

/** Converts any thrown value into `{code, detail}` without reading its message or stack. */
function toSafeFailure(error, redactor) {
  if (error instanceof E2EError) return { code: error.code, detail: redactor.mask(error.detail) };
  if (safeName(error) === 'TimeoutError') return { code: 'TIMEOUT', detail: 'step timed out' };
  return { code: 'UNEXPECTED', detail: `unhandled ${safeName(error)}` };
}

module.exports = { CODES, E2EError, safeName, toSafeFailure };
