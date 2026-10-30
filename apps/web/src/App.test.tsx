import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { navigation } from './navigation';

vi.mock('./features/demo-attendance', () => ({ default: ({ sessionGeneration }: { sessionGeneration: number }) => <p>mock-attendance:{sessionGeneration}</p> }));
vi.mock('./features/demo-services', () => ({ default: ({ sessionGeneration }: { sessionGeneration: number | string }) => <p>mock-services:{sessionGeneration}</p> }));

const demoMe = (name: string) => ({ user_id: name === '가상 B' ? '10000000-0000-4000-8000-000000000002' : '10000000-0000-4000-8000-000000000001', display_name: name, record_source: 'DEMO', department_id: '20000000-0000-4000-8000-000000000001', department_code: 'DEMO', academic_year: 1, community_access: true });
const demoOk = (data: unknown) => new Response(JSON.stringify({ data }), { status: 200 });
function demoBackend(meHandler: () => Promise<Response> | Response = () => demoOk(demoMe('가상 A'))) {
  const fetcher = vi.fn((url: string, init: RequestInit = {}) => {
    const path = new URL(url).pathname.replace('/api/v1', '');
    if (path === '/auth/login') { const input = JSON.parse(String(init.body)); return Promise.resolve(demoOk({ token: `token.${input.student_id}`, token_type: 'Bearer', student_id: input.student_id, name: '가상 이름', record_source: 'DEMO' })); }
    if (path === '/auth/me') return Promise.resolve(meHandler());
    if (path === '/auth/logout') return Promise.resolve(demoOk({ status: 'ok' }));
    return Promise.resolve(demoOk({ items: [], offset: 0, limit: 20, has_more: false }));
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
function openSection(id: string) { fireEvent.click(within(screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' })).getByRole('link', { name: navigation.find(item => item.id === id)!.label })); }
async function demoLogin(id = 'fakeA') {
  openSection('login');
  fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: id } });
  fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'synthetic-password' } });
  fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
  await screen.findByRole('heading', { name: '현재 가상 계정' });
}
const privateCalls = (fetcher: ReturnType<typeof vi.fn>) => fetcher.mock.calls.filter(([url]) => /\/me\/demo-/.test(String(url)));

