'use strict';

// TASK-AI-OPP-01C: real UI stages only. These functions create no fixture/product data and
// never call a model or a direct database. Live execution belongs to the approved root operator.
const { step, apiPath, withApiResponse, readData, navTo, loginFromStart, openLoginFromGuard, submitLogin } = require('./ui.cjs');
const { buildStages } = require('./scenario.cjs');
const S = require('./selectors.cjs');
const { assertMatchPage, assertBrief, ownSaved, assertNoSavedChange, assertSavedDraft, requireThat } = require('./ai-contract.cjs');

const AI = Object.freeze({
  route: '/app/ai', navigation: 'AI 도우미', keyword: '관심 키워드', search: '맞춤 공고 보기',
  list: '맞춤 공고', brief: '공고 요약', openBrief: '요약·절차 보기',
  makeDraft: '준비 초안 만들기', draft: '준비 초안 편집', memo: '준비 메모 초안',
  firstCheck: '준비 항목 초안 1', review: '준비 초안 검토', confirmation: '저장 전 확인',
  consent: '선택한 준비 항목을 내 기록에 추가하는 데 동의합니다',
  confirm: '확인하고 내 준비에 저장', cancel: '초안 취소',
  success: '선택한 준비 항목을 서버에서 다시 확인했습니다.',
});
const MATCH = /^\/me\/opportunity-matches$/;

