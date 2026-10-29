import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import PublicCampusPage from './index';
import { isGuide, isGuidePage, officialUrl } from './models';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
afterEach(() => vi.resetAllMocks());
const source = {
  url: 'https://www.dit.ac.kr/cs/', site: 'cs', checked_at: '2026-10-30', existence: 'VERIFIED',
  processing_rules: 'PARTIAL', freshness: 'UNKNOWN', evidence: '자동 테스트용 공개 메뉴 확인 설명',
  checked_scope: '도구 반환본 확인이며 원문 수정일과 실시간 최신성은 확인하지 않았습니다.',
};
const card = { id: 'demo-guide', title: '가상 교육과정 안내', category: 'department', summary: '자동 테스트용 편집 요약입니다.', tags: ['가상'], source };
const page = { items: [card], total: 1, offset: 0, limit: 6, snapshot_version: 'public-campus-2026-10-30-v1', notice: '공식 공개 페이지를 참고한 자체 요약입니다.' };
const guide = { ...card, content_kind: 'EDITORIAL_PUBLIC_SUMMARY', feature_ids: ['FR-DEPT-007'], sections: [{ heading: '가상 학습 분야', paragraphs: ['학과 소개와 학기별 이수 판정을 구분합니다.', '<script>private-unsafe</script>'] }] };

describe('공개 대학 안내', () => {
  it('서버 목록을 자체 카드와 출처로 표시한다', async () => {
    vi.mocked(requestData).mockResolvedValue(page);
    render(<PublicCampusPage />);
    expect(await screen.findByRole('heading', { name: card.title })).toBeTruthy();
    expect(screen.getByText(/학교가 운영하는 공식 서비스가 아니며/)).toBeTruthy();
    expect(screen.getByText(/컴퓨터소프트웨어과 · 확인/)).toBeTruthy();
  });

  it('검색과 주제·출처 필터를 서버 요청에 연결한다', async () => {
    vi.mocked(requestData).mockResolvedValue(page);
    render(<PublicCampusPage />);
    await screen.findByRole('heading', { name: card.title });
    fireEvent.change(screen.getByLabelText('안내 검색'), { target: { value: '교육' } });
    fireEvent.change(screen.getByLabelText('주제'), { target: { value: 'department' } });
    fireEvent.change(screen.getByLabelText('자료 출처'), { target: { value: 'cs' } });
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    await waitFor(() => expect(vi.mocked(requestData)).toHaveBeenLastCalledWith(
      '/public-campus?q=%EA%B5%90%EC%9C%A1&offset=0&limit=6&category=department&site=cs',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('상세 본문을 안전한 텍스트로 열고 원문 확인 범위를 표시한다', async () => {
    vi.mocked(requestData).mockImplementation(async path => path.includes('?') ? page : guide);
    const { container } = render(<PublicCampusPage />);
    fireEvent.click(await screen.findByRole('button', { name: `${card.title} 내용 읽기` }));
    expect(await screen.findByRole('heading', { name: '가상 학습 분야' })).toBeTruthy();
    expect(screen.getByText('<script>private-unsafe</script>')).toBeTruthy();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(/최신성 미검증/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /공식 원문 확인/ }).getAttribute('rel')).toBe('noopener noreferrer');
    fireEvent.click(screen.getByRole('button', { name: /목록으로 돌아가기/ }));
    expect(screen.getByRole('heading', { name: card.title })).toBeTruthy();
  });

  it('빈 결과와 서버 오류를 구분하며 원문 오류를 노출하지 않는다', async () => {
    vi.mocked(requestData).mockResolvedValue({ ...page, items: [], total: 0 });
    render(<PublicCampusPage />);
    expect(await screen.findByText(/일치하는 안내가 없습니다/)).toBeTruthy();
    vi.mocked(requestData).mockRejectedValue(new Error('private-password'));
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('private-password')).toBeNull();
    expect(screen.getByRole('button', { name: '목록 다시 확인' })).toBeTruthy();
  });

  it('오염된 출처와 잘못된 응답을 거부한다', async () => {
    expect(officialUrl('https://u:p@www.dit.ac.kr/cs/')).toBe(false);
    expect(officialUrl('https://evil.example/cs/')).toBe(false);
    expect(officialUrl('https://www.dit.ac.kr/cs/?token=secret')).toBe(false);
    expect(isGuide({ ...guide, source: { ...source, freshness: 'VERIFIED' } })).toBe(false);
    expect(isGuidePage({ ...page, total: -1 })).toBe(false);
    vi.mocked(requestData).mockResolvedValue({ data: 'unexpected-private-record' });
    render(<PublicCampusPage />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('unexpected-private-record')).toBeNull();
  });

  it('화면 종료 시 진행 중인 요청을 취소한다', () => {
    let signal: AbortSignal | null = null;
    vi.mocked(requestData).mockImplementation((_path, init) => { signal = init?.signal as AbortSignal; return new Promise(() => {}); });
    const view = render(<PublicCampusPage />);
    view.unmount();
    expect((signal as AbortSignal | null)?.aborted).toBe(true);
  });

  it('페이지 이동은 아직 제출하지 않은 필터를 섞지 않는다', async () => {
    vi.mocked(requestData).mockResolvedValue({ ...page, total: 7 });
    render(<PublicCampusPage />);
    await screen.findByRole('heading', { name: card.title });
    fireEvent.change(screen.getByLabelText('안내 검색'), { target: { value: '아직 제출 안 함' } });
    fireEvent.change(screen.getByLabelText('자료 출처'), { target: { value: 'cs' } });
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    await waitFor(() => expect(vi.mocked(requestData)).toHaveBeenLastCalledWith(
      '/public-campus?q=&offset=6&limit=6', expect.any(Object),
    ));
  });
});
