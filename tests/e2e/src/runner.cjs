'use strict';

const { mkdirSync } = require('node:fs');
const path = require('node:path');
const { createApiClient } = require('./api-client.cjs');
const { loadConfig } = require('./config.cjs');
const { E2EError, toSafeFailure } = require('./errors.cjs');
const { Redactor } = require('./redact.cjs');
const { Report } = require('./report.cjs');
const { ResourceRegistry, cleanupResources, newRunMarker } = require('./resources.cjs');
const { buildStages } = require('./scenario.cjs');
const { apiPath } = require('./ui.cjs');

const ARTIFACTS = path.join(__dirname, '..', '.artifacts');
const PRIVATE_PATH = /^\/(?:auth(?:\/|$)|anonymous-posts(?:\/|$)|recruitments(?:\/|$)|me\/)/;
const GLOBAL_DEPS = ['preflight.demo_accounts', 'browser.launch'];

// Playwright is loaded only on the live path so NOT_RUN and unit tests never need it installed.
async function defaultLaunch() {
  let chromium;
  try {
    ({ chromium } = require('playwright'));
  } catch {
    throw new E2EError('PLAYWRIGHT_MISSING', 'playwright 1.64.1 not installed in tests/e2e (npm ci)');
  }
  try {
    return await chromium.launch({ headless: true });
  } catch {
    throw new E2EError('BROWSER_LAUNCH', 'chromium for playwright 1.64.1 not available (root: npx playwright install chromium)');
  }
}

async function runStage(report, redactor, { id, viewport = null, deps = [] }, fn) {
  const blocked = deps.find((dep) => {
    const status = report.stageStatus(dep, GLOBAL_DEPS.includes(dep) || dep.startsWith('preflight.') ? null : viewport);
    return status !== 'PASS';
  });
  if (blocked) {
    report.addStage({ id, viewport, status: 'SKIPPED', code: 'DEPENDENCY_FAILED', detail: `requires ${blocked}` });
    return false;
  }
  const started = Date.now();
  try {
    await fn();
    report.addStage({ id, viewport, status: 'PASS', durationMs: Date.now() - started });
    return true;
  } catch (error) {
    const failure = toSafeFailure(error, redactor);
    report.addStage({ id, viewport, status: 'FAIL', ...failure, durationMs: Date.now() - started });
    return false;
  }
}

async function openInstrumentedPage(browser, cfg, viewport, obs) {
  const context = await browser.newContext({
    viewport,
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
    serviceWorkers: 'block',
    acceptDownloads: false,
  });
  // HTTP resources never follow redirects: route.continue alone cannot police redirect hops.
  const allowed = new Set([new URL(cfg.webUrl).origin, new URL(cfg.apiUrl).origin]);
  await context.route('**/*', async (route) => {
    let origin = null;
    try {
      origin = new URL(route.request().url()).origin;
    } catch {
      origin = null;
    }
    if (!allowed.has(origin)) {
      obs.blocked_external_requests += 1;
      return route.abort('blockedbyclient');
    }
    let response;
    try {
      response = await route.fetch({ maxRedirects: 0, maxRetries: 0, timeout: cfg.timeoutMs });
      if (response.status() >= 300 && response.status() < 400) {
        obs.blocked_redirects += 1;
        return await route.abort('blockedbyclient');
      }
      return await route.fulfill({ response });
    } catch {
      obs.blocked_requests += 1;
      await route.abort('failed').catch(() => {});
    } finally {
      if (response) await response.dispose().catch(() => {});
    }
  });
  const page = await context.newPage();
  page.setDefaultTimeout(cfg.timeoutMs);
  page.on('console', (message) => {
    if (message.type() === 'error') obs.console_errors += 1;
  });
  page.on('pageerror', () => {
    obs.page_errors += 1;
  });
  const apiBase = new URL(cfg.apiUrl);
  page.on('response', (res) => {
    const p = apiPath({ apiBase }, res.url());
    if (p && PRIVATE_PATH.test(p) && !/no-store/i.test(res.headers()['cache-control'] ?? '')) {
      obs.private_responses_without_no_store += 1;
    }
  });
  return { context, page };
}

