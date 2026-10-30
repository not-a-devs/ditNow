import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestData } from '../../lib/api';
import CampusAssistantPage from './index';

vi.mock('../../lib/api', () => ({ requestData: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe('캠퍼스 검색 통합 화면', () => {
  it('공백 검색을 차단하고 개인정보 연결 상태를 알린다', () => {
    render(<CampusAssistantPage />);
    expect(screen.getByRole('button', { name: '검색' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/개인 시간표·성적 안내/)).toBeTruthy();
    expect(vi.mocked(requestData)).not.toHaveBeenCalled();
  });

  it('실제 API 결과와 출처 한계를 표시한다', async () => {
    vi.mocked(requestData).mockResolvedValue({
      mode: 'retrieval_only', found: true, verification: 'UNKNOWN',
      source_notice: '공식 출처와 최신성이 검증되지 않은 시설 자료입니다.',
      generated: false, personal_data_access: false,
      hits: [{ source_id: 'demo-library', name: '가상 도서관', category: '시설',
        text: '자동 테스트 전용 시설입니다.', building: '가상관', floor: '2층', room: null,
        hours: null, score: 1, matched_by: 'alias' }],
    });
    render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '도서관' } });
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    expect(await screen.findByRole('heading', { name: '가상 도서관' })).toBeTruthy();
    expect(screen.getByText(/공식 출처와 최신성이 검증되지/)).toBeTruthy();
    expect(vi.mocked(requestData)).toHaveBeenCalledWith(
      '/ai/campus/search?q=%EB%8F%84%EC%84%9C%EA%B4%80&limit=5',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('연결 실패 시 가상 성공 결과를 만들지 않는다', async () => {
    vi.mocked(requestData).mockRejectedValue(new Error('offline'));
    render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '가상 시설' } });
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });

  it('잘못된 응답이 시설 자료나 개인정보로 렌더링되지 않는다', async () => {
    vi.mocked(requestData).mockResolvedValue({ found: true, hits: 'private-record-secret' });
    render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '가상 시설' } });
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('private-record-secret')).toBeNull();
  });

  it('화면을 떠나면 진행 중인 시설 요청을 취소한다', () => {
    let signal: AbortSignal | null = null;
    vi.mocked(requestData).mockImplementation((_path, init) => {
      signal = init?.signal as AbortSignal;
      return new Promise(() => {});
    });
    const view = render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '가상 시설' } });
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    view.unmount();
    expect(signal).not.toBeNull();
    expect((signal as AbortSignal | null)?.aborted).toBe(true);
  });

  it('AI에게 묻기: 위치를 허락하면 함께 보내고 도보 예상 시간을 보여 준다', async () => {
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
      getCurrentPosition: (ok: PositionCallback) => ok({ coords: { latitude: 35.166, longitude: 129.073 } } as GeolocationPosition),
    } });
    vi.mocked(requestData).mockResolvedValue({ answer: '미래관은 걸어서 약 4분이에요.', found: true,
      locations: [{ id: 'bld_mirae', name: '미래관', building: '미래관', lat: 35.1, lng: 129.0, distance_m: 280, walk_minutes: 4 }] });
    render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '미래관까지 몇 분?' } });
    fireEvent.click(screen.getByLabelText(/내 위치로 도보 시간 계산/));
    fireEvent.click(screen.getByRole('button', { name: 'AI에게 묻기' }));
    expect(await screen.findByText('미래관은 걸어서 약 4분이에요.')).toBeTruthy();
    expect(screen.getByText(/걸어서 약 4분 · 약 280m/)).toBeTruthy();
    const [path, init] = vi.mocked(requestData).mock.calls[0];
    expect(path).toBe('/ai/ask');
    expect(JSON.parse(String(init?.body))).toEqual({ question: '미래관까지 몇 분?', user_location: { lat: 35.166, lng: 129.073 } });
  });

  it('AI에게 묻기: 위치를 끄면 보내지 않고, 잘못된 응답은 오류로 알린다', async () => {
    vi.mocked(requestData).mockResolvedValue({ answer: 1 });
    render(<CampusAssistantPage />);
    fireEvent.change(screen.getByLabelText('시설 이름 또는 질문'), { target: { value: '미래관' } });
    fireEvent.click(screen.getByRole('button', { name: 'AI에게 묻기' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(JSON.parse(String(vi.mocked(requestData).mock.calls[0][1]?.body))).toEqual({ question: '미래관' });
  });
});
