'use strict';

const { E2EError, safeName } = require('./errors.cjs');
const S = require('./selectors.cjs');

/** Runs one UI step; Playwright errors become static codes carrying only this label. */
async function step(label, fn) {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof E2EError) throw error;
    if (safeName(error) === 'TimeoutError') throw new E2EError('SELECTOR_MISSING', label);
    throw new E2EError('UNEXPECTED', `${label} (${safeName(error)})`);
  }
}

function apiPath(ctx, rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }
  const base = ctx.apiBase;
  if (url.origin !== base.origin || !(url.pathname === base.pathname || url.pathname.startsWith(base.pathname + '/'))) return null;
  return url.pathname.slice(base.pathname.length) || '/';
}

function responseWaiter(ctx, { method, path, status = null }) {
  const waiting = ctx.page.waitForResponse(
    (res) => {
      if (res.request().method() !== method) return false;
      const p = apiPath(ctx, res.url());
      return p !== null && path.test(p) && (status === null || res.status() === status);
    },
    { timeout: ctx.timeoutMs },
  );
  waiting.catch(() => {});
  return waiting;
}

/** Performs `action` and requires the browser itself to receive the API response. */
async function withApiResponse(ctx, spec, action) {
  const waiting = responseWaiter(ctx, spec.status === undefined ? spec : { ...spec, status: null });
  await step(`${spec.label} action`, action);
  let res;
  try {
    res = await waiting;
  } catch {
    throw new E2EError('TIMEOUT', `${spec.label}: browser never received ${spec.method} response`);
  }
  const allowed = [].concat(spec.status ?? 200);
  if (!allowed.includes(res.status())) {
    throw new E2EError('HTTP_STATUS', `${spec.label}: expected ${allowed.join('|')} got ${res.status()}`);
  }
  return res;
}

async function readData(res) {
  try {
    const body = await res.json();
    return body && typeof body === 'object' ? body.data ?? null : null;
  } catch {
    return null;
  }
}

function heading(ctx, key) {
  const selector = key === 'opportunities' ? S.OPP.savedSection : key === 'community' ? S.ANON.section : S.RECRUIT.section;
  return ctx.page.locator(selector);
}

async function clickTabIfPresent(ctx, key) {
  const tab = ctx.page.getByRole('tab', { name: S.TABS[key] });
  if (S.TABS[key] && (await tab.count()) > 0 && (await tab.first().isVisible())) await tab.first().click();
}

/** In-app navigation via the shared sidebar (opens the mobile menu when collapsed). */
async function navTo(ctx, key, { expectList = true } = {}) {
  const { page } = ctx;
  const target = S.ROUTES[key];
  const onRoute = currentPath(page) === target;
  const listWait = expectList && !onRoute ? responseWaiter(ctx, { method: 'GET', path: S.LIST_API[key], status: 200 }) : null;
  await step(`${S.QUESTIONS.ROUTES} navigate ${key}`, async () => {
    if (!onRoute) {
      const link = page.getByRole('navigation', { name: S.NAV.landmark }).getByRole('link', { name: S.NAV[key] });
      if (!(await link.isVisible())) await page.locator(S.NAV.menuToggle).first().click();
      await link.click();
      await page.waitForURL((url) => url.pathname.replace(/\/$/, '') === target, { timeout: ctx.timeoutMs, waitUntil: 'commit' });
    }
  });
  if (!expectList) return;
  await step(`${S.QUESTIONS.ROUTES} ${key} page`, async () => {
    await clickTabIfPresent(ctx, key);
    await heading(ctx, key).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
  });
  if (listWait) {
    try {
      await listWait;
    } catch {
      throw new E2EError('TIMEOUT', `${key}: list GET 200 not received after navigation`);
    }
  }
}

