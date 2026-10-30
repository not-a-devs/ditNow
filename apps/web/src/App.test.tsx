import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { navigation } from './navigation';

vi.mock('./features/demo-attendance', () => ({ default: ({ sessionGeneration }: { sessionGeneration: number }) => <p>mock-attendance:{sessionGeneration}</p> }));
vi.mock('./features/demo-services', () => ({ default: ({ sessionGeneration }: { sessionGeneration: number | string }) => <p>mock-services:{sessionGeneration}</p> }));
vi.mock('./features/demo-profile', () => ({ default: ({ sessionGeneration }: { sessionGeneration?: number }) => <p>mock-profile:{sessionGeneration}</p> }));
vi.mock('./features/demo-action-center', () => ({ default: ({ sessionGeneration }: { sessionGeneration: number }) => <p>mock-action-center:{sessionGeneration}</p> }));
vi.mock('./features/demo-channels', () => ({ default: ({ sessionGeneration }: { sessionGeneration?: number }) => <p>mock-channels:{sessionGeneration}</p> }));

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

describe('release-visible navigation boundary', () => {
  it.each(['academic', 'classrooms', 'department', 'support'].flatMap(id => [`/app/${id}`, `/app/${id}/`]))('replaces hidden direct route %s before any feature or request mounts', path => {
    window.history.replaceState(null, '', path);
    const before = window.history.length;
    const fetcher = demoBackend();
    const replace = vi.spyOn(window.history, 'replaceState');
    const push = vi.spyOn(window.history, 'pushState');
    render(<App />);
    expect(window.location.pathname).toBe('/app');
    expect(screen.getByRole('heading', { name: /이번 학기도/ })).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith(null, '', '/app');
    expect(push).not.toHaveBeenCalled();
    expect(window.history.length).toBe(before);
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.queryByText(/mock-/)).toBeNull();
  });
  it('replaces hidden popstate entries without pushing another history entry', () => {
    const fetcher = demoBackend(); render(<App />);
    for (const id of ['academic', 'classrooms', 'department', 'support']) {
      window.history.replaceState(null, '', `/app/${id}/`);
      const before = window.history.length;
      fireEvent.popState(window);
      expect(window.location.pathname).toBe('/app');
      expect(window.history.length).toBe(before);
      expect(screen.getByRole('heading', { name: /이번 학기도/ })).toBeInTheDocument();
    }
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('keeps authenticated Home and account free of memory demos, including hidden popstate routes', async () => {
    const fetcher = demoBackend(); render(<App />); await demoLogin();
    expect(screen.getByText('가상 A · DEMO')).toBeInTheDocument();
    expect(screen.queryByText(/mock-/)).toBeNull();
    openSection('home');
    expect(screen.queryByLabelText('가상 액션 센터')).toBeNull();
    for (const id of ['academic', 'classrooms', 'department', 'support']) {
      window.history.pushState(null, '', `/app/${id}/`); fireEvent.popState(window);
      expect(window.location.pathname).toBe('/app');
      expect(screen.queryByText(/mock-/)).toBeNull();
    }
    expect(privateCalls(fetcher)).toHaveLength(0);
    expect(fetcher.mock.calls.map(([url]) => new URL(String(url)).pathname)).toEqual(['/api/v1/auth/login', '/api/v1/auth/me']);
    fireEvent.click(screen.getAllByRole('button', { name: '로그아웃' })[0]);
    await screen.findByText('로그인되지 않음');
    expect(privateCalls(fetcher)).toHaveLength(0);
  });
  it('uses the same available destinations in Home quick cards and mobile navigation', () => {
    render(<App />);
    const quick = screen.getByRole('region', { name: '나의 캠퍼스로 바로' });
    const labels = ['익명 커뮤니티', '팀원 모집', '장학 · 기회', 'AI 도우미'];
    expect(Array.from(quick.querySelectorAll('strong'), el => el.textContent)).toEqual(labels);
    const mobile = screen.getByRole('navigation', { name: '빠른 메뉴' });
    expect(within(mobile).getAllByRole('button').map(button => button.querySelector('span:last-child')?.textContent)).toEqual(['홈', ...labels.slice(0, 3), '전체 메뉴']);
    const destinations = ['community', 'recruitments', 'opportunities', 'ai'];
    for (let i = 0; i < destinations.length; i++) {
      fireEvent.click(within(screen.getByRole('region', { name: '나의 캠퍼스로 바로' })).getAllByRole('button')[i]);
      expect(window.location.pathname).toBe(`/app/${destinations[i]}`);
      if (i < 3) expect(screen.getByText('로그인이 필요한 화면입니다')).toBeInTheDocument();
      openSection('home');
    }
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
    expect(within(menu).getAllByRole('link')).toHaveLength(8);
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
    expect(screen.getByRole('heading', { name: /이번 학기도/ })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/app');
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
  const expectHomeActionsAndStatusAbsent = () => {
    expect(screen.queryByText('MY ACTIONS')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '내가 챙길 일' })).not.toBeInTheDocument();
    expect(screen.queryByText('나만의 하루를 준비하고 있어요')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '공개 서버 연결 확인' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '연결 확인' })).not.toBeInTheDocument();
  };
  it('does not mount Home MY ACTIONS or server status for anonymous visitors', () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    render(<App />);
    expectHomeActionsAndStatusAbsent();
    expect(screen.getByText('BETTER TOGETHER')).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => /\/health|\/me\/demo/.test(String(url)))).toHaveLength(0);
  });
  it('does not mount Home MY ACTIONS or server status after mocked login', async () => {
    const fetcher = demoBackend();
    render(<App />);
    await demoLogin();
    openSection('home');
    expectHomeActionsAndStatusAbsent();
    expect(fetcher.mock.calls.filter(([url]) => /\/health|\/me\/demo/.test(String(url)))).toHaveLength(0);
  });
});
