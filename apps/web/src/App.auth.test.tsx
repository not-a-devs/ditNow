import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

const me = { user_id: '10000000-0000-4000-8000-000000000001', display_name: '가상 A', record_source: 'DEMO', department_id: '20000000-0000-4000-8000-000000000001', department_code: 'DEMO', academic_year: 1, community_access: true };
const post = { id: 'post-fixture', display_name: '익명', title: '가상 게시글', body: '시험용 본문', status: 'active', comment_count: 0, is_mine: true, revision: 1, created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z' };
const ok = (data: unknown, status = 200) => new Response(JSON.stringify({ data }), { status });
const fail = (status: number) => new Response(JSON.stringify({ code: status === 401 ? 'UNAUTHORIZED' : 'UNAVAILABLE', message: 'raw-private-secret' }), { status });
const page = (items: unknown[]) => ({ items, offset: 0, limit: 20, has_more: false });
type Handler = (path: string, init: RequestInit) => Response | Promise<Response>;
function backend(handler: Handler) {
  const fetcher = vi.fn((url: string, init: RequestInit = {}) => {
    const path = new URL(url).pathname.replace('/api/v1', '');
    if (path === '/auth/login') { const input = JSON.parse(String(init.body)); return Promise.resolve(ok({ token: `token.${input.student_id}`, token_type: 'Bearer', student_id: input.student_id, name: '가상 이름', record_source: 'DEMO' })); }
    return Promise.resolve(handler(path, init));
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
function navigate(name: string) { fireEvent.click(within(screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' })).getByRole('link', { name })); }
async function login(id = 'fakeA') {
  navigate('로그인 · 계정');
  fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: id } });
  fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'synthetic-password' } });
  fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
  await screen.findByRole('heading', { name: '현재 가상 계정' });
}
function logout() { fireEvent.click(screen.getAllByRole('button', { name: '로그아웃' })[0]); }

describe('new application authenticated P0 integration (fetch test double only)', () => {
  it('requires current auth/me after login; 503 never opens protected screens', async () => {
    const fetcher = backend(path => path === '/auth/me' ? fail(503) : ok(page([])));
    render(<StrictMode><App /></StrictMode>);
    navigate('익명 커뮤니티');
    expect(fetcher).not.toHaveBeenCalled();
    navigate('로그인 · 계정');
    fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: 'fakeA' } });
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'synthetic' } });
    const submit = screen.getByRole('button', { name: '가상 계정으로 로그인' }).closest('form')!;
    fireEvent.submit(submit); fireEvent.submit(submit);
    await screen.findByText('공통 신원·권한 서버가 준비되지 않아 로그인되지 않았습니다.');
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/auth/login'))).toHaveLength(1);
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/auth/me'))).toHaveLength(1);
    navigate('익명 커뮤니티');
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    expect(screen.queryByText('raw-private-secret')).not.toBeInTheDocument();
  });

  it('creates, re-reads, edits and deletes anonymous posts through authenticated API requests', async () => {
    let rows: typeof post[] = [];
    const fetcher = backend((path, init) => {
      if (path === '/auth/me') return ok(me);
      if (path === '/anonymous-posts' && !init?.method) return ok(page(rows));
      if (path === '/anonymous-posts' && init?.method === 'POST') { rows = [{ ...post, ...JSON.parse(String(init.body)) }]; return ok(rows[0], 201); }
      if (init?.method === 'PATCH') { rows = [{ ...rows[0], ...JSON.parse(String(init.body)), revision: 2 }]; return ok(rows[0]); }
      if (init?.method === 'DELETE') { rows = []; return ok({ id: post.id, deleted: true }); }
      return fail(503);
    });
    render(<StrictMode><App /></StrictMode>); await login(); navigate('익명 커뮤니티');
    await screen.findByText('게시글이(가) 아직 없습니다.');
    fireEvent.change(screen.getByLabelText('제목'), { target: { value: '새 글 제목' } });
    fireEvent.change(screen.getByLabelText('본문'), { target: { value: '새 글 본문' } });
    fireEvent.click(screen.getByRole('button', { name: '익명으로 등록 요청' }));
    await screen.findByRole('heading', { name: '새 글 제목' });
    fireEvent.click(screen.getByRole('button', { name: '수정' }));
    fireEvent.change(screen.getByLabelText('본문 수정'), { target: { value: '수정한 본문' } });
    fireEvent.click(screen.getByRole('button', { name: '수정 요청' }));
    await screen.findByText('수정한 본문'); vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '삭제' }));
    await screen.findByText('게시글이(가) 아직 없습니다.');
    const calls = fetcher.mock.calls.filter(([url]) => url.includes('/anonymous-posts'));
    for (const [, init] of calls) expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer token.fakeA');
    expect(calls.find(([, init]) => init?.method === 'POST')![1]!.headers).toHaveProperty('Idempotency-Key');
    expect(calls.filter(([, init]) => !init?.method).length).toBeGreaterThanOrEqual(4);
    expect(calls.find(([, init]) => init?.method === 'PATCH')![1]!.body).toContain('"revision":1');
    expect(calls.find(([, init]) => init?.method === 'DELETE')![0]).toContain('revision=2');
  });

  it.each([401, 403])('clears all private data on current %s', async status => {
    let denied = false;
    backend((path, init) => path === '/auth/me' ? ok(me) : init?.method === 'POST' ? (denied = true, fail(status)) : ok(page(denied ? [] : [post])));
    render(<App />); await login(); navigate('익명 커뮤니티'); await screen.findByText(post.body);
    fireEvent.change(screen.getByLabelText('제목'), { target: { value: '비공개 초안' } });
    fireEvent.change(screen.getByLabelText('본문'), { target: { value: '폐기할 초안' } });
    fireEvent.click(screen.getByRole('button', { name: '익명으로 등록 요청' }));
    await screen.findByText('로그인이 필요한 화면입니다');
    expect(screen.queryByText(post.body)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('폐기할 초안')).not.toBeInTheDocument();
    expect(screen.getByText('로그인되지 않음')).toBeInTheDocument();
  });

  it('discards late A mutation and drafts after logout and B login, without querying B from old A UI', async () => {
    let finish!: (value: Response) => void, oldSignal!: AbortSignal;
    const fetcher = backend((path, init) => {
      const bearer = new Headers(init?.headers).get('Authorization');
      if (path === '/auth/me') return ok({ ...me, display_name: bearer?.includes('fakeB') ? '가상 B' : '가상 A' });
      if (path === '/auth/logout') return ok({ status: 'ok' });
      if (init?.method === 'POST') { oldSignal = init.signal!; return new Promise<Response>(resolve => { finish = resolve; }); }
      return ok(page(bearer?.includes('fakeB') ? [] : [post]));
    });
    render(<StrictMode><App /></StrictMode>); await login(); navigate('익명 커뮤니티'); await screen.findByText(post.body);
    fireEvent.change(screen.getByLabelText('제목'), { target: { value: 'A 전용 초안' } });
    fireEvent.change(screen.getByLabelText('본문'), { target: { value: '이전 계정 본문' } });
    const createForm = screen.getByRole('button', { name: '익명으로 등록 요청' }).closest('form')!;
    fireEvent.submit(createForm); fireEvent.submit(createForm);
    expect(fetcher.mock.calls.filter(([url, init]) => url.includes('/anonymous-posts') && init?.method === 'POST')).toHaveLength(1);
    logout(); expect(oldSignal.aborted).toBe(true); expect(screen.queryByText(post.body)).not.toBeInTheDocument();
    await login('fakeB'); navigate('익명 커뮤니티'); await screen.findByText('게시글이(가) 아직 없습니다.');
    const before = fetcher.mock.calls.length;
    await act(async () => finish(ok({ ...post, title: 'A 늦은 성공' }, 201)));
    expect(fetcher).toHaveBeenCalledTimes(before);
    expect(screen.getByLabelText('제목')).toHaveValue(''); expect(screen.queryByText('A 늦은 성공')).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });

  it('does not display a private list until auth/me resolves, or accept malformed authority', async () => {
    let complete!: (r: Response) => void;
    const fetcher = backend(() => new Promise<Response>(resolve => { complete = resolve; }));
    render(<App />); navigate('로그인 · 계정');
    fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: 'fakeA' } });
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'synthetic' } });
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    await screen.findByText('공통 신원과 현재 권한을 확인 중입니다');
    navigate('익명 커뮤니티'); expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    await act(async () => complete(ok({ ...me, extra_token: 'must-not-propagate' })));
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it('ignores a previous account logout failure after another account signs in', async () => {
    let finishLogout!: (response: Response) => void;
    backend((path, init) => {
      if (path === '/auth/me') return ok({ ...me, display_name: new Headers(init.headers).get('Authorization')?.includes('fakeB') ? '가상 B' : '가상 A' });
      if (path === '/auth/logout') return new Promise<Response>(resolve => { finishLogout = resolve; });
      return ok(page([]));
    });
    render(<App />); await login(); logout(); await login('fakeB');
    await act(async () => finishLogout(fail(403)));
    expect(screen.getByRole('heading', { name: '현재 가상 계정' })).toBeInTheDocument();
    expect(screen.getAllByText(/가상 B/)).toHaveLength(2);
    navigate('익명 커뮤니티'); await screen.findByText('게시글이(가) 아직 없습니다.');
  });

  it('creates and edits real-name recruitment, distinguishes close from logical cancellation', async () => {
    const template = { id: 'recruit-fixture', owner: { display_name: '가상 모집자' }, is_mine: true, title: '가상 모집', body: '가상 모집 본문', field: '개발', roles: ['디자인'], capacity: 3, accepted_count: 0, deadline_at: '2099-01-01T00:00:00Z', status: 'open', opportunity_id: null, revision: 1, created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z' };
    let rows: typeof template[] = [];
    const fetcher = backend((path, init) => {
      if (path === '/auth/me') return ok(me);
      if (path === '/recruitments' && !init.method) return ok(page(rows));
      if (path === '/recruitments' && init.method === 'POST') { rows = [{ ...template, ...JSON.parse(String(init.body)) }]; return ok(rows[0], 201); }
      if (init.method === 'PATCH') { rows = [{ ...rows[0], ...JSON.parse(String(init.body)), revision: 2 }]; return ok(rows[0]); }
      if (path.endsWith('/close')) { rows = [{ ...rows[0], status: 'closed', revision: 3 }]; return ok(rows[0]); }
      if (init.method === 'DELETE') { rows = []; return ok({ id: template.id, deleted: true }); }
      return fail(503);
    });
    render(<App />); await login(); navigate('팀원 모집'); await screen.findByText('모집글이(가) 아직 없습니다.');
    const create = async () => {
      fireEvent.change(screen.getByLabelText('제목'), { target: { value: '신규 팀 모집' } });
      fireEvent.change(screen.getByLabelText('분야'), { target: { value: '개발' } });
      fireEvent.change(screen.getByLabelText('모집 역할 (쉼표로 구분)'), { target: { value: '디자인' } });
      fireEvent.change(screen.getByLabelText('마감 일시'), { target: { value: '2099-01-01T12:00' } });
      fireEvent.change(screen.getByLabelText('설명'), { target: { value: '함께 구현할 팀원' } });
      fireEvent.click(screen.getByRole('button', { name: '모집글 등록 요청' }));
      await screen.findByRole('heading', { name: '신규 팀 모집' });
    };
    await create(); fireEvent.click(screen.getByRole('button', { name: '수정' }));
    fireEvent.change(within(screen.getByRole('form', { name: '모집글 수정' })).getByLabelText('설명'), { target: { value: '수정한 모집 본문' } });
    fireEvent.click(screen.getByRole('button', { name: '수정 요청' })); await screen.findByText('수정한 모집 본문');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '모집글 취소 · 목록에서 제거' })); await screen.findByText('모집글이(가) 아직 없습니다.');
    expect(fetcher.mock.calls.find(([, init]) => init?.method === 'DELETE')![0]).toContain('/recruitments/recruit-fixture?revision=2');
    await create(); fireEvent.click(screen.getByRole('button', { name: '모집 마감' })); await screen.findByText('마감');
    expect(screen.queryByRole('button', { name: '모집글 취소 · 목록에서 제거' })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([url]) => url.endsWith('/recruitments/recruit-fixture/close'))).toBe(true);
  });

  it('saves an opportunity, updates preparation/checklist and deletes through private authenticated paths', async () => {
    const opportunity = { id: 'opp-fixture', kind: 'scholarship', title: '[가상] 기회', organization: '가상 기관', target_scope: { level: 'school', department_codes: [], academic_years: [] }, apply_starts_at: null, deadline_at: null, deadline_passed: false, submission_mode: 'external_link', source_kind: 'DEMO', needs_verification: true };
    const detail = { ...opportunity, eligibility: '가상 자격', destination: null, original_url: null, source_url: null, checked_at: null, files: [], platform_receives_submission: false };
    let saved: { opportunity_id: string; status: string; memo: string; self_reported_submitted_at: null; revision: number; created_at: string; updated_at: string; checks: { id: string; text: string; sort_order: number; completed_at: string | null; revision: number }[]; opportunity: typeof opportunity }[] = [];
    const fetcher = backend((path, init) => {
      if (path === '/auth/me') return ok(me);
      if (path === '/opportunities') return ok({ items: [opportunity], next_cursor: null });
      if (path === '/opportunities/opp-fixture') return ok(detail);
      if (path === '/me/saved-opportunities') return ok({ items: saved });
      if (path.endsWith('/checks') && init.method === 'POST') { saved[0].checks = [{ id: 'check-fixture', ...JSON.parse(String(init.body)), completed_at: null, revision: 1 }]; return ok(saved[0].checks[0], 201); }
      if (path.endsWith('/checks/check-fixture') && init.method === 'PATCH') { saved[0].checks[0].completed_at = '2026-10-30T00:00:00Z'; saved[0].checks[0].revision++; return ok(saved[0].checks[0]); }
      if (path.endsWith('/checks/check-fixture') && init.method === 'DELETE') { saved[0].checks = []; return ok({ deleted: true }); }
      if (init.method === 'PUT') { saved = [{ opportunity_id: opportunity.id, status: 'interested', memo: '', self_reported_submitted_at: null, revision: 1, created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z', checks: [], opportunity }]; return ok(saved[0], 201); }
      if (init.method === 'PATCH') { saved[0].status = JSON.parse(String(init.body)).status; saved[0].revision++; return ok(saved[0]); }
      if (init.method === 'DELETE') { saved = []; return ok({ deleted: true }); }
      return fail(503);
    });
    render(<App />); await login(); navigate('장학 · 기회'); await screen.findByText('아직 담아 둔 공고가 없습니다.');
    fireEvent.click(screen.getByRole('button', { name: /\[가상\] 기회/ })); await screen.findByRole('heading', { name: opportunity.title });
    fireEvent.click(screen.getByRole('button', { name: '내 준비 목록에 추가' })); await screen.findByRole('button', { name: /준비 중.*변경/ });
    fireEvent.click(screen.getByRole('button', { name: /준비 중.*변경/ })); await screen.findByText('준비 중');
    fireEvent.change(screen.getByLabelText('준비 항목'), { target: { value: '가상 서류 확인' } }); fireEvent.click(screen.getByRole('button', { name: '추가' }));
    const checkbox = await screen.findByLabelText('가상 서류 확인 완료 여부'); fireEvent.click(checkbox); await waitFor(() => expect(screen.getByLabelText('가상 서류 확인 완료 여부')).toBeChecked());
    fireEvent.click(screen.getByRole('button', { name: '삭제' })); await screen.findByText('준비 항목이 없습니다.');
    fireEvent.click(screen.getByRole('button', { name: '목록에서 삭제' })); await screen.findByText('아직 담아 둔 공고가 없습니다.');
    for (const [url, init] of fetcher.mock.calls) {
      const header = new Headers(init?.headers).get('Authorization');
      if (url.includes('/me/')) expect(header).toBe('Bearer token.fakeA');
      if (url.includes('/api/v1/opportunities')) expect(header).toBeNull();
    }
    expect(document.querySelectorAll('main')).toHaveLength(1);
  });
});
