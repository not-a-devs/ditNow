import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import DemoProfile from './index';

vi.mock('./api', async () => ({ ...await vi.importActual<typeof import('./api')>('./api'), loadDemoProfile: vi.fn(), saveDemoProfile: vi.fn() }));
const base: api.DemoPreferences = { interests: [], skill_level: 'beginner', revision: 1, record_source: 'DEMO', storage: 'PROCESS_MEMORY' };
const saved: api.DemoPreferences = { interests: ['coding', 'career'], skill_level: 'intermediate', revision: 2, record_source: 'DEMO', storage: 'PROCESS_MEMORY' };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.loadDemoProfile).mockResolvedValue(base); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
async function loaded() { const view = render(<DemoProfile />); await screen.findByText(/저장된 값 · 개정 1/); return view; }
async function editAndConfirm() {
  fireEvent.click(screen.getByLabelText('진로')); fireEvent.click(screen.getByLabelText('코딩')); fireEvent.click(screen.getByLabelText('중급'));
  fireEvent.click(screen.getByRole('button', { name: '변경 내용 확인' }));
  fireEvent.click(screen.getByRole('button', { name: '저장 확정' }));
}

describe('가상 활동 선호 설정', () => {
  it('고정 DEMO/PROCESS_MEMORY 응답만 허용하고 신원·학적·역할 필드를 거부한다', () => {
    expect(api.isDemoPreferences(base)).toBe(true);
    for (const changed of [{ user_id: 'x' }, { display_name: '이름' }, { department: '학과' }, { academic_year: 1 }, { role: 'admin' }, { bio: '소개' },
      { record_source: 'OFFICIAL' }, { storage: 'MARIADB' }, { interests: ['gaming'] }, { interests: ['coding', 'coding'] }, { skill_level: 'expert' }, { revision: 0 }, { revision: '1' }])
      expect(api.isDemoPreferences({ ...base, ...changed })).toBe(false);
    const missing: Record<string, unknown> = { ...base }; delete missing.storage; expect(api.isDemoPreferences(missing)).toBe(false);
  });
  it('프로세스 메모리 한계를 명시하고 자유 입력 칸이 없다', async () => {
    await loaded();
    expect(screen.getByRole('note')).toHaveTextContent(/PROCESS_MEMORY.*데이터베이스에 저장되지 않으며.*재시작 시 초기화/);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')).toHaveLength(4);
  });
  it('편집→확인→저장→다시 조회 순서로 저장하고 확인 전에는 보내지 않는다', async () => {
    vi.mocked(api.saveDemoProfile).mockResolvedValue(saved); await loaded();
    vi.mocked(api.loadDemoProfile).mockResolvedValue(saved);
    expect(screen.getByRole('button', { name: '변경 내용 확인' })).toBeDisabled();
    fireEvent.click(screen.getByLabelText('진로')); fireEvent.click(screen.getByLabelText('코딩')); fireEvent.click(screen.getByLabelText('중급'));
    fireEvent.click(screen.getByRole('button', { name: '변경 내용 확인' }));
    expect(screen.getByRole('group', { name: '저장 확인' })).toHaveTextContent('코딩, 진로');
    expect(api.saveDemoProfile).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '저장 확정' }));
    await screen.findByText(/다시 조회해 같은 값을 확인했습니다/);
    expect(vi.mocked(api.saveDemoProfile).mock.calls[0][0]).toEqual({ interests: ['coding', 'career'], skill_level: 'intermediate', revision: 1 });
    expect(api.loadDemoProfile).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/저장된 값 · 개정 2/)).toBeInTheDocument();
  });
  it('계속 편집은 저장하지 않고 확인 단계를 닫는다', async () => {
    await loaded(); fireEvent.click(screen.getByLabelText('디자인'));
    fireEvent.click(screen.getByRole('button', { name: '변경 내용 확인' }));
    fireEvent.click(screen.getByRole('button', { name: '계속 편집' }));
    expect(screen.queryByRole('group', { name: '저장 확인' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('디자인')).toBeChecked(); expect(api.saveDemoProfile).not.toHaveBeenCalled();
  });
  it('409는 입력을 보존하고 다시 조회는 입력을 대체한다', async () => {
    vi.mocked(api.saveDemoProfile).mockRejectedValue(new ApiError('CONFLICT', 409)); await loaded();
    await editAndConfirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('입력은 보존했습니다');
    expect(screen.getByLabelText('진로')).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: /다시 조회/ }));
    await waitFor(() => expect(screen.getByLabelText('진로')).not.toBeChecked());
  });
  it('401은 개인 설정을 지운다', async () => {
    vi.mocked(api.saveDemoProfile).mockRejectedValue(new ApiError('UNAUTHORIZED', 401)); await loaded();
    await editAndConfirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 만료');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it('503 기본 비활성 상태를 안내하고 저장 컨트롤을 표시하지 않는다', async () => {
    vi.mocked(api.loadDemoProfile).mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<DemoProfile />); expect(await screen.findByRole('alert')).toHaveTextContent('준비되지 않았');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it('계정 세대 변경 시 이전 요청을 중단하고 이전 계정 값을 지운다', async () => {
    const signals: AbortSignal[] = [];
    let resolveOld: (value: api.DemoPreferences) => void = () => {};
    vi.mocked(api.loadDemoProfile).mockImplementationOnce(signal => { signals.push(signal!); return new Promise(resolve => { resolveOld = resolve; }); });
    const view = render(<DemoProfile sessionGeneration={1} />);
    vi.mocked(api.loadDemoProfile).mockImplementation(signal => { signals.push(signal!); return Promise.resolve(base); });
    view.rerender(<DemoProfile sessionGeneration={2} />);
    await screen.findByText(/저장된 값 · 개정 1/);
    expect(signals[0].aborted).toBe(true);
    await act(async () => { resolveOld(saved); });
    expect(screen.queryByText(/개정 2/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('코딩')).not.toBeChecked();
  });
  it('같은 틱의 두 번 저장 확정은 요청을 한 번만 보낸다', async () => {
    vi.mocked(api.saveDemoProfile).mockResolvedValue(saved); await loaded();
    vi.mocked(api.loadDemoProfile).mockResolvedValue(saved);
    fireEvent.click(screen.getByLabelText('진로')); fireEvent.click(screen.getByLabelText('코딩')); fireEvent.click(screen.getByLabelText('중급'));
    fireEvent.click(screen.getByRole('button', { name: '변경 내용 확인' }));
    const confirm = screen.getByRole('button', { name: '저장 확정' });
    act(() => { confirm.click(); confirm.click(); });
    await screen.findByText(/다시 조회해 같은 값을 확인했습니다/);
    expect(api.saveDemoProfile).toHaveBeenCalledTimes(1);
  });
  it.each([base, { ...saved, interests: ['design'] as api.Interest[] }])('제출과 다른 저장 영수증은 성공으로 표시하지 않는다 %j', async receipt => {
    vi.mocked(api.saveDemoProfile).mockResolvedValue(receipt);
    await loaded();
    vi.mocked(api.loadDemoProfile).mockResolvedValue(receipt);
    await editAndConfirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('형식을 확인하지 못했습니다');
    expect(screen.queryByText(/다시 조회해 같은 값을 확인했습니다/)).toBeNull();
    expect(api.loadDemoProfile).toHaveBeenCalledTimes(1);
  });
  it.each([base, { ...saved, interests: [] as api.Interest[] }])('이전 개정 또는 같은 개정의 다른 재조회는 성공이 아니다 %j', async readback => {
    vi.mocked(api.saveDemoProfile).mockResolvedValue(saved);
    await loaded();
    vi.mocked(api.loadDemoProfile).mockResolvedValue(readback);
    await editAndConfirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('형식을 확인하지 못했습니다');
    expect(screen.queryByText(/다시 조회해 같은 값을 확인했습니다|최신 값을 표시합니다/)).toBeNull();
  });
  it('403은 같은 세대의 다시 조회·저장을 잠그고 새 세대에서만 다시 읽는다', async () => {
    vi.mocked(api.saveDemoProfile).mockRejectedValue(new ApiError('FORBIDDEN', 403));
    const view = await loaded(); await editAndConfirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('접근할 수 없어');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    const reload = screen.getByRole('button', { name: /다시 조회/ });
    expect(reload).toBeDisabled(); act(() => { reload.click(); });
    expect(api.loadDemoProfile).toHaveBeenCalledTimes(1);
    view.rerender(<DemoProfile sessionGeneration={1} />);
    await screen.findByText(/저장된 값 · 개정 1/);
    expect(api.loadDemoProfile).toHaveBeenCalledTimes(2);
  });
  it('StrictMode 이중 설정에서도 첫 요청을 중단하고 최신 요청만 반영한다', async () => {
    const signals: AbortSignal[] = [];
    vi.mocked(api.loadDemoProfile).mockImplementation(signal => { signals.push(signal!); return Promise.resolve(base); });
    render(<StrictMode><DemoProfile /></StrictMode>);
    await screen.findByText(/저장된 값 · 개정 1/);
    expect(signals.length).toBeGreaterThanOrEqual(1);
    expect(signals.slice(0, -1).every(signal => signal.aborted)).toBe(true);
    expect(signals[signals.length - 1].aborted).toBe(false);
  });
  it('저장 중 계정이 바뀌면 이전 결과를 표시하지 않는다', async () => {
    let resolveSave: (value: api.DemoPreferences) => void = () => {};
    vi.mocked(api.saveDemoProfile).mockImplementation(() => new Promise(resolve => { resolveSave = resolve; }));
    const view = await loaded(); await editAndConfirm();
    view.rerender(<DemoProfile sessionGeneration={1} />);
    await screen.findByText(/저장된 값 · 개정 1/);
    await act(async () => { resolveSave(saved); });
    expect(screen.queryByText(/다시 조회해 같은 값을 확인했습니다/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('진로')).not.toBeChecked();
  });
});
