import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import DataProvenancePage from './index';
import { isOverview, labelText, provenanceLabels, toProvenanceLabel } from './models';
import { SourceLabel } from './SourceLabel';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
afterEach(() => vi.resetAllMocks());

const labels = provenanceLabels.map((label) => ({
  label, title: labelText[label], description: `${label} 자동 테스트용 설명`, user_guidance: `${label} 자동 테스트용 안내`,
}));
const overview = {
  catalog_version: 'data-provenance-2026-10-30-v1', feature_ids: ['FR-ADM-004'],
  notice: '자동 테스트용 읽기 전용 안내입니다.',
  status: { school_sso_connected: false, financial_effect: 'NONE', persistence: 'IN_PROCESS_FIXED', content_administration: 'NOT_IMPLEMENTED' },
  labels,
};

describe('SourceLabel', () => {
  it.each(provenanceLabels)('%s 배지를 고유 문구로 표시한다', (label) => {
    const { container } = render(<SourceLabel label={label} />);
    const badge = container.querySelector(`[data-provenance="${label}"]`);
    expect(badge).toBeTruthy();
    expect(badge?.textContent).toContain(labelText[label]);
    expect(badge?.textContent).toContain('출처');
  });

  it('알 수 없는 값은 공식이 아닌 출처 미확인으로 표시한다', () => {
    for (const value of ['official', 'ADMIN', '', null, 42, { label: 'DEMO' }]) {
      const { container, unmount } = render(<SourceLabel label={value} />);
      expect(container.querySelector('[data-provenance="UNKNOWN"]')?.textContent).toContain('출처 미확인');
      unmount();
    }
    expect(toProvenanceLabel('OFFICIAL_PUBLIC')).toBe('OFFICIAL_PUBLIC');
  });
});

describe('자료 출처 표시 안내', () => {
  it('고정 경로만 요청하고 네 가지 배지와 상태를 표시한다', async () => {
    vi.mocked(requestData).mockResolvedValue(overview);
    render(<DataProvenancePage />);
    expect(await screen.findByRole('heading', { name: '출처 배지 종류' })).toBeTruthy();
    expect(vi.mocked(requestData)).toHaveBeenCalledWith('/data-provenance', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    for (const label of provenanceLabels) expect(screen.getByRole('heading', { level: 3, name: labelText[label] })).toBeTruthy();
    const status = screen.getByRole('region', { name: '현재 상태' });
    expect(within(status).getByText(/학교 통합 로그인\(SSO\): 연결되지 않음/)).toBeTruthy();
    expect(within(status).getByText(/금전적 효력: 없음/)).toBeTruthy();
    expect(within(status).getByText(/출처 관리 기능: 구현되지 않음/)).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('잘못된 응답은 오류로 처리하고 다시 시도할 수 있다', async () => {
    vi.mocked(requestData).mockResolvedValueOnce({ ...overview, status: { ...overview.status, school_sso_connected: true } });
    render(<DataProvenancePage />);
    expect(await screen.findByText(/출처 표시 안내를 불러오지 못했습니다/)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '출처 배지 종류' })).toBeNull();
    vi.mocked(requestData).mockResolvedValueOnce(overview);
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByRole('heading', { name: '출처 배지 종류' })).toBeTruthy();
  });

  it('네트워크 실패를 상태 영역으로 알린다', async () => {
    vi.mocked(requestData).mockRejectedValue(new Error('offline'));
    render(<DataProvenancePage />);
    await screen.findByText(/출처 표시 안내를 불러오지 못했습니다/);
    expect(screen.getByRole('status').textContent).toMatch(/불러오지 못했습니다/);
  });

  it('StrictMode 정리된 요청의 지연 실패는 현재 성공을 지우지 않는다', async () => {
    let reject!: (error: Error) => void;
    vi.mocked(requestData).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    vi.mocked(requestData).mockResolvedValueOnce(overview);
    render(<StrictMode><DataProvenancePage /></StrictMode>);
    expect(await screen.findByRole('heading', { name: '출처 배지 종류' })).toBeInTheDocument();
    expect(vi.mocked(requestData).mock.calls[0][1]?.signal?.aborted).toBe(true);
    await act(async () => reject(new Error('synthetic late error')));
    expect(screen.getByRole('heading', { name: '출처 배지 종류' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다시 시도' })).toBeNull();
  });
});

describe('isOverview', () => {
  it('네 라벨이 정해진 순서로 모두 있을 때만 허용한다', () => {
    expect(isOverview(overview)).toBe(true);
    expect(isOverview({ ...overview, labels: labels.slice(0, 3) })).toBe(false);
    expect(isOverview({ ...overview, labels: [...labels].reverse() })).toBe(false);
    expect(isOverview({ ...overview, status: { ...overview.status, financial_effect: 'REAL' } })).toBe(false);
    expect(isOverview({ ...overview, labels: [{ ...labels[0], label: 'ADMIN' }, ...labels.slice(1)] })).toBe(false);
  });
});
