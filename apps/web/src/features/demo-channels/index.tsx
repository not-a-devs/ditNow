import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { cancelDemoChannel, createDemoChannel, listDemoChannels, type DemoChannelRequest, type Purpose, type RequestedKind } from './api';

export { default as OperationalGates } from './OperationalGates';

const PURPOSES: [Purpose, string][] = [['study', '스터디'], ['project', '프로젝트'], ['social', '친목']];
const STATUS = { CREATED: '가상 생성됨 · 실제 채널 아님', PENDING_REVIEW: '검토 대기 · 실제 검토·승인 없음' } as const;
const isAuth = (error: unknown) => error instanceof ApiError && (error.status === 401 || error.status === 403);
// The server answered with a definite rejection, so nothing was created.
const isDefiniteReject = (error: unknown) => error instanceof ApiError && error.code !== 'INVALID_RESPONSE' && [400, 404, 409, 422].includes(error.status);
const message = (error: unknown) => error instanceof ApiError && error.status === 503
  ? '가상 채널 신청 연결을 준비하고 있습니다.'
  : isAuth(error) ? '로그인이 만료되었거나 접근 권한이 없어 신청 정보를 지웠습니다. 다시 로그인한 뒤 이용하세요.'
  : error instanceof ApiError && error.status === 404 ? '신청을 찾을 수 없습니다. 목록을 다시 불러왔습니다.'
  : error instanceof ApiError && error.status === 409 ? '신청 상태가 바뀌었거나 개인 한도(20건)에 도달했습니다. 목록을 다시 불러왔습니다.'
  : error instanceof ApiError && error.status === 400 ? '입력값을 확인하세요. 동의가 필요합니다.'
  : error instanceof ApiError && error.code === 'INVALID_RESPONSE' ? '가상 신청 응답의 형식을 확인하지 못했습니다.'
  : '요청 결과를 확인하지 못했습니다. 목록을 다시 불러와 확인해 주세요.';
const UNCERTAIN_CREATE = '신청이 기록되었는지 확인하지 못했습니다. 중복 신청을 막기 위해 목록을 다시 불러와 확인하기 전까지 새 신청을 할 수 없습니다.';
const same = (a: DemoChannelRequest, b: DemoChannelRequest) => a.id === b.id && a.purpose === b.purpose
  && a.requested_kind === b.requested_kind && a.status === b.status && a.revision === b.revision;

/** Shared auth owner must change this generation (or remount) on account/session changes. */
export default function DemoChannels({ sessionGeneration = 0 }: { sessionGeneration?: number }) {
  // A new generation is a new instance: old account state is dropped during commit.
  return <DemoChannelsSession key={sessionGeneration} />;
}

interface Run { signal: AbortSignal; current: () => boolean; finish: () => void }

