import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import PlatformLogin, { type PlatformLoginProps } from './index';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return { ...actual, login: vi.fn(), logout: vi.fn() };
});
const demo: api.DemoLoginSession = { token: 'fictional-ui-test-token', token_type: 'Bearer', student_id: 'fictional-id', name: '가상 학생', record_source: 'DEMO' };
function props(overrides: Partial<PlatformLoginProps> = {}): PlatformLoginProps {
  return { enabled: true, session: { state: 'signed_out' }, onSignedIn: vi.fn(), onSignedOut: vi.fn(), ...overrides };
}
function fill() {
  fireEvent.change(screen.getByLabelText('가상 학번'), { target: { value: 'fictional-id' } });
  fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'fictional-password' } });
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.login).mockResolvedValue(demo); vi.mocked(api.logout).mockResolvedValue(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('신규 플랫폼 로그인', () => {
  it('기본 비활성이고 초기 값이나 별도 계정 자격을 채우지 않는다', () => {
    render(<PlatformLogin {...props({ enabled: undefined })} />);
    expect(screen.getByLabelText('가상 학번')).toBeDisabled();
    expect(screen.getByLabelText('비밀번호')).toHaveValue('');
    expect(screen.getByLabelText('가상 학번')).toHaveValue('');
    fireEvent.submit(screen.getByRole('button', { name: '가상 계정으로 로그인' }).closest('form')!);
    expect(api.login).not.toHaveBeenCalled();
  });
  it('빈 입력은 서버에 보내지 않고 접근 가능한 오류로 안내한다', () => {
    render(<PlatformLogin {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    expect(screen.getByRole('alert')).toHaveTextContent('학번을 1~20자');
    expect(api.login).not.toHaveBeenCalled();
  });
  it('중복 제출을 동기적으로 막고 비밀번호를 지운 뒤 성공은 상위 콜백에만 전달한다', async () => {
    let resolve!: (value: api.DemoLoginSession) => void;
    vi.mocked(api.login).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const onSignedIn = vi.fn(), local = vi.spyOn(Storage.prototype, 'setItem'), log = vi.spyOn(console, 'log');
    render(<PlatformLogin {...props({ onSignedIn })} />); fill();
    const form = screen.getByRole('button', { name: '가상 계정으로 로그인' }).closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(api.login).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('비밀번호')).toHaveValue('');
    expect(screen.getByRole('button', { name: '로그인 확인 중…' })).toBeDisabled();
    await act(async () => resolve(demo));
    expect(onSignedIn).toHaveBeenCalledExactlyOnceWith(demo);
    expect(local).not.toHaveBeenCalled(); expect(log).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent(demo.token);
    expect(document.body).not.toHaveTextContent('fictional-password');
  });
  it.each([401, 403, 429, 503])('%s 실패는 성공으로 가장하지 않고 비밀번호와 원문 오류를 표시하지 않는다', async status => {
    const error = new ApiError(status === 401 ? 'UNAUTHORIZED' : 'UNAVAILABLE', status);
    error.message = 'unsafe-private-details'; vi.mocked(api.login).mockRejectedValueOnce(error);
    const onSignedIn = vi.fn(); render(<PlatformLogin {...props({ onSignedIn })} />); fill();
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    await screen.findByRole('alert'); expect(onSignedIn).not.toHaveBeenCalled();
    expect(screen.getByLabelText('비밀번호')).toHaveValue('');
    expect(document.body).not.toHaveTextContent('unsafe-private-details');
    if (status === 503) expect(screen.getByRole('alert')).toHaveTextContent('로그인되지 않았습니다');
  });
  it('StrictMode에서 자동 요청 없이 제출당 한 번만 로그인한다', async () => {
    const onSignedIn = vi.fn(); render(<StrictMode><PlatformLogin {...props({ onSignedIn })} /></StrictMode>);
    expect(api.login).not.toHaveBeenCalled(); fill();
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledOnce());
    expect(api.login).toHaveBeenCalledOnce();
  });
  it('화면 제거는 요청을 취소하고 늦은 로그인 결과를 폐기한다', async () => {
    let resolve!: (value: api.DemoLoginSession) => void;
    vi.mocked(api.login).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const onSignedIn = vi.fn(); const view = render(<PlatformLogin {...props({ onSignedIn })} />); fill();
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    const signal = vi.mocked(api.login).mock.calls[0][1]!; view.unmount();
    expect(signal.aborted).toBe(true); await act(async () => resolve(demo));
    expect(onSignedIn).not.toHaveBeenCalled();
  });
  it('요청 중 활성화 철회나 상위 세션 변경 뒤 과거 결과는 공통 세션에 넣지 않는다', async () => {
    let resolve!: (value: api.DemoLoginSession) => void;
    vi.mocked(api.login).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const onSignedIn = vi.fn(), current = props({ onSignedIn });
    const view = render(<PlatformLogin {...current} />); fill();
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    const signal = vi.mocked(api.login).mock.calls[0][1]!;
    view.rerender(<PlatformLogin {...current} enabled={false} session={{ state: 'expired' }} />);
    expect(signal.aborted).toBe(true); await act(async () => resolve(demo));
    expect(onSignedIn).not.toHaveBeenCalled();
    expect(screen.getByText(/세션이 만료되었습니다/)).toBeInTheDocument();
  });
  it('만료는 상위 상태로 표시하며 임의 TTL이나 토큰 표시 없이 재로그인한다', async () => {
    const onSignedIn = vi.fn(); render(<PlatformLogin {...props({ session: { state: 'expired' }, onSignedIn })} />);
    expect(screen.getByText(/세션이 만료되었습니다/)).toBeInTheDocument(); fill();
    fireEvent.click(screen.getByRole('button', { name: '가상 계정으로 로그인' }));
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(demo));
  });
  it('서버 로그아웃 성공을 확인한 뒤 상위 메모리 세션 제거를 요청한다', async () => {
    const onSignedOut = vi.fn(); render(<PlatformLogin {...props({ session: { state: 'signed_in', session: demo }, onSignedOut })} />);
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledExactlyOnceWith('logout'));
    expect(api.logout).toHaveBeenCalledWith(demo.token, expect.any(AbortSignal));
    expect(document.body).not.toHaveTextContent(demo.token);
  });
  it.each([401, 503])('로그아웃 %s 실패도 로컬 세션 제거를 요청하고 미확인 서버 폐기를 구별한다', async status => {
    vi.mocked(api.logout).mockRejectedValueOnce(new ApiError('UNAVAILABLE', status));
    const onSignedOut = vi.fn(); render(<PlatformLogin {...props({ session: { state: 'signed_in', session: demo }, onSignedOut })} />);
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledWith(status === 401 ? 'expired' : 'local_only'));
    expect(screen.getByText(status === 401 ? /세션이 만료되어/ : /서버의 세션 폐기는 확인하지 못했습니다/)).toBeInTheDocument();
  });
  it('상위 세션 제거 콜백 실패는 네트워크 실패와 구분하고 중복 호출하지 않는다', async () => {
    const onSignedOut = vi.fn(() => { throw new Error('private-owner-details'); });
    render(<PlatformLogin {...props({ session: { state: 'signed_in', session: demo }, onSignedOut })} />);
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await screen.findByRole('alert');
    expect(onSignedOut).toHaveBeenCalledExactlyOnceWith('logout');
    expect(document.body).not.toHaveTextContent('private-owner-details');
    expect(screen.getByRole('alert')).toHaveTextContent('공통 메모리 세션 해제를 완료하지 못했습니다');
  });
});
