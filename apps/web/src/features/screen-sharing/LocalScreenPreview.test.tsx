import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LocalScreenPreview from './LocalScreenPreview';
import { MediaRoom } from './media';

const display = vi.fn();
const peerConnection = vi.fn();
const fetchSpy = vi.fn();
const START = '화면 선택 · 로컬 미리보기 시작';
const STOP = '로컬 미리보기 중지';

function fakeStream(kinds: string[] = ['video']) {
  const tracks = kinds.map(kind => ({ kind, onended: null as (() => void) | null, stop: vi.fn() }));
  const stream = { getTracks: () => tracks, getVideoTracks: () => tracks.filter(t => t.kind === 'video'), getAudioTracks: () => tracks.filter(t => t.kind === 'audio') };
  return { track: tracks.find(t => t.kind === 'video')!, tracks, stream };
}
function deferred() {
  let resolve!: (value: unknown) => void; let reject!: (error: unknown) => void;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const videoEl = () => screen.getByTestId('local-preview') as HTMLVideoElement & { srcObject: unknown };

beforeEach(() => {
  display.mockReset(); peerConnection.mockReset(); fetchSpy.mockReset();
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (Windows NT 10.0) Desktop', mediaDevices: { getDisplayMedia: display } });
  vi.stubGlobal('RTCPeerConnection', peerConnection);
  vi.stubGlobal('fetch', fetchSpy);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('로컬 화면 미리보기 · 모의 미디어만 사용', () => {
  it('마운트만으로 캡처하지 않고 로컬 전용 고지를 항상 표시한다', () => {
    render(<LocalScreenPreview />);
    expect(screen.getByText(/로컬 미리보기입니다. 실제 수업 시청 화면이 아니며/)).toBeInTheDocument();
    expect(display).not.toHaveBeenCalled(); expect(peerConnection).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: STOP })).toBeDisabled();
    const video = videoEl();
    expect(video.autoplay).toBe(true); expect(video.muted).toBe(true); expect(video.hasAttribute('playsinline')).toBe(true);
  });

  it('직접 클릭 안에서 await 전에 오디오 없이 화면을 선택하고 중지 시 트랙·핸들러를 정리한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    const sync = vi.spyOn(MediaRoom.prototype, 'sync'); const receive = vi.spyOn(MediaRoom.prototype, 'receive');
    render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    expect(display).toHaveBeenCalledOnce(); expect(display).toHaveBeenCalledWith({ video: true, audio: false });
    await waitFor(() => expect(videoEl().srcObject).toBe(stream));
    expect(track.onended).toBeTypeOf('function');
    fireEvent.click(screen.getByRole('button', { name: STOP }));
    expect(track.stop).toHaveBeenCalledOnce(); expect(track.onended).toBeNull(); expect(videoEl().srcObject).toBeNull();
    expect(screen.getByText('로컬 미리보기를 중지했습니다.')).toBeInTheDocument();
    expect(sync).not.toHaveBeenCalled(); expect(receive).not.toHaveBeenCalled();
    expect(peerConnection).not.toHaveBeenCalled(); expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('선택 대기 중 중복 클릭은 캡처 요청을 한 번만 만든다', async () => {
    const pending = deferred(); display.mockReturnValue(pending.promise);
    render(<LocalScreenPreview />);
    const start = screen.getByRole('button', { name: START });
    fireEvent.click(start); fireEvent.click(start); fireEvent.click(start);
    expect(display).toHaveBeenCalledOnce();
    const { track, stream } = fakeStream();
    await act(async () => { pending.resolve(stream); });
    expect(videoEl().srcObject).toBe(stream); expect(display).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: STOP })); expect(track.stop).toHaveBeenCalledOnce();
  });

  it('권한 거절·취소는 원문 없는 고정 안내만 보이고 다시 시도할 수 있다', async () => {
    display.mockRejectedValueOnce(new DOMException('private-device-label', 'NotAllowedError'));
    render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('화면 선택이 취소되었거나 허용되지 않았습니다.');
    expect(document.body.textContent).not.toMatch(/private-device-label|NotAllowedError/);
    expect(videoEl().srcObject ?? null).toBeNull();
    const { stream } = fakeStream(); display.mockResolvedValueOnce(stream);
    await waitFor(() => expect(screen.getByRole('button', { name: START })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: START }));
    await waitFor(() => expect(videoEl().srcObject).toBe(stream)); expect(display).toHaveBeenCalledTimes(2);
  });

  it('오디오 트랙이 섞이면 모든 트랙을 중지하고 미리보기하지 않는다', async () => {
    const { tracks, stream } = fakeStream(['audio', 'video']); display.mockResolvedValue(stream);
    render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    await screen.findByRole('alert');
    tracks.forEach(t => expect(t.stop).toHaveBeenCalledOnce()); expect(videoEl().srcObject ?? null).toBeNull();
  });

  it.each([
    ['보안 컨텍스트 아님', () => vi.stubGlobal('isSecureContext', false)],
    ['getDisplayMedia 없음', () => vi.stubGlobal('navigator', { userAgent: 'Desktop', mediaDevices: {} })],
    ['모바일', () => vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (iPhone) Mobile', mediaDevices: { getDisplayMedia: display } })],
    ['userAgentData 모바일', () => vi.stubGlobal('navigator', { userAgent: 'x', userAgentData: { mobile: true }, mediaDevices: { getDisplayMedia: display } })],
  ])('미지원(%s)은 명확히 안내하고 캡처하지 않는다', (_name, setup) => {
    setup(); render(<LocalScreenPreview />);
    expect(screen.getByText(/로컬 화면 미리보기를 지원하지 않습니다/)).toBeInTheDocument();
    const start = screen.getByRole('button', { name: START }); expect(start).toBeDisabled();
    fireEvent.click(start); expect(display).not.toHaveBeenCalled();
  });

  it('브라우저에서 공유를 끝내면 트랙을 정리하고 종료를 표시한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    await waitFor(() => expect(videoEl().srcObject).toBe(stream));
    act(() => { track.onended?.(); });
    expect(track.stop).toHaveBeenCalledOnce(); expect(videoEl().srcObject).toBeNull();
    expect(screen.getByText(/브라우저에서 화면 공유가 중지되어/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: START })).not.toBeDisabled();
  });

  it('미리보기 중 unmount는 트랙을 중지한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    const view = render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    await waitFor(() => expect(videoEl().srcObject).toBe(stream));
    view.unmount(); expect(track.stop).toHaveBeenCalledOnce();
  });

  it('unmount 뒤 늦게 끝난 캡처도 즉시 트랙을 중지하고 상태를 갱신하지 않는다', async () => {
    const pending = deferred(); display.mockReturnValue(pending.promise);
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const view = render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    view.unmount();
    const { track, stream } = fakeStream();
    await act(async () => { pending.resolve(stream); });
    expect(track.stop).toHaveBeenCalledOnce(); expect(track.onended).toBeNull();
    expect(errors).not.toHaveBeenCalled(); expect(peerConnection).not.toHaveBeenCalled();
  });

  it('선택 대기 중 중지하면 늦게 선택된 화면을 표시하지 않는다', async () => {
    const pending = deferred(); display.mockReturnValue(pending.promise);
    render(<LocalScreenPreview />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    fireEvent.click(screen.getByRole('button', { name: STOP }));
    const { track, stream } = fakeStream();
    await act(async () => { pending.resolve(stream); });
    expect(track.stop).toHaveBeenCalledOnce(); expect(videoEl().srcObject ?? null).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('StrictMode에서도 클릭당 한 번만 캡처하고 정리한다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    const view = render(<StrictMode><LocalScreenPreview /></StrictMode>);
    expect(display).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: START }));
    await waitFor(() => expect(videoEl().srcObject).toBe(stream));
    expect(display).toHaveBeenCalledOnce();
    view.unmount(); expect(track.stop).toHaveBeenCalledOnce();
  });

  it('sessionGeneration이 바뀌면 이전 미리보기를 정리하고 자동 재캡처하지 않는다', async () => {
    const { track, stream } = fakeStream(); display.mockResolvedValue(stream);
    const view = render(<LocalScreenPreview sessionGeneration={1} />);
    fireEvent.click(screen.getByRole('button', { name: START }));
    await waitFor(() => expect(videoEl().srcObject).toBe(stream));
    view.rerender(<LocalScreenPreview sessionGeneration={2} />);
    expect(track.stop).toHaveBeenCalledOnce(); expect(display).toHaveBeenCalledOnce();
    expect(videoEl().srcObject ?? null).toBeNull();
    expect(screen.getByRole('button', { name: STOP })).toBeDisabled();
  });
});
