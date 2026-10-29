'use strict';

const { E2EError } = require('./errors.cjs');
const S = require('./selectors.cjs');
const { step, withApiResponse, readData, navTo, loginFromStart, reloadAndResume, openLoginFromGuard } = require('./ui.cjs');

const DENIED = [403, 404];

function assert(condition, detail) {
  if (!condition) throw new E2EError('ASSERTION', detail);
}

function localDeadline(days) {
  const d = new Date(Date.now() + days * 86_400_000);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

// Anonymous payloads must never carry A's identity (FR-COM-001 / NFR-PRIV-001).
function assertNoIdentity(value, account, label) {
  const text = JSON.stringify(value);
  for (const secret of [account.identity.user_id, account.identity.display_name, account.credential.studentId]) {
    assert(!secret || !text.includes(secret), `${label}: anonymous projection contains author identity`);
  }
}

async function findMine(ctx, path, title, label) {
  const { data } = await ctx.api.expect(`${label} list requery`, 'GET', `${path}?limit=50`, 200, { token: ctx.accounts.A.token });
  const item = (data?.items ?? []).find((i) => i.title === title && i.is_mine === true);
  assert(item, `${label}: created item not found as is_mine in API list`);
  return item;
}

async function getById(ctx, path, id, label, statuses = 200, token = ctx.accounts.A.token) {
  return ctx.api.expect(label, 'GET', `${path}/${encodeURIComponent(id)}`, statuses, { token });
}

function onceAcceptDialog(page) {
  page.once('dialog', (dialog) => dialog.accept().catch(() => {}));
}

// ------------------------------------------------------------------ stages

async function loginA(ctx) {
  await loginFromStart(ctx, ctx.accounts.A.credential, ctx.accounts.A.identity);
}

async function anonymousCreateEditReload(ctx) {
  const { page, state } = ctx;
  await navTo(ctx, 'community');
  const section = page.locator(S.ANON.section);
  const form = section.locator('form').first();
  const title = `${ctx.marker} 익명 ${ctx.vp}`;
  await step('anon create form', async () => {
    await form.getByLabel(S.ANON.title, { exact: true }).fill(title);
    await form.getByLabel(S.ANON.body, { exact: true }).fill(`${ctx.marker} 브라우저 확인 본문`);
  });
  await withApiResponse(ctx, { label: 'anon create', method: 'POST', path: /^\/anonymous-posts$/, status: 201 }, () =>
    form.getByRole('button', { name: S.ANON.submit }).click(),
  );
  const created = await findMine(ctx, '/anonymous-posts', title, 'anon create');
  ctx.registry.register('anonymous_post', created.id, { revision: created.revision, viewport: ctx.vp });
  assert(created.display_name === S.ANON.anonymousName, 'anon create: display_name is not 익명');
  assertNoIdentity(created, ctx.accounts.A, 'anon create');

  const item = section.locator('li').filter({ hasText: title }).first();
  await step('anon item visible as 익명', () => item.waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  const itemText = await item.innerText();
  assert(itemText.includes(S.ANON.anonymousName), 'anon UI: author label 익명 missing');
  assert(!itemText.includes(ctx.accounts.A.identity.display_name), 'anon UI: author display name leaked');

  const edited = `${title} 수정`;
  await step('anon open edit', () => item.getByRole('button', { name: S.ANON.edit, exact: true }).click());
  const editing = section.locator('li').filter({ has: page.getByLabel(S.ANON.editTitle) }).first();
  await step('anon edit form', () => editing.getByLabel(S.ANON.editTitle).fill(edited));
  await withApiResponse(ctx, { label: 'anon update', method: 'PATCH', path: /^\/anonymous-posts\/[^/]+$/, status: 200 }, () =>
    editing.getByRole('button', { name: S.ANON.save, exact: true }).click(),
  );

  await reloadAndResume(ctx, 'community', ctx.accounts.A.credential, ctx.accounts.A.identity);
  await step('anon edited title after reload', () =>
    page.locator(S.ANON.section).locator('li').filter({ hasText: edited }).first().waitFor({ state: 'visible', timeout: ctx.timeoutMs }),
  );
  const { data } = await getById(ctx, '/anonymous-posts', created.id, 'anon read after reload');
  assert(data?.title === edited, 'anon read: API title does not match edited title');
  assert(data.revision > created.revision, 'anon read: revision did not advance');
  ctx.registry.register('anonymous_post', created.id, { revision: data.revision });
  state.post = { id: created.id, title: edited, revision: data.revision };
}

async function recruitmentCreateEditReload(ctx) {
  const { page, state } = ctx;
  await navTo(ctx, 'recruitments');
  const section = page.locator(S.RECRUIT.section);
  const form = section.locator('form').first();
  const title = `${ctx.marker} 모집 ${ctx.vp}`;
  await step('recruit create form', async () => {
    await form.getByLabel(S.RECRUIT.title, { exact: true }).fill(title);
    await form.getByLabel(S.RECRUIT.field, { exact: true }).fill('E2E');
    await form.getByLabel(S.RECRUIT.roles).fill('프런트엔드, 백엔드');
    await form.getByLabel(S.RECRUIT.capacity).fill('3');
    await form.getByLabel(S.RECRUIT.deadline).fill(localDeadline(14));
    await form.getByLabel(S.RECRUIT.body, { exact: true }).fill(`${ctx.marker} 모집 설명`);
  });
  await withApiResponse(ctx, { label: 'recruit create', method: 'POST', path: /^\/recruitments$/, status: 201 }, () =>
    form.getByRole('button', { name: S.RECRUIT.submit }).click(),
  );
  const created = await findMine(ctx, '/recruitments', title, 'recruit create');
  ctx.registry.register('recruitment', created.id, { revision: created.revision, viewport: ctx.vp });
  assert(created.status === 'open', 'recruit create: status is not open');

  const item = section.locator('li').filter({ hasText: title }).first();
  await step('recruit item visible', () => item.waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  const edited = `${title} 수정`;
  await step('recruit open edit', () => item.getByRole('button', { name: S.RECRUIT.edit, exact: true }).click());
  const editForm = section.getByRole('form', { name: S.RECRUIT.editForm });
  await step('recruit edit form', async () => {
    await editForm.getByLabel(S.RECRUIT.title, { exact: true }).fill(edited);
    await editForm.getByLabel(S.RECRUIT.field, { exact: true }).fill('E2E 수정');
  });
  await withApiResponse(ctx, { label: 'recruit update', method: 'PATCH', path: /^\/recruitments\/[^/]+$/, status: 200 }, () =>
    editForm.getByRole('button', { name: S.RECRUIT.save, exact: true }).click(),
  );

  await reloadAndResume(ctx, 'recruitments', ctx.accounts.A.credential, ctx.accounts.A.identity);
  await step('recruit edited title after reload', () =>
    page.locator(S.RECRUIT.section).locator('li').filter({ hasText: edited }).first().waitFor({ state: 'visible', timeout: ctx.timeoutMs }),
  );
  const { data } = await getById(ctx, '/recruitments', created.id, 'recruit read after reload');
  assert(data?.title === edited && data.field === 'E2E 수정', 'recruit read: API fields do not match edit');
  assert(data.revision > created.revision, 'recruit read: revision did not advance');
  ctx.registry.register('recruitment', created.id, { revision: data.revision });
  state.recruitment = { id: created.id, title: edited, revision: data.revision };
}

function savedCard(ctx) {
  return ctx.page.locator(S.OPP.savedSection).locator('li').filter({ hasText: ctx.opportunity.title }).first();
}

async function opportunitySaveCheckUpdateReload(ctx) {
  const { page, state } = ctx;
  const id = ctx.opportunity.id;
  await navTo(ctx, 'opportunities');
  const list = page.locator(S.OPP.listSection);
  await step('opp find seeded DEMO item', async () => {
    await list.getByLabel(S.OPP.openOnly).uncheck();
    await list.getByLabel(S.OPP.search).fill(ctx.opportunity.title.slice(0, 50));
    await list.getByRole('button').filter({ hasText: ctx.opportunity.title }).first().click({ timeout: ctx.timeoutMs });
  });
  const saveRes = await withApiResponse(
    ctx,
    { label: 'opp save', method: 'PUT', path: /^\/me\/saved-opportunities\/[^/]+$/, status: 201 },
    () => list.getByRole('button', { name: S.OPP.save }).click({ timeout: ctx.timeoutMs }),
  );
  // Registered on the 201 itself so cleanup covers it even if a later requery fails.
  ctx.registry.register('saved_opportunity', id, { viewport: ctx.vp });
  const savedData = await readData(saveRes);
  assert(savedData?.opportunity_id === id, 'opp save: response is for a different opportunity');

  const checkText = `${ctx.marker} 준비 ${ctx.vp}`;
  const card = savedCard(ctx);
  await step('opp check form', () => card.getByLabel(S.OPP.checkInput).fill(checkText));
  await withApiResponse(ctx, { label: 'opp check add', method: 'POST', path: /^\/me\/saved-opportunities\/[^/]+\/checks$/, status: 201 }, () =>
    card.getByRole('button', { name: S.OPP.checkAdd, exact: true }).click(),
  );
  await withApiResponse(ctx, { label: 'opp check toggle', method: 'PATCH', path: /^\/me\/saved-opportunities\/[^/]+\/checks\/[^/]+$/, status: 200 }, () =>
    // click(), not check(): the checkbox is server-controlled and only flips after the refetch.
    card.getByLabel(S.OPP.checkDone(checkText)).click(),
  );
  await withApiResponse(ctx, { label: 'opp status update', method: 'PATCH', path: /^\/me\/saved-opportunities\/[^/]+$/, status: 200 }, () =>
    card.getByRole('button', { name: S.OPP.statusChange }).first().click(),
  );

  await reloadAndResume(ctx, 'opportunities', ctx.accounts.A.credential, ctx.accounts.A.identity);
  await step('opp check persisted after reload', async () => {
    await savedCard(ctx).getByText(checkText).waitFor({ state: 'visible', timeout: ctx.timeoutMs });
    if (!(await savedCard(ctx).getByLabel(S.OPP.checkDone(checkText)).isChecked())) throw new E2EError('ASSERTION', 'opp UI: check not completed after reload');
  });
  const { data } = await ctx.api.expect('opp saved requery', 'GET', '/me/saved-opportunities', 200, { token: ctx.accounts.A.token });
  const saved = (data?.items ?? []).find((s) => s.opportunity_id === id);
  assert(saved, 'opp requery: saved item missing');
  const check = (saved.checks ?? []).find((c) => c.text === checkText);
  assert(check && check.completed_at, 'opp requery: check missing or not completed');
  assert(saved.status !== savedData.status && saved.revision > savedData.revision, 'opp requery: status/revision not updated');
  state.saved = { checkText };
}

async function isolationStudentB(ctx) {
  const B = ctx.accounts.B;
  const A = ctx.accounts.A;
  const { post, recruitment, saved } = ctx.state;
  const peer = await ctx.newPeer();
  await loginFromStart(peer, B.credential, B.identity);

  await navTo(peer, 'community');
  const postItem = peer.page.locator(S.ANON.section).locator('li').filter({ hasText: post.title }).first();
  await step('B sees A post as 익명', () => postItem.waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  const postText = await postItem.innerText();
  assert(!postText.includes(A.identity.display_name), 'B UI: A display name leaked on anonymous post');
  assert((await postItem.getByRole('button', { name: S.ANON.edit, exact: true }).count()) === 0, 'B UI: edit offered on A post');
  assert((await postItem.getByRole('button', { name: S.ANON.remove, exact: true }).count()) === 0, 'B UI: delete offered on A post');

  await navTo(peer, 'recruitments');
  const recItem = peer.page.locator(S.RECRUIT.section).locator('li').filter({ hasText: recruitment.title }).first();
  await step('B sees A recruitment', () => recItem.waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  for (const name of [S.RECRUIT.edit, S.RECRUIT.close, S.RECRUIT.remove]) {
    assert((await recItem.getByRole('button', { name, exact: true }).count()) === 0, `B UI: owner action offered on A recruitment`);
  }

  await navTo(peer, 'opportunities');
  await step('B saved list loaded', () => peer.page.locator(S.OPP.savedSection).waitFor({ state: 'visible', timeout: ctx.timeoutMs }));
  assert((await peer.page.locator(S.OPP.savedSection).getByText(saved.checkText).count()) === 0, 'B UI: A checklist visible');

  // Direct server attempts with B's own token: UI hiding is not authorization (TC-018).
  const t = { token: B.token };
  const postRef = encodeURIComponent(post.id);
  const recRef = encodeURIComponent(recruitment.id);
  const deny = `${S.QUESTIONS.CROSS_ACCOUNT} B`;
  // Valid payloads, so a refusal proves authorization rather than input validation.
  const attempt = `${ctx.marker} B 시도`;
  await ctx.api.expect(`${deny} PATCH A post`, 'PATCH', `/anonymous-posts/${postRef}`, DENIED, { ...t, body: { revision: post.revision, title: attempt } });
  await ctx.api.expect(`${deny} DELETE A post`, 'DELETE', `/anonymous-posts/${postRef}?revision=${post.revision}`, DENIED, t);
  await ctx.api.expect(`${deny} PATCH A recruitment`, 'PATCH', `/recruitments/${recRef}`, DENIED, { ...t, body: { revision: recruitment.revision, title: attempt } });
  await ctx.api.expect(`${deny} close A recruitment`, 'POST', `/recruitments/${recRef}/close`, DENIED, { ...t, body: { revision: recruitment.revision } });
  await ctx.api.expect(`${deny} DELETE A recruitment`, 'DELETE', `/recruitments/${recRef}?revision=${recruitment.revision}`, DENIED, t);
  const bSaved = await ctx.api.expect('B saved list', 'GET', '/me/saved-opportunities', 200, t);
  assert(!JSON.stringify(bSaved.data ?? {}).includes(saved.checkText), 'B API: A checklist returned');
  if (!B.hadOpportunitySaved) {
    await ctx.api.expect(`${deny} PATCH A saved`, 'PATCH', `/me/saved-opportunities/${encodeURIComponent(ctx.opportunity.id)}`, 404, {
      ...t,
      headers: { 'If-Match': '1' },
      body: { memo: attempt },
    });
  }

  const postAfter = await getById(ctx, '/anonymous-posts', post.id, 'A post after B attempts');
  assert(postAfter.data?.revision === post.revision && postAfter.data.title === post.title, 'A post changed by B');
  const recAfter = await getById(ctx, '/recruitments', recruitment.id, 'A recruitment after B attempts');
  assert(recAfter.data?.revision === recruitment.revision && recAfter.data.status === 'open', 'A recruitment changed by B');
}

async function anonymousDelete(ctx) {
  const { page, state } = ctx;
  await navTo(ctx, 'community');
  const item = page.locator(S.ANON.section).locator('li').filter({ hasText: state.post.title }).first();
  onceAcceptDialog(page);
  await withApiResponse(ctx, { label: 'anon delete', method: 'DELETE', path: /^\/anonymous-posts\/[^/]+$/, status: 200 }, () =>
    item.getByRole('button', { name: S.ANON.remove, exact: true }).click(),
  );
  await reloadAndResume(ctx, 'community', ctx.accounts.A.credential, ctx.accounts.A.identity);
  assert((await page.locator(S.ANON.section).locator('li').filter({ hasText: state.post.title }).count()) === 0, 'anon UI: deleted post still listed');
  await getById(ctx, '/anonymous-posts', state.post.id, 'anon GET after delete', 404);
  ctx.registry.mark('anonymous_post', state.post.id, 'deleted');
}

async function recruitmentDelete(ctx) {
  const { page, state } = ctx;
  await navTo(ctx, 'recruitments');
  const item = page.locator(S.RECRUIT.section).locator('li').filter({ hasText: state.recruitment.title }).first();
  onceAcceptDialog(page);
  const res = await withApiResponse(
    ctx,
    { label: `${S.QUESTIONS.RECRUIT_DELETE} recruit delete`, method: 'DELETE', path: /^\/recruitments\/[^/]+$/, status: 200 },
    () => item.getByRole('button', { name: S.RECRUIT.remove, exact: true }).click(),
  );
  const data = await readData(res);
  assert(data?.deleted === true && data.id === state.recruitment.id, 'recruit delete: response is not data{id,deleted:true}');
  await reloadAndResume(ctx, 'recruitments', ctx.accounts.A.credential, ctx.accounts.A.identity);
  assert((await page.locator(S.RECRUIT.section).locator('li').filter({ hasText: state.recruitment.title }).count()) === 0, 'recruit UI: cancelled item still listed');
  await getById(ctx, '/recruitments', state.recruitment.id, 'recruit GET after delete', 404);
  const list = await ctx.api.expect('recruit list after delete', 'GET', '/recruitments?limit=50', 200, { token: ctx.accounts.A.token });
  assert(!(list.data?.items ?? []).some((i) => i.id === state.recruitment.id), 'recruit list: cancelled item still listed');
  ctx.registry.mark('recruitment', state.recruitment.id, 'deleted');
}

async function opportunityRemove(ctx) {
  const { state } = ctx;
  await navTo(ctx, 'opportunities');
  const card = savedCard(ctx);
  await withApiResponse(ctx, { label: 'opp check delete', method: 'DELETE', path: /^\/me\/saved-opportunities\/[^/]+\/checks\/[^/]+$/, status: 200 }, () =>
    card.locator('li').filter({ hasText: state.saved.checkText }).getByRole('button', { name: S.OPP.checkRemove, exact: true }).click(),
  );
  await withApiResponse(ctx, { label: 'opp remove', method: 'DELETE', path: /^\/me\/saved-opportunities\/[^/]+$/, status: 200 }, () =>
    savedCard(ctx).getByRole('button', { name: S.OPP.removeSaved }).click(),
  );
  await reloadAndResume(ctx, 'opportunities', ctx.accounts.A.credential, ctx.accounts.A.identity);
  assert((await savedCard(ctx).count()) === 0, 'opp UI: removed item still in saved list');
  const { data } = await ctx.api.expect('opp saved after remove', 'GET', '/me/saved-opportunities', 200, { token: ctx.accounts.A.token });
  assert(!(data?.items ?? []).some((s) => s.opportunity_id === ctx.opportunity.id), 'opp requery: removed item still saved');
  ctx.registry.mark('saved_opportunity', ctx.opportunity.id, 'deleted');
}

// Separate sample so the delete path above is never exercised on a closed item.
async function recruitmentCloseNotDeletable(ctx) {
  const { page } = ctx;
  await navTo(ctx, 'recruitments');
  const section = page.locator(S.RECRUIT.section);
  const form = section.locator('form').first();
  const title = `${ctx.marker} 마감표본 ${ctx.vp}`;
  await step('close sample form', async () => {
    await form.getByLabel(S.RECRUIT.title, { exact: true }).fill(title);
    await form.getByLabel(S.RECRUIT.field, { exact: true }).fill('E2E');
    await form.getByLabel(S.RECRUIT.roles).fill('디자인');
    await form.getByLabel(S.RECRUIT.capacity).fill('2');
    await form.getByLabel(S.RECRUIT.deadline).fill(localDeadline(14));
    await form.getByLabel(S.RECRUIT.body, { exact: true }).fill(`${ctx.marker} 마감 표본`);
  });
  await withApiResponse(ctx, { label: 'close sample create', method: 'POST', path: /^\/recruitments$/, status: 201 }, () =>
    form.getByRole('button', { name: S.RECRUIT.submit }).click(),
  );
  const created = await findMine(ctx, '/recruitments', title, 'close sample');
  ctx.registry.register('recruitment', created.id, { revision: created.revision, viewport: ctx.vp });
  const item = section.locator('li').filter({ hasText: title }).first();
  onceAcceptDialog(page);
  await withApiResponse(ctx, { label: 'close sample close', method: 'POST', path: /^\/recruitments\/[^/]+\/close$/, status: 200 }, () =>
    item.getByRole('button', { name: S.RECRUIT.close, exact: true }).click(),
  );
  const closed = await getById(ctx, '/recruitments', created.id, 'close sample read');
  assert(closed.data?.status === 'closed', 'close sample: status is not closed');
  const refused = await ctx.api.request(`${S.QUESTIONS.CLOSED_DELETE} DELETE closed`, 'DELETE', `/recruitments/${encodeURIComponent(created.id)}?revision=${closed.data.revision}`, {
    token: ctx.accounts.A.token,
  });
  assert(refused.status >= 400 && refused.status < 500 && refused.status !== 401, `${S.QUESTIONS.CLOSED_DELETE}: DELETE closed returned ${refused.status}`);
  const still = await getById(ctx, '/recruitments', created.id, 'close sample still readable');
  assert(still.data?.status === 'closed', 'close sample: closed item changed after refused DELETE');
}

async function logoutA(ctx) {
  const { page } = ctx;
  const button = page.getByRole('button', { name: S.LOGIN.logout, exact: true });
  await step(`${S.QUESTIONS.LOGOUT} find logout`, async () => {
    if (!(await button.first().isVisible())) await page.locator(S.NAV.menuToggle).first().click();
    await button.first().waitFor({ state: 'visible', timeout: ctx.timeoutMs });
  });
  await withApiResponse(ctx, { label: 'UI POST /auth/logout', method: 'POST', path: /^\/auth\/logout$/, status: 200 }, () => button.first().click());
  await navTo(ctx, 'community', { expectList: false });
  await openLoginFromGuard(ctx);
}

/** Ordered per-viewport stages. `deps` are same-viewport stage IDs that must PASS first. */
function buildStages({ includeClose }) {
  const stages = [
    { id: 'auth.login_a', deps: [], run: loginA },
    { id: 'community.anonymous.create_edit_reload', deps: ['auth.login_a'], run: anonymousCreateEditReload },
    { id: 'community.recruitment.create_edit_reload', deps: ['auth.login_a'], run: recruitmentCreateEditReload },
    { id: 'opportunity.save_check_update_reload', deps: ['auth.login_a'], run: opportunitySaveCheckUpdateReload },
    {
      id: 'isolation.student_b',
      deps: ['community.anonymous.create_edit_reload', 'community.recruitment.create_edit_reload', 'opportunity.save_check_update_reload'],
      run: isolationStudentB,
    },
    { id: 'community.anonymous.delete', deps: ['community.anonymous.create_edit_reload'], run: anonymousDelete },
    { id: 'community.recruitment.delete', deps: ['community.recruitment.create_edit_reload'], run: recruitmentDelete },
    { id: 'opportunity.remove', deps: ['opportunity.save_check_update_reload'], run: opportunityRemove },
  ];
  if (includeClose) stages.push({ id: 'community.recruitment.close_not_deletable', deps: ['auth.login_a'], run: recruitmentCloseNotDeletable });
  stages.push({ id: 'auth.logout_a', deps: ['auth.login_a'], run: logoutA });
  return stages;
}

module.exports = { buildStages, localDeadline };
