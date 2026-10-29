import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import PublicDiscoveryPage from './index';
import { isPage, type Item, type Page } from './models';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const guide = (index = 0): Item => ({
  id: `guide:demo-${index}`, kind: 'guide', title: `가상 대학 안내 ${index}`, summary: '테스트 전용 안내',
  detail_path: `/app/information?guide=demo-${index}`,
  source: { kind: 'official_summary', snapshot_version: 'public-campus-2026-10-30-v1', evidence: {
    url: 'https://www.dit.ac.kr/kr/', site: 'university', checked_at: '2026-10-30', existence: 'VERIFIED',
    processing_rules: 'PARTIAL', freshness: 'UNKNOWN', evidence: '가상 테스트 근거', checked_scope: '페이지 확인 테스트',
  } },
});
const facility: Item = { id: 'facility:demo-library', kind: 'facility', title: '가상 시설', summary: '가상 시설 설명',
  detail_path: '/app/ai?q=%EA%B0%80%EC%83%81%20%EC%8B%9C%EC%84%A4',
  source: { kind: 'unverified_facility', verification: 'UNKNOWN', source_path: 'chatbot/data/facilities.json', notice: '공식 출처와 최신성은 검증되지 않았습니다.' } };
const page = (changes: Partial<Page> = {}): Page => ({ query: '대학', kind: 'all', items: [guide(), facility],
  total: 2, counts: { guide: 1, facility: 1 }, offset: 0, limit: 8, complete: true,
  personal_data_access: false, generated: false, notice: '공개 자료만 검색합니다.', ...changes });
function submit(query = '대학') {
  fireEvent.change(screen.getByLabelText('검색어'), { target: { value: query } });
  fireEvent.submit(screen.getByLabelText('검색어').closest('form')!);
}

describe('공개 통합 검색', () => {
  it('초기 개인검색 미지원과 공백 입력을 안내하고 요청하지 않는다', () => {
    render(<PublicDiscoveryPage />);
    expect(screen.getByText(/개인 시간표·성적·신청·대화 검색은 아직/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '검색' }).hasAttribute('disabled')).toBe(true);
    submit('   ');
    expect(requestData).not.toHaveBeenCalled();
  });

  it('폼 제출로 실제 공개 API를 요청하고 두 출처를 구별하며 내부 링크를 표시한다', async () => {
    vi.mocked(requestData).mockResolvedValue(page());
    render(<PublicDiscoveryPage />); submit();
    expect(await screen.findByRole('heading', { name: '가상 시설' })).toBeTruthy();
    expect(screen.getByText(/페이지 존재 확인/)).toBeTruthy();
    expect(screen.getByText(/출처 신뢰도 UNKNOWN/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /안내 상세로 이동/ }).getAttribute('href')).toBe('/app/information?guide=demo-0');
    expect(screen.getByRole('link', { name: /시설 검색에서 확인/ }).getAttribute('href')).toBe(facility.detail_path);
    expect(requestData).toHaveBeenCalledWith('/discovery?q=%EB%8C%80%ED%95%99&kind=all&offset=0&limit=8', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    await waitFor(() => expect(document.activeElement?.tagName).toBe('H2'));
  });

  it('실패 재시도에서 검색 초안이 변경돼도 마지막 요청을 그대로 보낸다', async () => {
    vi.mocked(requestData).mockRejectedValueOnce(new Error('private-server-secret')).mockResolvedValue(page());
    render(<PublicDiscoveryPage />); submit();
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('검색어'), { target: { value: '새로운 초안' } });
    fireEvent.click(screen.getByRole('button', { name: '같은 검색 재시도' }));
    expect(await screen.findByRole('heading', { name: '가상 시설' })).toBeTruthy();
    expect(vi.mocked(requestData).mock.calls[1][0]).toBe(vi.mocked(requestData).mock.calls[0][0]);
    expect(screen.queryByText('private-server-secret')).toBeNull();
    expect((screen.getByLabelText('검색어') as HTMLInputElement).value).toBe('새로운 초안');
  });

  it('페이지 이동은 적용된 검색을 유지하고 일부 범위를 명시한다', async () => {
    vi.mocked(requestData).mockResolvedValueOnce(page({ items: Array.from({ length: 8 }, (_, i) => guide(i)), total: 10,
      counts: { guide: 10, facility: 0 }, complete: false })).mockResolvedValueOnce(page({ items: [guide(8), guide(9)],
      total: 10, counts: { guide: 10, facility: 0 }, offset: 8, complete: false }));
    render(<PublicDiscoveryPage />); submit();
    expect(await screen.findByText(/처리량 제한으로 일부 결과/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('검색어'), { target: { value: '보내지않은초안' } });
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    expect(await screen.findByRole('heading', { name: '가상 대학 안내 8' })).toBeTruthy();
    expect(vi.mocked(requestData).mock.calls[1][0]).toContain('q=%EB%8C%80%ED%95%99&kind=all&offset=8');
    expect(screen.getByRole('button', { name: '다음' }).hasAttribute('disabled')).toBe(true);
  });

  it('빈 결과와 진행 중인 요청의 화면 이탈 취소를 구별한다', async () => {
    vi.mocked(requestData).mockResolvedValueOnce(page({ items: [], total: 0, counts: { guide: 0, facility: 0 } }));
    const view = render(<PublicDiscoveryPage />); submit();
    expect(await screen.findByText(/일치하는 공개 자료가 없습니다/)).toBeTruthy();
    vi.mocked(requestData).mockImplementation(() => new Promise(() => {}));
    submit('시설');
    expect(screen.getByRole('status').textContent).toContain('찾고 있습니다');
    const signal = vi.mocked(requestData).mock.calls[1][1]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('잘못된 응답이나 외부 상세 링크를 개인 자료처럼 렌더링하지 않는다', async () => {
    vi.mocked(requestData).mockResolvedValue(page({ items: [{ ...guide(), detail_path: 'https://private.invalid/student' }, facility] }));
    render(<PublicDiscoveryPage />); submit();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '가상 대학 안내 0' })).toBeNull();
  });

  it('공통 client는 discovery 경로에 API prefix를 한 번 적용한다', async () => {
    const client = await vi.importActual<typeof import('../../lib/api')>('../../lib/api');
    expect(new URL(client.resolveApiUrl('/discovery?q=test')).pathname).toBe('/api/v1/discovery');
  });
});

describe('응답 검증', () => {
  it.each([
    page({ personal_data_access: true } as unknown as Partial<Page>),
    page({ generated: true } as unknown as Partial<Page>),
    page({ total: 99 }),
    page({ items: [guide(), guide()] }),
    page({ items: [{ ...guide(), source: facility.source }, facility] }),
    page({ items: [{ ...guide(), detail_path: '/app/information?guide=other' }, facility] }),
    page({ items: [{ ...facility, detail_path: '//evil.invalid/app/ai?q=a' }, guide()] }),
    page({ items: [{ ...facility, detail_path: '/app/ai?q=a&next=https://evil.invalid' }, guide()] }),
  ])('민감 접근·출처 위장·집계 불일치·안전하지 않은 링크를 거부한다', value => {
    expect(isPage(value)).toBe(false);
  });
});