describe('demo platform route integration', () => {
  it('shows public travel on academic but keeps private attendance unmounted while anonymous', () => {
    window.history.pushState(null, '', '/app');
    const fetcher = demoBackend();
    render(<App />);
    openSection('academic');
    expect(screen.getByRole('heading', { name: '강의 간 이동 여유 계산' })).toBeInTheDocument();
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    expect(screen.queryByText(/mock-attendance/)).toBeNull();
    expect(privateCalls(fetcher)).toHaveLength(0);
    vi.unstubAllGlobals();
  });

  it('does not mount support services while identity is still being checked', async () => {
    window.history.pushState(null, '', '/app');
    let release: (response: Response) => void = () => undefined;
    const fetcher = demoBackend(() => new Promise<Response>(resolve => { release = resolve; }));
    render(<App />);
    openSection('login');
    fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: 'fakeA' } });
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'synthetic-password' } });
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith('/auth/me'))).toBe(true));
    openSection('support');
    expect(screen.queryByText(/mock-services/)).toBeNull();
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    expect(privateCalls(fetcher)).toHaveLength(0);
    release(demoOk(demoMe('가상 A')));
    expect(await screen.findByText(/mock-services:/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('mounts private modules with the verified generation and unmounts them on user switch and logout', async () => {
    window.history.pushState(null, '', '/app');
    let name = '가상 A'; demoBackend(() => demoOk(demoMe(name)));
    render(<App />);
    await demoLogin('fakeA');
    openSection('academic');
    const first = (await screen.findByText(/mock-attendance:/)).textContent;
    expect(screen.getByRole('heading', { name: '강의 간 이동 여유 계산' })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '로그아웃' })[0]);
    await waitFor(() => expect(screen.queryByText(/mock-attendance/)).toBeNull());
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    name = '가상 B'; await demoLogin('fakeB');
    openSection('academic');
    const second = (await screen.findByText(/mock-attendance:/)).textContent;
    expect(screen.getByText('가상 B')).toBeInTheDocument();
    expect(second).not.toBe(first);
    openSection('support');
    expect(await screen.findByText(/mock-services:/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '로그아웃' })[0]);
    await waitFor(() => expect(screen.queryByText(/mock-services/)).toBeNull());
    vi.unstubAllGlobals();
  });

  it('keeps public campus information and adds data provenance', () => {
    window.history.pushState(null, '', '/app');
    demoBackend();
    render(<App />);
    openSection('information');
    expect(screen.getByRole('heading', { name: '대학·학과 정보' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '자료 출처 표시 안내' })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe('integrated campus shell', () => {
  it('connects global search to the public feature without exposing personal records', () => {
    window.history.replaceState(null, '', '/app/search');
    render(<App />);
    expect(screen.getByRole('heading', { name: '통합 검색' })).toBeInTheDocument();
    expect(screen.getByText(/개인 시간표·성적·신청·대화 검색은 아직/)).toBeInTheDocument();
  });
  it('connects the public information menu to the live API namespace', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {
      items: [], total: 0, offset: 0, limit: 6,
      snapshot_version: 'public-campus-2026-10-30-v1', notice: '공개 편집 요약',
    } }), { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    window.history.replaceState(null, '', '/app/information');
    render(<App />);
    expect(screen.getByRole('heading', { name: '대학·학과 정보' })).toBeInTheDocument();
    expect(await screen.findByText('일치하는 안내가 없습니다. 검색어나 분류를 바꿔 보세요.')).toBeInTheDocument();
    expect(new URL(fetcher.mock.calls[0][0]).pathname).toBe('/api/v1/public-campus');
  });
  it('connects the AI menu to the campus search feature', () => {
    window.history.replaceState(null, '', '/app/ai');
    render(<App />);
    expect(screen.getByRole('heading', { name: '어디를 찾고 있나요?' })).toBeInTheDocument();
    expect(screen.getByLabelText('시설 이름 또는 질문')).toBeInTheDocument();
    expect(screen.getByText(/개인 시간표·성적 안내/)).toBeInTheDocument();
  });
  it('shows public status and all platform navigation without claiming authentication', () => {
    render(<App />);
    expect(screen.getByText('로그인되지 않음')).toBeInTheDocument();
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    expect(within(menu).getAllByRole('link')).toHaveLength(12);
    expect(screen.getByRole('heading', { name: /이번 학기도,\s*나답게\./ })).toBeInTheDocument();
  });
  it('changes route and clearly marks unfinished functionality', () => {
    render(<App />);
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    fireEvent.click(within(menu).getByRole('link', { name: '익명 커뮤니티' }));
    expect(window.location.pathname).toBe('/app/community');
    expect(screen.getByRole('heading', { name: '익명 커뮤니티' })).toBeInTheDocument();
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    expect(within(menu).getByRole('link', { name: '익명 커뮤니티' })).toHaveAttribute('aria-current', 'page');
  });
  it('honors browser back navigation and handles unknown pages', () => {
    window.history.replaceState(null, '', '/missing');
    render(<App />);
    expect(screen.getByText('페이지를 찾을 수 없어요')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '캠퍼스 홈으로 이동' }));
    window.history.replaceState(null, '', '/app/classrooms');
    fireEvent.popState(window);
    expect(screen.getByRole('heading', { name: '내 강의실' })).toBeInTheDocument();
  });
  it('offers all-menu toggle controls for mobile navigation', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    expect(screen.getByRole('button', { name: '전체 메뉴 닫기' })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: '전체 메뉴 닫기' }));
    expect(screen.getByRole('button', { name: '전체 메뉴 열기' })).toHaveAttribute('aria-expanded', 'false');
  });
  it.each(['header', 'bottom'])('focuses the first navigation link and returns to the %s trigger on Escape', source => {
    render(<App />);
    const trigger = source === 'header' ? screen.getByRole('button', { name: '전체 메뉴 열기' }) : screen.getByRole('button', { name: '전체 메뉴' });
    trigger.focus(); fireEvent.click(trigger);
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    const first = within(menu).getAllByRole('link')[0];
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: 'Escape' });
    expect(trigger).toHaveFocus(); expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });
  it('keeps route navigation focus on main instead of restoring the old menu trigger', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    fireEvent.click(within(menu).getByRole('link', { name: '익명 커뮤니티' }));
    expect(screen.getByRole('main')).toHaveFocus();
    expect(screen.getByRole('button', { name: '전체 메뉴 열기' })).toHaveAttribute('aria-expanded', 'false');
    expect(window.location.pathname).toBe('/app/community');
  });
  it('keeps Korean words together in the AI heading without changing its label', () => {
    window.history.replaceState(null, '', '/app/ai'); render(<App />);
    expect(screen.getByRole('heading', { name: '캠퍼스 기회·준비 도우미' })).toHaveStyle({ wordBreak: 'keep-all', textWrap: 'balance' });
    expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
    expect(screen.getByLabelText('시설 이름 또는 질문')).toBeInTheDocument();
    expect(document.querySelector('p p')).toBeNull();
  });
  it('checks actual health and distinguishes liveness from database readiness', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { status: 'ok', service: 'ditnow-api' } }), { status: 200 })));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '연결 확인' }));
    expect(await screen.findByText('공개 서버가 응답했습니다. 인증·DB 연결 상태는 확인하지 않습니다.')).toBeInTheDocument();
  });
  it('provides a retry action on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('secret')));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '연결 확인' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('secret');
    expect(screen.getByRole('button', { name: '다시 확인' })).toBeEnabled();
  });
  it.each([null, {}, { status: 'unknown', service: 'ditnow-api' }, { status: 'ok', service: 'other' }])('rejects invalid health data before showing success: %j', async data => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data }), { status: 200 })));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '연결 확인' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('공개 서버가 응답했습니다. 인증·DB 연결 상태는 확인하지 않습니다.')).not.toBeInTheDocument();
  });
});