async function maybeScreenshot(cfg, page, viewport, stageId) {
  if (!cfg.screenshots || !page) return;
  try {
    mkdirSync(ARTIFACTS, { recursive: true });
    await page.screenshot({
      path: path.join(ARTIFACTS, `${viewport}-${stageId}.png`),
      mask: [page.locator('input[type="password"]')],
    });
  } catch {
    // Screenshots are optional evidence; never fail or log on them.
  }
}

async function preflightAccounts(api, accounts, redactor, trackToken) {
  for (const label of ['A', 'B']) {
    const account = accounts[label];
    const login = await api.login(account.credential, `student ${label}`);
    account.token = login.token;
    trackToken(login.token);
    account.identity = await api.me(login.token, `student ${label}`);
    redactor.add(account.identity.user_id);
    redactor.add(account.identity.display_name);
  }
  if (accounts.A.identity.user_id === accounts.B.identity.user_id) {
    throw new E2EError('PRECONDITION', 'students A and B resolve to the same user');
  }
}

async function preflightOpportunity(api, accounts, opportunityId, opportunity) {
  const ref = encodeURIComponent(opportunityId);
  const { data } = await api.expect('DEMO opportunity public GET', 'GET', `/opportunities/${ref}`, 200);
  if (!data || data.source_kind !== 'DEMO' || data.id !== opportunityId || typeof data.title !== 'string' || !data.title.trim()) {
    throw new E2EError('ASSERTION', 'DEMO opportunity detail shape mismatch');
  }
  opportunity.id = opportunityId;
  opportunity.title = data.title;
  const savedBy = async (label) => {
    const res = await api.expect(`student ${label} saved precheck`, 'GET', '/me/saved-opportunities', 200, { token: accounts[label].token });
    return (res.data?.items ?? []).some((s) => s.opportunity_id === opportunityId);
  };
  if (await savedBy('A')) {
    throw new E2EError('PRECONDITION', 'student A already saved the DEMO opportunity; harness will not touch pre-existing rows');
  }
  accounts.B.hadOpportunitySaved = await savedBy('B');
}

/**
 * Entry point. Without `P0_E2E_RUN=1` nothing is launched or fetched and the report is NOT_RUN.
 * `launchBrowser`, `fetchImpl` and `stagesFactory` are injectable for offline harness tests only.
 */
