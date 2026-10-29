import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import CampusAssistantPage from './index';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
describe('시설 검색 결과 링크', () => {
  it('링크의 검색어를 입력과 공개 검색 API에 연결한다', async () => {
    vi.mocked(requestData).mockReset().mockResolvedValue({ mode: 'retrieval_only', found: false, hits: [], verification: 'UNKNOWN',
      source_notice: '시설 스냅샷 · 공식 출처 미검증', generated: false, personal_data_access: false });
    window.history.replaceState(null, '', '/app/ai?q=가상%20시설');
    render(<CampusAssistantPage />);
    expect(screen.getByLabelText('시설 이름 또는 질문')).toHaveValue('가상 시설');
    expect(await screen.findByText(/일치하는 시설이 없습니다/)).toBeInTheDocument();
    expect(requestData).toHaveBeenCalledWith('/ai/campus/search?q=%EA%B0%80%EC%83%81+%EC%8B%9C%EC%84%A4&limit=5', expect.anything());
  });
  it('길이 제한을 넘거나 제어 문자를 담은 링크는 자동 조회하지 않는다', async () => {
    vi.mocked(requestData).mockReset();
    window.history.replaceState(null, '', `/app/ai?q=${'a'.repeat(201)}%00`);
    render(<CampusAssistantPage />);
    await waitFor(() => expect(requestData).not.toHaveBeenCalled());
    expect(screen.getByLabelText('시설 이름 또는 질문')).toHaveValue('');
  });
});
