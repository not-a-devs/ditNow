// UI states against the real shared transport (fetch stubbed). jsdom/RTL only — this is not a
// browser, DB or mounted-App verification.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CareersPage from './index';

const RID = '12345678-1234-1234-1234-123456789012';
const PID = '00000000-0000-4000-8000-0000000000a1';
const JOB = {
  id: '00000000-0000-4000-8000-000000000001', title: '[DEMO] 가상 백엔드 인턴', organization: '가상 기업',
  department_codes: [], apply_starts_at: null, deadline_at: '2026-11-06T03:00:00Z', deadline_passed: false,
  provenance: 'DEMO', original_url: null, checked_at: null, platform_receives_application: false,
};
const PROGRAM = {
  id: PID, title: '[DEMO] 가상 취업 캠프', host: '가상 진로지원팀', summary: '시연', capacity: 2,
  apply_starts_at: null, apply_ends_at: '2026-11-06T03:00:00Z', window_open: true, provenance: 'DEMO',
  source_url: null, checked_at: null, accepts_virtual_application: true,
};
const PROFILE = {
  id: '00000000-0000-4000-8000-0000000000b1', alias: '별빛개발자', desired_roles: ['백엔드'], skills: ['Python'],
  summary: '', revision: 1, created_at: '2026-10-30T03:00:00Z', updated_at: '2026-10-30T03:00:00Z', shared_with: [], is_virtual: true,
};
const APPLICATION = {
  id: '00000000-0000-4000-8000-0000000000c1', program_id: PID, status: 'applied', note: '', revision: 1,
  created_at: '2026-10-30T03:00:00Z', updated_at: '2026-10-30T03:00:00Z', cancelled_at: null,
  review_status: 'not_reviewed', is_virtual: true, program: PROGRAM,
};

type Reply = { status: number; body: unknown } | 'pending' | 'network' | Promise<Response>;
type Handler = (method: string, path: string, init: RequestInit) => Reply | undefined;

const ok = (data: unknown): Reply => ({ status: 200, body: { data } });
const fail = (status: number, code: string): Reply => ({ status, body: { code, message: 'x', retryable: false, request_id: RID } });