async function runP0BrowserE2E({ env = process.env, fetchImpl = globalThis.fetch, launchBrowser = defaultLaunch, stagesFactory = buildStages, mode = 'live' } = {}) {
  const redactor = new Redactor();
  const report = new Report({ redactor, mode });
  const loaded = loadConfig(env);
  if (loaded.status === 'NOT_RUN') {
    report.setReason(loaded.reason);
    return { exitCode: 0, report };
  }
  if (loaded.status === 'INVALID') {
    report.setReason('CONFIG_INVALID', loaded.problems);
    return { exitCode: 2, report };
  }

  const cfg = loaded.config;
  for (const credential of [cfg.studentA, cfg.studentB]) {
    redactor.add(credential.studentId);
    redactor.add(credential.password);
  }
  report.setOptions({
    web: 'loopback',
    api: 'loopback',
    viewports: cfg.viewports.map((v) => v.width),
    include_close: cfg.includeClose,
    screenshots: cfg.screenshots,
  });

  const tokens = new Set();
  const trackToken = token => {
    if (tokens.size >= 100) throw new E2EError('PRECONDITION', 'session cleanup budget exceeded');
    tokens.add(token); redactor.add(token);
  };
  const marker = newRunMarker();
  const registry = new ResourceRegistry({ onSecret: (id) => redactor.add(id) });
  const api = createApiClient({ apiUrl: cfg.apiUrl, fetchImpl, timeoutMs: cfg.timeoutMs, onToken: trackToken });
  const accounts = { A: { credential: cfg.studentA, token: null, identity: null }, B: { credential: cfg.studentB, token: null, identity: null, hadOpportunitySaved: true } };
  const opportunity = { id: null, title: null };
  let browser = null;
  const contexts = [];

  try {
    await runStage(report, redactor, { id: 'preflight.demo_accounts' }, () => preflightAccounts(api, accounts, redactor, trackToken));
    await runStage(report, redactor, { id: 'preflight.opportunity', deps: ['preflight.demo_accounts'] }, () =>
      preflightOpportunity(api, accounts, cfg.opportunityId, opportunity),
    );
    await runStage(report, redactor, { id: 'browser.launch', deps: ['preflight.demo_accounts'] }, async () => {
      browser = await launchBrowser();
    });

    const stages = stagesFactory({ includeClose: cfg.includeClose });
    for (const viewport of cfg.viewports) {
      const vp = viewport.width;
      const obs = { console_errors: 0, page_errors: 0, blocked_external_requests: 0, blocked_redirects: 0, blocked_requests: 0, private_responses_without_no_store: 0, session_after_reload: [] };
      let main = null;
      if (browser) {
        try {
          main = await openInstrumentedPage(browser, cfg, viewport, obs);
          contexts.push(main.context);
        } catch {
          main = null;
        }
      }
      const base = { cfg, trackToken, apiBase: new URL(cfg.apiUrl), timeoutMs: cfg.timeoutMs, recordReload: (outcome) => obs.session_after_reload.push(outcome) };
      const ctx = {
        ...base,
        page: main?.page ?? null,
        vp,
        marker,
        api,
        registry,
        accounts,
        opportunity,
        state: {},
        async newPeer() {
          const peer = await openInstrumentedPage(browser, cfg, viewport, obs);
          contexts.push(peer.context);
          return { ...base, page: peer.page };
        },
      };
      for (const stage of stages) {
        const deps = [...GLOBAL_DEPS, ...stage.deps];
        if (/^(opportunity|isolation)\./.test(stage.id)) deps.push('preflight.opportunity');
        await runStage(report, redactor, { id: stage.id, viewport: vp, deps }, async () => {
          if (!ctx.page) throw new E2EError('BROWSER_LAUNCH', 'browser context unavailable');
          await stage.run(ctx);
        });
        await maybeScreenshot(cfg, ctx.page, vp, stage.id);
      }
      report.observe(vp, 'console_errors', obs.console_errors);
      report.observe(vp, 'page_errors', obs.page_errors);
      report.observe(vp, 'blocked_external_requests', obs.blocked_external_requests);
      report.observe(vp, 'blocked_redirects', obs.blocked_redirects);
      report.observe(vp, 'blocked_requests', obs.blocked_requests);
      report.observe(vp, 'private_responses_without_no_store', obs.private_responses_without_no_store);
      report.observe(vp, 'session_after_reload', [...new Set(obs.session_after_reload)]);
    }
  } finally {
    let summary = { failed: 1, cleanup_exception: true };
    try { summary = await cleanupResources({ api, token: accounts.A.token, registry, marker }); }
    catch { /* Keep a static failure and still close every context and revoke every token. */ }
    let closingFailed = 0;
    for (const context of contexts) { try { await context.close(); } catch { closingFailed += 1; } }
    if (browser) { try { await browser.close(); } catch { closingFailed += 1; } }
    let sessionsFailed = 0;
    for (const token of tokens) { try { if (!(await api.logout(token))) sessionsFailed += 1; } catch { sessionsFailed += 1; } }
    report.setCleanup({ ...summary, failed: summary.failed + sessionsFailed + closingFailed, sessions_attempted: tokens.size, sessions_failed: sessionsFailed, closing_failed: closingFailed, registry: registry.counts() });
  }
  return { exitCode: report.status === 'PASS' ? 0 : 1, report };
}

module.exports = { runP0BrowserE2E, runStage, defaultLaunch, openInstrumentedPage };