/** Fills the login form on the current page; requires POST /auth/login and GET /auth/me. */
async function submitLogin(ctx, credential, identity) {
  const { page } = ctx;
  assertLoginLocation(ctx);
  const meWait = responseWaiter(ctx, { method: 'GET', path: /^\/auth\/me$/, status: null });
  await step(`${S.QUESTIONS.LOGIN_ROUTE} login form`, async () => {
    await page.getByLabel(S.LOGIN.studentId).fill(credential.studentId, { timeout: ctx.timeoutMs });
    assertLoginLocation(ctx);
    await page.getByLabel(S.LOGIN.password, { exact: true }).fill(credential.password, { timeout: ctx.timeoutMs });
  });
  const loginResponse = await withApiResponse(ctx, { label: 'UI POST /auth/login', method: 'POST', path: /^\/auth\/login$/, status: 200 }, () =>
    { assertLoginLocation(ctx); return page.getByRole('button', { name: S.LOGIN.submit }).click(); },
  );
  const login = await readData(loginResponse);
  if (typeof login?.token === 'string' && /^[A-Za-z0-9._~+/-]{8,512}={0,2}$/.test(login.token)) ctx.trackToken(login.token);
  if (!login || login.record_source !== 'DEMO' || login.token_type !== 'Bearer'
    || login.student_id !== credential.studentId || typeof login.token !== 'string'
    || !/^[A-Za-z0-9._~+/-]{8,512}={0,2}$/.test(login.token)) {
    throw new E2EError('ASSERTION', 'UI LoginData contract mismatch');
  }
  let me;
  try {
    me = await meWait;
  } catch {
    throw new E2EError('ASSERTION', `${S.QUESTIONS.SESSION_IDENTITY}: UI did not confirm session via GET /auth/me`);
  }
  if (me.status() !== 200) throw new E2EError('HTTP_STATUS', `UI GET /auth/me: expected 200 got ${me.status()}`);
  const current = await readData(me);
  if (current?.user_id !== identity.user_id || current?.display_name !== identity.display_name || current?.record_source !== 'DEMO') {
    throw new E2EError('ASSERTION', 'UI current identity differs from approved account');
  }
  await step(`${S.QUESTIONS.SESSION_IDENTITY} own session identity shown`, () =>
    page.getByText(identity.display_name, { exact: false }).first().waitFor({ state: 'visible', timeout: ctx.timeoutMs }),
  );
}

function assertLoginLocation(ctx) {
  try {
    const url = new URL(ctx.page.url());
    if (url.origin === new URL(ctx.cfg.webUrl).origin && url.pathname === S.ROUTES.login && !url.search && !url.hash) return;
  } catch { /* Static failure only; no URL or credentials are printed. */ }
  throw new E2EError('PRECONDITION', 'exact local login location required before credential input');
}

async function loginFromStart(ctx, credential, identity) {
  await step(`${S.QUESTIONS.LOGIN_ROUTE} open ${S.ROUTES.login}`, async () => {
    await ctx.page.goto(`${ctx.cfg.webUrl}${S.ROUTES.login}`, { waitUntil: 'domcontentloaded', timeout: ctx.timeoutMs });
    await ctx.page.getByLabel(S.LOGIN.studentId).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
  });
  await submitLogin(ctx, credential, identity);
}

/** Current PR60 contract: reload clears memory; the protected page offers an explicit login button. */
async function openLoginFromGuard(ctx) {
  await step(`${S.QUESTIONS.SIGNED_OUT_GUARD} protected login boundary`, async () => {
    await ctx.page.getByText(S.LOGIN.required, { exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
    await ctx.page.getByRole('button', { name: S.LOGIN.open, exact: true }).click();
    await ctx.page.waitForURL(url => url.pathname === S.ROUTES.login, { timeout: ctx.timeoutMs });
    await ctx.page.getByLabel(S.LOGIN.studentId).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
  });
}

async function reloadAndResume(ctx, key, credential, identity) {
  await step(`reload ${key}`, () => ctx.page.reload({ waitUntil: 'domcontentloaded', timeout: ctx.timeoutMs }));
  await openLoginFromGuard(ctx);
  await submitLogin(ctx, credential, identity);
  await navTo(ctx, key);
  ctx.recordReload('relogin_required');
}

function currentPath(page) {
  return new URL(page.url()).pathname.replace(/\/$/, '');
}

module.exports = { step, apiPath, responseWaiter, withApiResponse, readData, navTo, submitLogin, loginFromStart, reloadAndResume, openLoginFromGuard };