function DemoChannelsSession() {
  const [items, setItems] = useState<DemoChannelRequest[] | null>(null);
  const [purpose, setPurpose] = useState<Purpose>('study'), [kind, setKind] = useState<RequestedKind>('FREE'), [consent, setConsent] = useState(false);
  const [pending, setPending] = useState<'read' | 'write' | null>('read');
  const [locked, setLocked] = useState(false), [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const alive = useRef(false), epoch = useRef(0), busy = useRef(false), lockedRef = useRef(false), uncertainRef = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useLayoutEffect(() => {
    alive.current = true;
    return () => { alive.current = false; epoch.current++; busy.current = false; controller.current?.abort(); controller.current = null; };
  }, []);

  function begin(kindOf: 'read' | 'write'): Run | null {
    if (!alive.current || lockedRef.current || busy.current) return null;
    busy.current = true; controller.current?.abort();
    const version = ++epoch.current, request = new AbortController(); controller.current = request;
    setPending(kindOf); setError(''); setNotice('');
    return {
      signal: request.signal,
      current: () => alive.current && !lockedRef.current && version === epoch.current && !request.signal.aborted,
      finish: () => { if (alive.current && version === epoch.current) { busy.current = false; controller.current = null; setPending(null); } },
    };
  }
  /** 401/403 for this generation: discard private content and intent; only a new generation resumes. */
  function lockIfAuth(cause: unknown) {
    if (!isAuth(cause)) return false;
    lockedRef.current = true; busy.current = false; epoch.current++; controller.current?.abort(); controller.current = null;
    setLocked(true); setItems(null); setConsent(false); setPurpose('study'); setKind('FREE');
    setPending(null); setNotice(''); setError(message(cause));
    return true;
  }
  function markUncertain(text: string) { uncertainRef.current = true; setUncertain(true); setConsent(false); setError(text); }
  /** Fallback reread after a definite 404/409; also latches 401/403. */
  async function reread(run: Run) {
    try { const list = await listDemoChannels(run.signal); if (run.current()) setItems(list.items); }
    catch (cause) { if (run.current()) lockIfAuth(cause); }
  }

  async function load() {
    const run = begin('read'); if (!run) return;
    try {
      const list = await listDemoChannels(run.signal);
      if (!run.current()) return;
      setItems(list.items);
      if (uncertainRef.current) {
        uncertainRef.current = false; setUncertain(false);
        setNotice('목록을 다시 불러왔습니다. 이전 신청이 목록에 있는지 확인한 뒤 필요할 때만 다시 신청하세요.');
      }
    } catch (cause) {
      if (run.current() && !lockIfAuth(cause)) setError(message(cause));
    } finally { run.finish(); }
  }

  useEffect(() => { void load(); }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!consent || uncertainRef.current) return;
    const body = { purpose, requested_kind: kind, consent: true as const };
    const run = begin('write'); if (!run) return;
    void (async () => {
      try {
        let created: DemoChannelRequest;
        try { created = await createDemoChannel(body, run.signal); }
        catch (cause) {
          if (!run.current() || lockIfAuth(cause)) return;
          if (!isDefiniteReject(cause)) return markUncertain(UNCERTAIN_CREATE);
          setError(message(cause));
          if (cause instanceof ApiError && cause.status === 409) await reread(run);
          return;
        }
        if (!run.current()) return;
        // The write intent is consumed; until readback confirms it, no new create is allowed.
        setConsent(false); uncertainRef.current = true;
        if (created.purpose !== body.purpose || created.requested_kind !== body.requested_kind) return markUncertain(UNCERTAIN_CREATE);
        let list;
        try { list = await listDemoChannels(run.signal); }
        catch (cause) { if (run.current() && !lockIfAuth(cause)) markUncertain(UNCERTAIN_CREATE); return; }
        if (!run.current()) return;
        setItems(list.items);
        const receipt = list.items.find(item => item.id === created.id);
        if (!receipt || !same(receipt, created)) return markUncertain(UNCERTAIN_CREATE);
        uncertainRef.current = false; setUncertain(false);
        setNotice(created.requested_kind === 'OFFICIAL'
          ? '공식 채널 신청을 가상으로 기록했습니다. 실제 검토·승인·공식 배지는 제공되지 않습니다.'
          : '가상 자유 채널 신청이 생성되었습니다. 실제 채널이나 메시지는 만들지 않습니다.');
      } finally { run.finish(); }
    })();
  }

  function cancel(item: DemoChannelRequest) {
    const run = begin('write'); if (!run) return;
    void (async () => {
      try {
        try {
          const cancelled = await cancelDemoChannel(item, run.signal);
          if (!run.current()) return;
          if (cancelled !== item.id) throw new ApiError('INVALID_RESPONSE', 200);
        }
        catch (cause) {
          if (!run.current() || lockIfAuth(cause)) return;
          setError(message(cause));
          if (cause instanceof ApiError && [404, 409].includes(cause.status)) await reread(run);
          return;
        }
        if (!run.current()) return;
        let list;
        try { list = await listDemoChannels(run.signal); }
        catch (cause) { if (run.current() && !lockIfAuth(cause)) setError('취소 결과를 목록에서 확인하지 못했습니다. 목록을 다시 불러와 확인해 주세요.'); return; }
        if (!run.current()) return;
        setItems(list.items);
        if (list.items.some(row => row.id === item.id)) setError('취소 응답을 받았지만 목록에 신청이 남아 있어 취소를 확인하지 못했습니다. 목록을 다시 불러와 확인해 주세요.');
        else setNotice('가상 신청을 취소했습니다.');
      } finally { run.finish(); }
    })();
  }

  const disabled = pending !== null || locked;
  return <section className="mx-auto grid max-w-3xl gap-4 p-4" aria-labelledby="demo-channels-title">
    <header><h1 id="demo-channels-title" className="text-2xl font-semibold">채널 신청 체험(DEMO)</h1>
      <p>가상 신청은 서버 메모리에만 있고 재시작하면 사라집니다. 실제 학과 채널·메시지·권한을 만들지 않습니다.</p></header>
    <p className="rounded bg-amber-50 p-3">공식 채널 신청은 항상 &lsquo;검토 대기&rsquo;로 남습니다. 실제 공식 승인, 공식 배지, 운영자·교직원 권한은 부여되지 않습니다.</p>
    <form className="grid gap-3 rounded border p-3" onSubmit={submit}>
      <label className="grid gap-1">목적<select className="rounded border p-2" value={purpose} disabled={disabled} onChange={event => setPurpose(event.target.value as Purpose)}>
        {PURPOSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <fieldset className="grid gap-1"><legend>신청 종류</legend>
        <label><input type="radio" name="demo-kind" checked={kind === 'FREE'} disabled={disabled} onChange={() => setKind('FREE')} /> 자유 채널(가상 생성)</label>
        <label><input type="radio" name="demo-kind" checked={kind === 'OFFICIAL'} disabled={disabled} onChange={() => setKind('OFFICIAL')} /> 공식 채널(가상 신청 · 승인 없음)</label>
      </fieldset>
      <label><input type="checkbox" checked={consent} disabled={disabled} onChange={event => setConsent(event.target.checked)} /> 가상 체험이며 실제 채널·승인이 아님을 확인합니다</label>
      <p>채널 이름은 목적과 종류로 자동 생성되며 직접 입력할 수 없습니다. 개인 한도 20건.</p>
      <button disabled={disabled || uncertain || !consent} className="rounded bg-blue-700 p-3 text-white">{pending === 'write' ? '처리 중…' : '가상 신청'}</button>
    </form>
    <button disabled={disabled} className="rounded border p-3" onClick={() => void load()}>목록 다시 불러오기</button>
    {pending === 'read' && <p role="status">내 가상 신청을 불러오는 중…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!locked && items && (items.length === 0 ? <p>가상 신청이 없습니다.</p> : <ul className="grid gap-2" aria-label="내 가상 채널 신청">
      {items.map(item => <li key={item.id} className="flex items-center justify-between gap-2 rounded border p-3">
        <span><strong>{item.title}</strong><br />{STATUS[item.status]}</span>
        <button disabled={disabled} className="rounded border p-2" aria-label={`${item.title} 취소`} onClick={() => cancel(item)}>취소</button>
      </li>)}</ul>)}
  </section>;
}
