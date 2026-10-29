import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import PublicCampusPage from './index';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
const source = { url: 'https://www.dit.ac.kr/cs/', site: 'cs', checked_at: '2026-10-30', existence: 'VERIFIED',
  processing_rules: 'PARTIAL', freshness: 'UNKNOWN', evidence: '가상 테스트 근거', checked_scope: '테스트 반환본' };
const guide = { id: 'demo-guide', title: '가상 상세 안내', category: 'department', summary: '자동 테스트용 안내', tags: [], source,
  content_kind: 'EDITORIAL_PUBLIC_SUMMARY', feature_ids: ['FR-DEPT-007'], sections: [{ heading: '학습 안내', paragraphs: ['가상 설명'] }] };
const empty = { items: [], total: 0, offset: 0, limit: 6, snapshot_version: 'public-campus-2026-10-30-v1', notice: '공개 편집 요약' };

describe('공개 안내 검색 결과의 상세 링크', () => {
  it('ID로 상세를 직접 열고 목록 복귀 시 실제 목록을 불러온다', async () => {
    vi.mocked(requestData).mockImplementation(async path => path.includes('?') ? empty : guide);
    window.history.replaceState(null, '', '/app/information?guide=demo-guide');
    render(<PublicCampusPage />);
    expect(await screen.findByRole('heading', { name: '학습 안내' })).toBeInTheDocument();
    expect(requestData).toHaveBeenCalledWith('/public-campus/demo-guide', expect.anything());
    fireEvent.click(screen.getByRole('button', { name: /목록으로 돌아가기/ }));
    expect(await screen.findByText(/일치하는 안내가 없습니다/)).toBeInTheDocument();
  });
  it('경로를 바꾸는 ID는 상세 요청에 사용하지 않는다', async () => {
    vi.mocked(requestData).mockReset().mockResolvedValue(empty);
    window.history.replaceState(null, '', '/app/information?guide=..%2Fprivate');
    render(<PublicCampusPage />);
    await screen.findByText(/일치하는 안내가 없습니다/);
    expect(vi.mocked(requestData).mock.calls.every(([path]) => path.startsWith('/public-campus?'))).toBe(true);
  });
});
