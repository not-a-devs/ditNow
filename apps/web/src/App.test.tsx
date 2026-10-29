import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('integrated campus shell', () => {
  it('shows public status and all platform navigation without claiming authentication', () => {
    render(<App />);
    expect(screen.getByText('로그인되지 않음')).toBeInTheDocument();
    const menu = screen.getByRole('navigation', { name: '캠퍼스 전체 메뉴' });
    expect(within(menu).getAllByRole('link')).toHaveLength(9);
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
});