// Default healthy server; each test overrides selected routes.
function stub(override: Handler = () => undefined) {
  const fetch = vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    const path = new URL(url).pathname;
    const reply = override(method, path, init) ?? defaults(method, path);
    if (reply instanceof Promise) return reply;
    if (reply === 'pending') return new Promise<Response>(() => {});
    if (reply === 'network') return Promise.reject(new TypeError('offline'));
    return Promise.resolve(new Response(JSON.stringify(reply.body), { status: reply.status }));
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function defaults(method: string, path: string): Reply {
  if (path.endsWith('/careers/jobs')) return ok({ items: [JOB], next_cursor: null });
  if (path.endsWith('/careers/contests')) return ok({ items: [], next_cursor: null });
  if (path.endsWith('/careers/me/profile') && method === 'GET') return ok({ profile: PROFILE });
  if (path.endsWith('/careers/programs')) return ok({ items: [PROGRAM], policy_id: 'demo-careers-20261030', policy_basis: 'DEMO' });
  if (path.endsWith('/careers/me/program-applications')) return ok({ items: [] });
  if (path.endsWith('/careers/employer-requests') && method === 'GET') return fail(403, 'FORBIDDEN');
  return fail(500, 'INTERNAL');
}

const posts = (fetch: ReturnType<typeof stub>, suffix: string) =>
  fetch.mock.calls
    .filter(([url, init]) => init?.method === 'POST' && new URL(url as string).pathname.endsWith(suffix))
    .map(([, init]) => ({ key: (init!.headers as Record<string, string>)['Idempotency-Key'], body: JSON.parse(init!.body as string) }));

describe('CareersPage', () => {
  it('shows loading states while requests are pending', () => {
    stub(() => 'pending');
    render(<CareersPage />);
    expect(screen.getByText('공고를 불러오는 중…')).toBeInTheDocument();
    expect(screen.getByText('내 진로 요약을 불러오는 중…')).toBeInTheDocument();
  });

  it('shows not-ready on 503 everywhere without fake data', async () => {
    stub(() => fail(503, 'UNAVAILABLE'));
    render(<CareersPage />);
    expect((await screen.findAllByText('서버 연결 준비 중입니다. 아직 이용할 수 없습니다.')).length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText(JOB.title)).not.toBeInTheDocument();
  });

  it('renders empty lists and retries the job list after a network error', async () => {
    let attempts = 0;
    stub((_m, path) => {
      if (path.endsWith('/careers/jobs')) return ++attempts === 1 ? 'network' : ok({ items: [], next_cursor: null });
      return undefined;
    });
    render(<CareersPage />);
    expect(await screen.findByText('연결할 수 있는 공모전이 없습니다.')).toBeInTheDocument();
    const alert = await screen.findByText('서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.');
    fireEvent.click(within(alert.closest('[role=alert]') as HTMLElement).getByText('다시 시도'));
    expect(await screen.findByText('조건에 맞는 공고가 없습니다.')).toBeInTheDocument();
  });

  it('401 removes every private panel and shows the parent notice, public lists stay', async () => {
    stub((_m, path) => (path.includes('/me/') || path.endsWith('/employer-requests') ? fail(401, 'UNAUTHORIZED') : undefined));
    render(<CareersPage />);
    expect(await screen.findByText(/로그인이 필요합니다\. 공통 로그인이 연결되기 전/)).toBeInTheDocument();
    expect(screen.getByText(`요청 ID: ${RID}`)).toBeInTheDocument();
    expect(await screen.findByText(JOB.title)).toBeInTheDocument();
    expect(screen.queryByText('가상 진로·이력 요약')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(PROFILE.alias)).not.toBeInTheDocument();
    expect(screen.queryByText('내 가상 신청')).not.toBeInTheDocument();
    expect(screen.queryByText('가상 신청')).not.toBeInTheDocument();
  });

  it('403 removes only the employer panel and names it in the parent notice', async () => {
    stub();
    render(<CareersPage />);
    expect(await screen.findByText(/기업 채용의뢰 초안: 이 계정에는 권한이 없어/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '기업 채용의뢰 초안' })).not.toBeInTheDocument();
    expect(await screen.findByDisplayValue(PROFILE.alias)).toBeInTheDocument();
  });

  it('removes already-loaded personal data when a later private call returns 401', async () => {
    stub((method, path) => (method === 'PATCH' && path.endsWith('/me/profile') ? fail(401, 'UNAUTHORIZED') : undefined));
    render(<CareersPage />);
    const alias = await screen.findByDisplayValue(PROFILE.alias);
    fireEvent.change(alias, { target: { value: '새별칭' } });
    fireEvent.click(screen.getByText('수정 저장'));
    expect(await screen.findByText(/로그인이 필요합니다/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue('새별칭')).not.toBeInTheDocument();
    expect(screen.queryByText('저장했습니다. 본인만 볼 수 있는 가상 기록입니다.')).not.toBeInTheDocument();
  });

  it('403 on applications discards notes and my applications; recheck remounts from empty state', async () => {
    let denied = true;
    const fetch = stub((method, path) => {
      if (path.endsWith('/applications') && method === 'POST') return denied ? fail(403, 'FORBIDDEN') : undefined;
      if (path.endsWith('/me/program-applications')) return ok({ items: [{ ...APPLICATION, id: '00000000-0000-4000-8000-0000000000c2', program_id: '00000000-0000-4000-8000-0000000000a2', program: null }] });
      return undefined;
    });
    render(<CareersPage />);
    const note = await screen.findByLabelText(`${PROGRAM.title} 메모`);
    expect(await screen.findByText('비공개로 전환된 프로그램')).toBeInTheDocument();
    fireEvent.change(note, { target: { value: '개인 메모' } });
    fireEvent.click(screen.getByText('가상 신청'));

    expect(await screen.findByText(/프로그램 가상 신청: 이 계정에는 권한이 없어/)).toBeInTheDocument();
    // Personal parts are unmounted, the public program card stays.
    expect(screen.getByText(PROGRAM.title)).toBeInTheDocument();
    expect(screen.queryByLabelText(`${PROGRAM.title} 메모`)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('개인 메모')).not.toBeInTheDocument();
    expect(screen.queryByText('내 가상 신청')).not.toBeInTheDocument();
    expect(screen.queryByText('비공개로 전환된 프로그램')).not.toBeInTheDocument();
    expect(await screen.findByDisplayValue(PROFILE.alias)).toBeInTheDocument(); // other panel unaffected

    denied = false;
    const listsBefore = fetch.mock.calls.filter(([url]) => String(url).endsWith('/me/program-applications')).length;
    // The employer panel is also 403 by default; recheck only the applications area.
    fireEvent.click(within(screen.getByText(/프로그램 가상 신청: 이 계정에는/)).getByText('권한 다시 확인'));
    // Fresh mount: list fetched again, note input empty (old state was discarded, not hidden).
    expect(await screen.findByLabelText(`${PROGRAM.title} 메모`)).toHaveValue('');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/me/program-applications')).length).toBe(listsBefore + 1),
    );
  });

  it('drops a late apply success after 401 and makes no follow-up request; login recheck recovers', async () => {
    let finishApply: (r: Response) => void = () => {};
    const applyReply = new Promise<Response>((resolve) => { finishApply = resolve; });
    let loggedOut = false;
    const fetch = stub((method, path) => {
      if (path.endsWith('/applications') && method === 'POST') return applyReply;
      if (path.endsWith('/me/profile') && method === 'PATCH') { loggedOut = true; return fail(401, 'UNAUTHORIZED'); }
      if (loggedOut && (path.includes('/me/') || path.endsWith('/employer-requests'))) return fail(401, 'UNAUTHORIZED');
      return undefined;
    });
    render(<CareersPage />);
    fireEvent.change(await screen.findByLabelText(`${PROGRAM.title} 메모`), { target: { value: '늦은 메모' } });
    fireEvent.click(screen.getByText('가상 신청')); // stays pending
    fireEvent.change(await screen.findByDisplayValue(PROFILE.alias), { target: { value: '새별칭' } });
    fireEvent.click(screen.getByText('수정 저장'));
    expect(await screen.findByText(/로그인이 필요합니다/)).toBeInTheDocument();
    expect(screen.queryByText('내 가상 신청')).not.toBeInTheDocument();

    const listCalls = () => fetch.mock.calls.filter(([url]) => String(url).endsWith('/me/program-applications')).length;
    const before = listCalls();
    finishApply(new Response(JSON.stringify({ data: APPLICATION }), { status: 201 }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByText(/가상 신청을 기록했습니다/)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('늦은 메모')).not.toBeInTheDocument();
    expect(listCalls()).toBe(before); // no follow-up personal fetch from the discarded panel

    loggedOut = false;
    fireEvent.click(screen.getByText('로그인 상태 다시 확인'));
    expect(await screen.findByDisplayValue(PROFILE.alias)).toBeInTheDocument();
    expect(await screen.findByLabelText(`${PROGRAM.title} 메모`)).toHaveValue('');
    expect(screen.queryByText(/가상 신청을 기록했습니다/)).not.toBeInTheDocument();
  });

  it('keeps the form, reuses the key for the same input and rotates it when input changes', async () => {
    let attempt = 0;
    const fetch = stub((method, path) => {
      if (path.endsWith('/me/profile') && method === 'GET') return ok({ profile: null });
      if (path.endsWith('/me/profile') && method === 'POST') return ++attempt < 3 ? 'network' : ok(PROFILE);
      return undefined;
    });
    render(<CareersPage />);
    const alias = await screen.findByLabelText('가상 별칭');
    fireEvent.change(alias, { target: { value: '별빛' } });
    fireEvent.click(screen.getByText('작성'));
    expect(await screen.findByText('서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('가상 별칭')).toHaveValue('별빛'); // form preserved
    expect(screen.queryByRole('status')).not.toBeInTheDocument(); // no false success

    await waitFor(() => expect(screen.getByText('작성')).not.toBeDisabled());
    fireEvent.click(screen.getByText('작성')); // same input → same key
    await waitFor(() => expect(posts(fetch, '/me/profile')).toHaveLength(2));
    fireEvent.change(screen.getByLabelText('가상 별칭'), { target: { value: '별빛개발자' } });
    await screen.findByText('서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.');
    await waitFor(() => expect(screen.getByText('작성')).not.toBeDisabled());
    fireEvent.click(screen.getByText('작성')); // changed input → new key
    expect(await screen.findByText('저장했습니다. 본인만 볼 수 있는 가상 기록입니다.')).toBeInTheDocument();

    const [first, second, third] = posts(fetch, '/me/profile');
    expect(second.key).toBe(first.key);
    expect(third.key).not.toBe(first.key);
    expect(third.body.alias).toBe('별빛개발자');
  });

  it('does not show success when the server reply fails the runtime guard', async () => {
    stub((method, path) => {
      if (path.endsWith('/applications') && method === 'POST') return ok({ ...APPLICATION, review_status: 'accepted' });
      return undefined;
    });
    render(<CareersPage />);
    fireEvent.click(await screen.findByText('가상 신청'));
    expect(await screen.findByText('서버 응답 형식이 올바르지 않아 표시하지 않았습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/가상 신청을 기록했습니다/)).not.toBeInTheDocument();
  });

  it('records a virtual application and labels it as not a real review', async () => {
    let applied = false;
    const fetch = stub((method, path) => {
      if (path.endsWith('/applications') && method === 'POST') { applied = true; return { status: 201, body: { data: APPLICATION } }; }
      if (path.endsWith('/me/program-applications')) return ok({ items: applied ? [APPLICATION] : [] });
      return undefined;
    });
    render(<CareersPage />);
    expect(await screen.findByText('적용 규칙: 가상 시연 정책 demo-careers-20261030 (학교 규정 아님)')).toBeInTheDocument();
    fireEvent.click(await screen.findByText('가상 신청'));
    expect(await screen.findByText('가상 신청을 기록했습니다. 실제 접수·선정이 아닙니다.')).toBeInTheDocument();
    expect(await screen.findByText(/가상 신청함 · 심사 없음\(시연\)/)).toBeInTheDocument();
    expect(posts(fetch, '/applications')[0].key).toMatch(/^apply-/);
  });

  it('renders hostile text as text and never links non-https URLs', async () => {
    const hostile = { ...JOB, title: '<img src=x onerror=alert(1)>', original_url: 'javascript:alert(1)' };
    stub((_m, path) => (path.endsWith('/careers/jobs') ? ok({ items: [hostile], next_cursor: null }) : undefined));
    const { container } = render(<CareersPage />);
    expect(await screen.findByText(hostile.title)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it('shows provenance labels: official needs link and date, otherwise unknown', async () => {
    const official = { ...JOB, id: '00000000-0000-4000-8000-000000000002', title: '공식', provenance: 'OFFICIAL_PUBLIC', original_url: 'https://job.dit.ac.kr/page/main/', checked_at: '2026-10-29T00:00:00Z' };
    const claimed = { ...JOB, id: '00000000-0000-4000-8000-000000000003', title: '주장만', provenance: 'OFFICIAL_PUBLIC', original_url: null, checked_at: null };
    stub((_m, path) => (path.endsWith('/careers/jobs') ? ok({ items: [official, claimed], next_cursor: null }) : undefined));
    render(<CareersPage />);
    expect(await screen.findByText(/공개 원문 · 확인/)).toBeInTheDocument();
    expect(screen.getAllByText('출처 미확인 — 원문 확인 필요')).toHaveLength(1);
    expect(screen.getByText('원문 열기').getAttribute('href')).toBe('https://job.dit.ac.kr/page/main/');
  });
});
