import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MediaRoom } from './media';
import type { Peer, Session, Signal } from './api';

class Track {
  kind = 'video'; onended: (() => void) | null = null; stop = vi.fn();
}
class Stream {
  constructor(private tracks: Track[]) {}
  getTracks() { return this.tracks; }
  getVideoTracks() { return this.tracks.filter(t => t.kind === 'video'); }
  getAudioTracks() { return this.tracks.filter(t => t.kind === 'audio'); }
}
const pcs: PC[] = [];
class PC {
  localDescription: RTCSessionDescriptionInit | null = null;
  remoteDescription: RTCSessionDescriptionInit | null = null;
  onicecandidate: ((event: { candidate: { candidate: string } | null }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  ontrack: ((event: { track: Track }) => void) | null = null;
  ondatachannel: ((event: { channel: { close(): void } }) => void) | null = null;
  connectionState = 'new';
  close = vi.fn(); addTransceiver = vi.fn(); addIceCandidate = vi.fn(async () => {});
  createOffer = vi.fn(async () => ({ type: 'offer' as const, sdp: 'v=0\r\nm=video 9 RTP/AVP 96\r\na=sendonly\r\n' }));
  createAnswer = vi.fn(async () => ({ type: 'answer' as const, sdp: 'v=0\r\nm=video 9 RTP/AVP 96\r\na=recvonly\r\n' }));
  setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => { this.localDescription = description; });
  setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => { this.remoteDescription = description; });
  constructor(public config: RTCConfiguration) { pcs.push(this); }
}
const presenter = { peer_id: 'teacher-peer', generation: 1 };
const viewer = { peer_id: 'student-peer', generation: 1 };
const session = { state: 'LIVE', me: presenter, presenter, viewers: [viewer] } as Session;
const display = vi.fn();
beforeEach(() => { pcs.length = 0; display.mockReset(); vi.stubGlobal('isSecureContext', true); vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: display } }); vi.stubGlobal('RTCPeerConnection', PC); vi.stubGlobal('MediaStream', Stream); });
afterEach(() => vi.unstubAllGlobals());

