import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('integrated campus shell', () => {
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
    expect(within(menu).getAllByRole('link')).toHaveLength(10);
    expect(screen.getByRole('heading', { name: /이번 학기도,\s*나답게\./ })).toBeInTheDocument();
  });
  it('changes route and clearly marks unfinished functionality', () => {
    render(<App />);
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    fireEvent.click(within(menu).getByRole('link', { name: '익명 커뮤니티' }));
    expect(window.location.pathname).toBe('/app/community');
    expect(screen.getByRole('heading', { name: '익명 커뮤니티' })).toBeInTheDocument();
    expect(screen.getByText('이 기능은 아직 연결되지 않았어요')).toBeInTheDocument();
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