async function navigateAi(ctx) {
  if (new URL(ctx.page.url()).pathname !== AI.route) {
    const link = ctx.page.getByRole('navigation', { name: S.NAV.landmark }).getByRole('link', { name: AI.navigation, exact: true });
    await step('navigate AI reference', async () => {
      if (!(await link.isVisible())) await ctx.page.locator(S.NAV.menuToggle).first().click();
      await link.click();
      await ctx.page.waitForURL(url => url.pathname === AI.route, { timeout: ctx.timeoutMs });
    });
  }
  await step('own reference input visible', () => ctx.page.getByLabel(AI.keyword, { exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
}

async function savedList(ctx, token = ctx.accounts.A.token) {
  const res = await ctx.api.expect('AI own saved requery', 'GET', '/me/saved-opportunities', 200, { token });
  requireThat(/no-store/i.test(res.cacheControl ?? ''), 'AI own saved requery missing no-store');
  requireThat(Array.isArray(res.data?.items), 'AI own saved list shape');
  return res.data;
}

/** Observe all API writes during a read/edit/cancel phase, not only known saved endpoints. */
function watchMutations(ctx) {
  let writes = 0;
  const listener = request => {
    if (apiPath(ctx, request.url()) !== null && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes += 1;
  };
  ctx.page.on('request', listener);
  return { count: () => writes, stop: () => ctx.page.off('request', listener) };
}

async function openReference(ctx, identity = ctx.accounts.A.identity) {
  await navigateAi(ctx);
  await ctx.page.getByLabel(AI.keyword, { exact: true }).fill('통합검증');
  const res = await withApiResponse(ctx, { label: 'own rule-based references', method: 'GET', path: MATCH, status: 200 },
    () => ctx.page.getByRole('button', { name: AI.search, exact: true }).click());
  assertMatchPage(await readData(res), identity, ctx.opportunity);
  const item = ctx.page.getByRole('list', { name: AI.list, exact: true }).locator('li').filter({ hasText: ctx.opportunity.title }).first();
  await step('approved reference evidence visible', () => item.getByLabel('일치 근거').waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  const brief = await withApiResponse(ctx, { label: 'own reference brief', method: 'GET', path: new RegExp(`^/me/opportunity-matches/${ctx.opportunity.id}/brief$`), status: 200 },
    () => item.getByRole('button', { name: AI.openBrief, exact: true }).click());
  assertBrief(await readData(brief), identity, ctx.opportunity);
  await step('reference brief evidence visible', () => ctx.page.getByRole('article', { name: AI.brief, exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
}

async function editDraft(ctx) {
  await ctx.page.getByRole('button', { name: AI.makeDraft, exact: true }).click();
  const region = ctx.page.getByRole('region', { name: AI.draft, exact: true });
  await region.waitFor({ state: 'visible', timeout: ctx.timeoutMs });
  await region.getByLabel(AI.memo, { exact: true }).fill(ctx.state.ai.memo);
  await region.getByLabel(AI.firstCheck, { exact: true }).fill(ctx.state.ai.checkText);
  const choices = region.getByRole('checkbox', { name: /^초안 항목 \d+ 저장$/ });
  const count = await choices.count();
  requireThat(count >= 1 && count <= 10, 'bounded draft choices required');
  for (let i = 0; i < count; i += 1) {
    if (i === 0) await choices.nth(i).check();
    else await choices.nth(i).uncheck();
  }
  return region;
}

async function loginA(ctx) {
  requireThat(!ctx.accounts.B.hadOpportunitySaved, 'AI test requires B without this DEMO saved record');
  ctx.state.ai = { memo: `${ctx.marker} AI 준비 ${ctx.vp}`, checkText: `${ctx.marker} AI 원문 검토 ${ctx.vp}` };
  await loginFromStart(ctx, ctx.accounts.A.credential, ctx.accounts.A.identity);
}

async function previewAndCancel(ctx) {
  const before = await savedList(ctx);
  requireThat(ownSaved(before, ctx.opportunity.id) === null, 'AI draft must not overwrite a pre-existing saved record');
  const observer = watchMutations(ctx);
  try {
    await openReference(ctx);
    await editDraft(ctx);
    await ctx.page.getByRole('button', { name: AI.cancel, exact: true }).click();
    await ctx.page.getByRole('region', { name: AI.draft, exact: true }).waitFor({ state: 'hidden', timeout: ctx.timeoutMs });
    assertNoSavedChange(before, await savedList(ctx));
    requireThat(observer.count() === 0, 'reference, edit or cancellation issued an API write');
  } finally { observer.stop(); }
}

async function explicitSave(ctx) {
  const before = await savedList(ctx);
  requireThat(ownSaved(before, ctx.opportunity.id) === null, 'AI confirmation found an existing saved record');
  const observer = watchMutations(ctx);
  try {
    const draft = await editDraft(ctx);
    await draft.getByRole('button', { name: AI.review, exact: true }).click();
    await ctx.page.getByRole('region', { name: AI.confirmation, exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
    assertNoSavedChange(before, await savedList(ctx));
    requireThat(observer.count() === 0, 'review before explicit consent issued an API write');
  } finally { observer.stop(); }
  const confirmation = ctx.page.getByRole('region', { name: AI.confirmation, exact: true });
  const button = confirmation.getByRole('button', { name: AI.confirm, exact: true });
  requireThat(await button.isDisabled(), 'save must require explicit consent');
  await confirmation.getByRole('checkbox', { name: AI.consent, exact: true }).check();
  // Register BEFORE the write: an uncertain PUT/check response must still be reviewed by the
  // existing current-marker cleanup. A row created by someone else is skipped, never adopted.
  ctx.registry.register('saved_opportunity', ctx.opportunity.id, { viewport: ctx.vp });
  const response = await withApiResponse(ctx, { label: 'explicit AI preparation save', method: 'PUT', path: new RegExp(`^/me/saved-opportunities/${ctx.opportunity.id}$`), status: 201 }, () => button.click());
  requireThat((await readData(response))?.opportunity_id === ctx.opportunity.id, 'explicit save returned another opportunity');
  await step('server-confirmed preparation success', () => ctx.page.getByText(AI.success, { exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  const saved = ownSaved(await savedList(ctx), ctx.opportunity.id);
  ctx.state.ai.check = assertSavedDraft(saved, { opportunityId: ctx.opportunity.id, ...ctx.state.ai });
  ctx.state.saved = { checkText: ctx.state.ai.checkText }; // Existing P0 remove UI stage contract.
}

async function freshSessionRead(ctx) {
  await step('reload AI protected preparation', () => ctx.page.reload({ waitUntil: 'domcontentloaded', timeout: ctx.timeoutMs }));
  await openLoginFromGuard(ctx);
  await submitLogin(ctx, ctx.accounts.A.credential, ctx.accounts.A.identity);
  ctx.recordReload('relogin_required');
  const response = await withApiResponse(ctx, { label: 'fresh UI session saved requery', method: 'GET', path: /^\/me\/saved-opportunities$/, status: 200 }, () => navTo(ctx, 'opportunities'));
  assertSavedDraft(ownSaved(await readData(response), ctx.opportunity.id), { opportunityId: ctx.opportunity.id, ...ctx.state.ai });
  await ctx.page.locator(S.OPP.savedSection).getByText(ctx.state.ai.checkText, { exact: true }).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
}

async function isolationB(ctx) {
  const peer = { ...ctx, ...await ctx.newPeer() };
  await loginFromStart(peer, ctx.accounts.B.credential, ctx.accounts.B.identity);
  await openReference(peer, ctx.accounts.B.identity);
  await navTo(peer, 'opportunities');
  requireThat(await peer.page.locator(S.OPP.savedSection).getByText(ctx.state.ai.checkText, { exact: true }).count() === 0, 'B UI contains A preparation');
  const bSaved = await savedList(ctx, ctx.accounts.B.token);
  requireThat(!JSON.stringify(bSaved).includes(ctx.marker) && ownSaved(bSaved, ctx.opportunity.id) === null, 'B server list contains A preparation');
  const path = `/me/saved-opportunities/${ctx.opportunity.id}`;
  await ctx.api.expect('B cannot edit A preparation', 'PATCH', path, 404, { token: ctx.accounts.B.token,
    body: { memo: `${ctx.marker} denied` }, headers: { 'If-Match': '1' } });
  await ctx.api.expect('B cannot edit A checklist', 'PATCH', `${path}/checks/${encodeURIComponent(ctx.state.ai.check.id)}`, 404, { token: ctx.accounts.B.token,
    body: { text: `${ctx.marker} denied` }, headers: { 'If-Match': String(ctx.state.ai.check.revision) } });
  assertSavedDraft(ownSaved(await savedList(ctx), ctx.opportunity.id), { opportunityId: ctx.opportunity.id, ...ctx.state.ai });
}

function buildAiStages() {
  const old = buildStages({ includeClose: false });
  return [
    { id: 'auth.login_a', deps: [], run: loginA },
    { id: 'opportunity.ai_reference_preview_cancel', deps: ['auth.login_a'], run: previewAndCancel },
    { id: 'opportunity.ai_explicit_save', deps: ['opportunity.ai_reference_preview_cancel'], run: explicitSave },
    { id: 'opportunity.ai_fresh_session_read', deps: ['opportunity.ai_explicit_save'], run: freshSessionRead },
    { id: 'isolation.ai_student_b', deps: ['opportunity.ai_fresh_session_read'], run: isolationB },
    { id: 'opportunity.remove', deps: ['opportunity.ai_explicit_save'], run: old.find(s => s.id === 'opportunity.remove').run },
    { id: 'auth.logout_a', deps: ['auth.login_a'], run: old.find(s => s.id === 'auth.logout_a').run },
  ];
}

module.exports = { AI, buildAiStages, watchMutations, navigateAi, editDraft };