describe('미디어 수명주기 · 실제 화면 캡처 없음', () => {
  it('명시적 선택 전 캡처가 없고 학생은 선택할 수 없다', async () => {
    const teacher = new MediaRoom(true, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    const student = new MediaRoom(false, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    expect(display).not.toHaveBeenCalled();
    await expect(student.chooseScreen()).rejects.toThrow();
    expect(display).not.toHaveBeenCalled(); teacher.close(); student.close();
  });
  it('오디오 없이 직접 선택하고 영상 sendonly·외부 ICE 없는 연결을 정리한다', async () => {
    const track = new Track(); display.mockResolvedValue(new Stream([track]));
    const send = vi.fn(async (_peer: Peer, _kind: Signal['kind'], _payload: string) => {}); const show = vi.fn();
    const room = new MediaRoom(true, send, show, vi.fn(), vi.fn());
    await room.chooseScreen(); await room.sync(session);
    expect(display).toHaveBeenCalledWith({ video: true, audio: false });
    expect(pcs[0].config).toEqual({ iceServers: [] });
    expect(pcs[0].addTransceiver.mock.calls[0][1]).toMatchObject({ direction: 'sendonly' });
    expect(send.mock.calls[0][1]).toBe('OFFER');
    room.close(); expect(track.stop).toHaveBeenCalledOnce(); expect(pcs[0].close).toHaveBeenCalledOnce(); expect(show).toHaveBeenLastCalledWith(null);
  });
  it('캡처 프롬프트 중 종료하면 늦게 선택된 트랙도 즉시 중지한다', async () => {
    let resolve!: (stream: Stream) => void;
    display.mockReturnValue(new Promise(done => { resolve = done; }));
    const track = new Track(); const show = vi.fn(); const room = new MediaRoom(true, vi.fn(), show, vi.fn(), vi.fn());
    const pending = room.chooseScreen(); room.close(); resolve(new Stream([track]));
    await expect(pending).rejects.toThrow(); expect(track.stop).toHaveBeenCalledOnce(); expect(pcs).toHaveLength(0);
  });
  it('허가 거절·오디오 유입·브라우저 미지원은 송출하지 않는다', async () => {
    const room = new MediaRoom(true, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    display.mockRejectedValueOnce(new DOMException('private-device', 'NotAllowedError'));
    await expect(room.chooseScreen()).rejects.toThrow();
    const audio = new Track(); audio.kind = 'audio'; const video = new Track();
    display.mockResolvedValueOnce(new Stream([audio, video])); await expect(room.chooseScreen()).rejects.toThrow();
    expect(audio.stop).toHaveBeenCalledOnce(); expect(video.stop).toHaveBeenCalledOnce();
    vi.stubGlobal('isSecureContext', false); await expect(room.chooseScreen()).rejects.toThrow(); room.close();
  });
  it('브라우저 공유 종료와 네트워크 단절은 캡처·연결을 정리한다', async () => {
    const track = new Track(); display.mockResolvedValue(new Stream([track]));
    const ended = vi.fn(); const room = new MediaRoom(true, vi.fn(), vi.fn(), vi.fn(), ended);
    await room.chooseScreen(); await room.sync(session); track.onended?.();
    expect(track.stop).toHaveBeenCalledOnce(); expect(ended).toHaveBeenCalledOnce(); expect(pcs[0].close).toHaveBeenCalledOnce();
  });
  it('학생 수신 ICE를 SDP 뒤 적용하고 recvonly 답변만 보낸다', async () => {
    const send = vi.fn(async (_peer: Peer, _kind: Signal['kind'], _payload: string) => {}); const show = vi.fn(); const fail = vi.fn();
    const room = new MediaRoom(false, send, show, fail, vi.fn());
    const student = { ...session, me: viewer, viewers: [] };
    await room.receive({ sequence: 1, sender_peer_id: presenter.peer_id, generation: 1, kind: 'ICE', payload: 'candidate:demo' }, student);
    expect(pcs[0].addIceCandidate).not.toHaveBeenCalled();
    await room.receive({ sequence: 2, sender_peer_id: presenter.peer_id, generation: 1, kind: 'OFFER', payload: 'v=0\r\nm=video 9 RTP/AVP 96\r\na=sendonly\r\n' }, student);
    expect(pcs[0].addTransceiver).toHaveBeenCalledWith('video', { direction: 'recvonly' });
    expect(pcs[0].addIceCandidate).toHaveBeenCalledWith({ candidate: 'candidate:demo', sdpMLineIndex: 0 });
    expect(send.mock.calls[0][1]).toBe('ANSWER');
    const remote = new Track(); pcs[0].ontrack?.({ track: remote }); expect(show).toHaveBeenCalled();
    pcs[0].connectionState = 'disconnected'; pcs[0].onconnectionstatechange?.();
    expect(remote.stop).toHaveBeenCalledOnce(); expect(fail).toHaveBeenCalledOnce(); room.close();
  });
  it('현재 목록에서 폐기되거나 재연결된 시청자 연결을 닫는다', async () => {
    const track = new Track(); display.mockResolvedValue(new Stream([track]));
    const room = new MediaRoom(true, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    await room.chooseScreen(); await room.sync(session); await room.sync({ ...session, viewers: [] });
    expect(pcs[0].close).toHaveBeenCalledOnce();
    await room.receive({ sequence: 1, sender_peer_id: viewer.peer_id, generation: 1, kind: 'ICE', payload: 'candidate:old' }, { ...session, viewers: [] }); room.close();
  });
  it('한 시청자 단절이나 잘못된 응답은 교수와 다른 시청자의 송출을 종료하지 않는다', async () => {
    const track = new Track(); display.mockResolvedValue(new Stream([track]));
    const failed = vi.fn(); const peerFailed = vi.fn();
    const room = new MediaRoom(true, vi.fn(), vi.fn(), failed, vi.fn(), peerFailed);
    const second = { peer_id: 'second-student', generation: 1 };
    const two = { ...session, viewers: [viewer, second] };
    await room.chooseScreen(); await room.sync(two);
    pcs[0].connectionState = 'disconnected'; pcs[0].onconnectionstatechange?.();
    expect(pcs[0].close).toHaveBeenCalledOnce(); expect(pcs[1].close).not.toHaveBeenCalled();
    expect(track.stop).not.toHaveBeenCalled(); expect(failed).not.toHaveBeenCalled(); expect(peerFailed).toHaveBeenCalledOnce();
    await room.sync(two); expect(pcs).toHaveLength(2);
    pcs[1].setRemoteDescription.mockRejectedValueOnce(new Error('bad peer description'));
    await room.receive({ sequence: 1, sender_peer_id: second.peer_id, generation: 1, kind: 'ANSWER', payload: 'bad' }, two);
    expect(pcs[1].close).toHaveBeenCalledOnce(); expect(track.stop).not.toHaveBeenCalled(); expect(failed).not.toHaveBeenCalled();
    await room.sync({ ...two, viewers: [{ ...viewer, generation: 2 }] }); expect(pcs).toHaveLength(3);
    room.close(); expect(track.stop).toHaveBeenCalledOnce();
  });
  it('교수 세대가 바뀌면 이전 수신 트랙과 핸들러를 정리하고 늦은 트랙을 거부한다', async () => {
    const show = vi.fn(); const room = new MediaRoom(false, vi.fn(), show, vi.fn(), vi.fn());
    const student = { ...session, me: viewer, viewers: [] };
    await room.receive({ sequence: 1, sender_peer_id: presenter.peer_id, generation: 1, kind: 'OFFER', payload: 'v=0\r\nm=video 9 RTP/AVP 96\r\na=sendonly\r\n' }, student);
    const late = pcs[0].ontrack!; const remote = new Track(); late({ track: remote });
    await room.sync({ ...student, presenter: { ...presenter, generation: 2 } });
    expect(remote.stop).toHaveBeenCalledOnce(); expect(show).toHaveBeenLastCalledWith(null);
    expect(pcs[0].ontrack).toBeNull(); expect(pcs[0].onicecandidate).toBeNull();
    const stale = new Track(); late({ track: stale }); expect(stale.stop).toHaveBeenCalledOnce();
    expect(show).toHaveBeenLastCalledWith(null); room.close();
  });
});
