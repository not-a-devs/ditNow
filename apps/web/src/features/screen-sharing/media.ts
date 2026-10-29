import { ApiError } from '../../lib/api';
import type { Peer, Session, Signal } from './api';

type Send = (peer: Peer, kind: Signal['kind'], payload: string) => Promise<void>;
interface Connection { pc: RTCPeerConnection; peer: Peer; remoteIce: string[]; localIce: string[]; ready: boolean }

/** No recording/audio/external ICE servers. Creation alone never opens a capture prompt. */
export class MediaRoom {
  private stream: MediaStream | null = null;
  private peers = new Map<string, Connection>();
  private failedPeers = new Map<string, number>();
  private closed = false;
  private choosing = false;
  constructor(private presenter: boolean, private send: Send, private show: (stream: MediaStream | null) => void,
    private failed: () => void, private ended: () => void, private peerFailed: () => void = () => {}) {}

  async chooseScreen(): Promise<void> {
    if (!this.presenter || this.closed || this.choosing || this.stream) throw new Error('Capture unavailable');
    if (!window.isSecureContext || !navigator.mediaDevices?.getDisplayMedia) throw new Error('Capture unsupported');
    this.choosing = true;
    try {
      // Must stay before any await: called only from the explicit UI click handler.
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      if (this.closed || stream.getAudioTracks().length || stream.getVideoTracks().length !== 1) {
        stream.getTracks().forEach(track => track.stop());
        throw new Error('Capture no longer permitted');
      }
      this.stream = stream;
      stream.getVideoTracks()[0].onended = () => { if (!this.closed) { this.close(); this.ended(); } };
      this.show(stream);
    } finally { this.choosing = false; }
  }

  private create(peer: Peer): Connection {
    if (this.closed) throw new Error('Closed');
    const pc = new RTCPeerConnection({ iceServers: [] });
    const entry: Connection = { pc, peer, remoteIce: [], localIce: [], ready: false };
    this.peers.set(peer.peer_id, entry);
    pc.onicecandidate = event => {
      if (!event.candidate || !this.current(entry)) return;
      if (entry.ready) void this.send(peer, 'ICE', event.candidate.candidate).catch(error => this.peerError(entry, error));
      else if (entry.localIce.length < 64) entry.localIce.push(event.candidate.candidate);
      else this.peerError(entry);
    };
    pc.onconnectionstatechange = () => { if (this.current(entry) && ['failed', 'disconnected'].includes(pc.connectionState)) this.peerError(entry); };
    pc.ontrack = event => {
      if (!this.current(entry)) { event.track.stop(); return; }
      if (this.presenter || event.track.kind !== 'video') { event.track.stop(); this.peerError(entry); return; }
      this.clearStream();
      this.stream = new MediaStream([event.track]); this.show(this.stream);
      event.track.onended = () => { if (!this.closed) this.fail(); };
    };
    pc.ondatachannel = event => { event.channel.close(); if (this.current(entry)) this.peerError(entry); };
    return entry;
  }

  private fail() { if (!this.closed) { this.close(); this.failed(); } }
  private current(entry: Connection) { return !this.closed && this.peers.get(entry.peer.peer_id) === entry; }
  private clearStream() { this.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); }); this.stream = null; this.show(null); }
  private drop(entry: Connection, failed = false) {
    entry.pc.ontrack = null; entry.pc.onicecandidate = null; entry.pc.onconnectionstatechange = null; entry.pc.ondatachannel = null;
    entry.remoteIce.length = entry.localIce.length = 0; entry.pc.close();
    if (this.peers.get(entry.peer.peer_id) === entry) this.peers.delete(entry.peer.peer_id);
    if (failed) this.failedPeers.set(entry.peer.peer_id, entry.peer.generation);
    if (!this.presenter) this.clearStream();
  }
  private peerError(entry: Connection, error?: unknown) {
    if (!this.current(entry)) return;
    if (!this.presenter || (error instanceof ApiError && [0, 401, 403, 503].includes(error.status))) { this.fail(); return; }
    this.drop(entry, true); this.peerFailed();
  }
  private async local(entry: Connection, kind: 'OFFER' | 'ANSWER') {
    const description = kind === 'OFFER' ? await entry.pc.createOffer() : await entry.pc.createAnswer();
    if (!this.current(entry)) return;
    await entry.pc.setLocalDescription(description);
    if (!this.current(entry) || !entry.pc.localDescription?.sdp) return;
    await this.send(entry.peer, kind, entry.pc.localDescription.sdp);
    if (!this.current(entry)) return;
    entry.ready = true;
    for (const candidate of entry.localIce.splice(0)) await this.send(entry.peer, 'ICE', candidate);
  }

  async sync(session: Session): Promise<void> {
    if (this.closed || !session.me || !session.presenter || session.state !== 'LIVE') throw new Error('Unavailable session');
    const allowed = this.presenter ? session.viewers : [session.presenter];
    for (const [id, entry] of this.peers) {
      if (!allowed.some(peer => peer.peer_id === id && peer.generation === entry.peer.generation)) {
        this.drop(entry);
      }
    }
    if (this.presenter && this.stream) {
      for (const peer of allowed) {
        if (this.peers.has(peer.peer_id) || this.failedPeers.get(peer.peer_id) === peer.generation) continue;
        const entry = this.create(peer);
        this.stream.getVideoTracks().forEach(track => entry.pc.addTransceiver(track, { direction: 'sendonly', streams: [this.stream!] }));
        try { await this.local(entry, 'OFFER'); } catch (error) { this.peerError(entry, error); }
      }
    }
  }

  async receive(signal: Signal, session: Session): Promise<void> {
    if (this.closed || !session.me || !session.presenter) return;
    const allowed = this.presenter ? session.viewers : [session.presenter];
    const peer = allowed.find(p => p.peer_id === signal.sender_peer_id && p.generation === signal.generation);
    if (!peer) { if (!this.presenter) this.fail(); return; }
    if (this.failedPeers.get(peer.peer_id) === peer.generation) return;
    let entry = this.peers.get(peer.peer_id);
    if (!entry) { if (this.presenter) throw new Error('Missing offer'); entry = this.create(peer); entry.pc.addTransceiver('video', { direction: 'recvonly' }); }
    try {
    if ((signal.kind === 'OFFER' && this.presenter) || (signal.kind === 'ANSWER' && !this.presenter)) throw new Error('Unexpected signal');
    if (signal.kind === 'ICE') {
      if (entry.pc.remoteDescription) await entry.pc.addIceCandidate({ candidate: signal.payload, sdpMLineIndex: 0 });
      else if (entry.remoteIce.length < 64) entry.remoteIce.push(signal.payload);
      else throw new Error('Too many candidates');
      return;
    }
    const type = signal.kind === 'OFFER' ? 'offer' : 'answer';
    await entry.pc.setRemoteDescription({ type, sdp: signal.payload });
    if (!this.current(entry)) return;
    for (const candidate of entry.remoteIce.splice(0)) await entry.pc.addIceCandidate({ candidate, sdpMLineIndex: 0 });
    if (signal.kind === 'OFFER') await this.local(entry, 'ANSWER');
    } catch (error) { this.peerError(entry, error); }
  }

  close(): void {
    this.closed = true;
    for (const entry of [...this.peers.values()]) this.drop(entry);
    this.peers.clear(); this.failedPeers.clear(); this.clearStream();
  }
}
