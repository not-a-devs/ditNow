import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import ScreenSharingPage from './index';
import { isContext, isSession, isSignals, type Context, type Session } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const COURSE = '11111111-1111-4111-8111-111111111111';
const ID = '22222222-2222-4222-8222-222222222222';
const PEER = '33333333-3333-4333-8333-333333333333';
const VIEWER = '44444444-4444-4444-8444-444444444444';
const session: Session = { id: ID, offering_id: COURSE, state: 'READY', revision: 1, expires_at: '2099-10-30T00:00:00Z',
  is_presenter: true, me: { peer_id: PEER, generation: 1 }, presenter: { peer_id: PEER, generation: 1 }, viewers: [], audio: false, recording: false, media_provider: 'NOT_CONNECTED' };
const teacher: Context = { offering_id: COURSE, role: 'teacher', session: null, source_kind: 'DEMO' };
const display = vi.fn();
let latest: Context;
beforeEach(() => {
  display.mockReset(); vi.mocked(requestData).mockReset(); latest = teacher;
  vi.stubGlobal('isSecureContext', true); vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: display } });
  vi.mocked(requestData).mockImplementation(async (path, init) => {
    if (path === `/screen-sharing/${COURSE}`) return latest;
    if (path.endsWith('/sessions')) { latest = { ...teacher, session }; return session; }
    if (path.endsWith('/activate')) { latest = { ...teacher, session: { ...session, state: 'LIVE', revision: 2 } }; return latest.session; }
    if (path.includes('/signals?')) return { items: [], cursor: 0 };
    if (path.endsWith('/end')) { latest = { ...teacher, session: { ...session, state: 'ENDED', revision: 3 } }; return latest.session; }
    if (path.endsWith('/join')) return latest.session;
    if (path.endsWith('/leave') && init?.method === 'POST') return null;
    throw new ApiError('UNAVAILABLE', 503);
  });
});
afterEach(() => vi.unstubAllGlobals());

function fakeStream() {
  const track = { kind: 'video', onended: null, stop: vi.fn() };
  return { track, stream: { getVideoTracks: () => [track], getAudioTracks: () => [], getTracks: () => [track] } };
}
async function prepare() {
  await screen.findByText('현재 분반의 서버 권한: 담당 교수');
  fireEvent.click(screen.getByRole('button', { name: '교수 공유 연결 준비' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '화면 선택 · 공유 시작' })).not.toBeDisabled());
}

describe('화면 공유 UI · 모의 미디어만 사용', () => {
  it('분반 미연결·503에서 가상 교수나 캡처를 만들지 않는다', async () => {
    const view = render(<ScreenSharingPage />);
    expect(screen.getByText(/승인된 공통 강의실에서/)).toBeInTheDocument(); expect(requestData).not.toHaveBeenCalled();
    vi.mocked(requestData).mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    view.rerender(<ScreenSharingPage offeringId={COURSE} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument(); expect(display).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '교수 공유 연결 준비' })).toBeNull();
  });
  it('교수 연결 준비와 직접 화면 선택을 분리하고 종료·unmount에서 트랙을 중지한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    const view = render(<ScreenSharingPage offeringId={COURSE} />); await prepare();
    expect(display).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '화면 선택 · 공유 시작' }));
    await waitFor(() => expect(display).toHaveBeenCalledWith({ video: true, audio: false }));
    await screen.findByText('공유 상태: LIVE · 오디오 OFF · 녹화 OFF');
    view.unmount(); expect(track.stop).toHaveBeenCalledOnce();
    expect(vi.mocked(requestData).mock.calls.every(([path]) => path.startsWith('/screen-sharing/'))).toBe(true);
  });
  it('학생은 수신 연결만 하고 캡처·교수 신호를 시작하지 않는다', async () => {
    latest = { offering_id: COURSE, role: 'student', source_kind: 'DEMO', session: { ...session, state: 'LIVE', is_presenter: false, me: null } };
    const view = render(<ScreenSharingPage offeringId={COURSE} />);
    await screen.findByText('현재 분반의 서버 권한: 수강생 · 시청 전용');
    expect(screen.queryByRole('button', { name: '화면 선택 · 공유 시작' })).toBeNull();
    latest = { ...latest, session: { ...latest.session!, me: { peer_id: VIEWER, generation: 1 } } };
    fireEvent.click(screen.getByRole('button', { name: '수업 화면 시청 연결' }));
    await waitFor(() => expect(requestData).toHaveBeenCalledWith(expect.stringContaining('/join'), expect.anything()));
    expect(display).not.toHaveBeenCalled(); view.unmount();
  });
  it('권한 거절 원문을 보여주지 않고 자동 재캡처하지 않는다', async () => {
    display.mockRejectedValue(new DOMException('private-window-title', 'NotAllowedError'));
    render(<ScreenSharingPage offeringId={COURSE} />); await prepare();
    fireEvent.click(screen.getByRole('button', { name: '화면 선택 · 공유 시작' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('private-window-title')).toBeNull(); expect(display).toHaveBeenCalledOnce();
  });
  it('캡처 선택 대기 중 화면을 떠나면 늦은 스트림도 중지하고 활성화 API를 보내지 않는다', async () => {
    let finish!: (stream: object) => void; display.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const { track, stream } = fakeStream(); const view = render(<ScreenSharingPage offeringId={COURSE} />); await prepare();
    fireEvent.click(screen.getByRole('button', { name: '화면 선택 · 공유 시작' })); view.unmount(); finish(stream);
    await waitFor(() => expect(track.stop).toHaveBeenCalledOnce());
    expect(vi.mocked(requestData).mock.calls.some(([path]) => path.endsWith('/activate'))).toBe(false);
  });
  it('StrictMode의 취소된 첫 응답이 현재 권한·초기화 상태를 덮어쓰지 않는다', async () => {
    let failFirst!: (error: Error) => void; let calls = 0;
    vi.mocked(requestData).mockImplementation(() => ++calls === 1 ? new Promise((_, reject) => { failFirst = reject; }) : Promise.resolve(teacher));
    render(<StrictMode><ScreenSharingPage offeringId={COURSE} /></StrictMode>);
    await screen.findByText('현재 분반의 서버 권한: 담당 교수'); failFirst(new Error('late-cancelled'));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull()); expect(display).not.toHaveBeenCalled();
  });
  it('제어 API 실패에도 로컬 캡처를 먼저 정지한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    render(<ScreenSharingPage offeringId={COURSE} />); await prepare();
    fireEvent.click(screen.getByRole('button', { name: '화면 선택 · 공유 시작' })); await screen.findByText('공유 상태: LIVE · 오디오 OFF · 녹화 OFF');
    const original = vi.mocked(requestData).getMockImplementation()!;
    vi.mocked(requestData).mockImplementation((path, init) => path.endsWith('/end') ? Promise.reject(new ApiError('NETWORK', 0)) : original(path, init));
    fireEvent.click(screen.getByRole('button', { name: '공유·시청 중지' }));
    expect(track.stop).toHaveBeenCalledOnce(); expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
  it('신원·오디오·잘못된 SDP·수강 범위 응답 오염을 거부한다', () => {
    expect(isSession({ ...session, presenter_id: 'private' })).toBe(false);
    expect(isContext({ ...teacher, source_kind: 'REAL' })).toBe(false);
    expect(isSession({ ...session, audio: true })).toBe(false);
    expect(isSignals({ items: [{ sequence: 1, sender_peer_id: PEER, generation: 1, kind: 'OFFER', payload: 'v=0\r\nm=audio 9 RTP/AVP 0\r\na=sendrecv\r\n' }], cursor: 1 })).toBe(false);
  });
});
