import { useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ApiError } from '../../lib/api';
import * as api from './api';

const LABELS: Record<api.Kind, string> = { ADMISSION_RESULT: '입학결과', ADMISSION_WITHDRAWAL: '등록포기', CERTIFICATE: '증명', TUITION: '등록금', PROTECTED_COUNSEL: '보호상담' };
const WARNING = '가상 · 공식 효력 없음 · 프로세스 메모리(서버 재시작 시 초기화)';
const BUTTON = 'min-h-11 rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-50';
type Intent = { type: 'create'; body: api.Create; key: string } | { type: 'advance'; item: api.Item; key: string } | { type: 'remove'; item: api.Item };
const explanation = (error: unknown) => error instanceof ApiError && error.status === 503 ? '가상 서비스 API가 아직 연결되지 않았습니다. 처리가 완료된 것으로 표시하지 않습니다.'
  : error instanceof ApiError && error.status === 401 ? '로그인이 만료되어 가상 서비스 기록을 지웠습니다. 다시 로그인해 주세요.'
  : error instanceof ApiError && error.status === 403 ? '현재 접근 권한이 없어 가상 서비스 기록을 지웠습니다.'
  : error instanceof ApiError && error.status === 409 ? '개정 또는 처리 상태가 달라졌습니다. 목록을 다시 조회한 후 확인해 주세요.'
  : error instanceof ApiError && error.status === 404 ? '이 가상 요청을 찾을 수 없습니다. 목록을 다시 조회해 주세요.'
  : error instanceof ApiError && error.status === 429 ? '가상 서비스의 메모리 안전 한도에 도달했습니다. 자동 재시도하지 않습니다.'
  : '처리 결과를 확인하지 못했습니다. 같은 요청을 다시 확인할 수 있습니다. 실제 민감정보를 입력하지 마세요.';

/** Only the common auth owner mounts this page after verifying /auth/me. No token storage. */
export default function DemoStudentServices({ sessionGeneration }: { sessionGeneration: number | string }) {
  return <Workspace key={sessionGeneration} />;
}
function Workspace() {
  const [kind, setKind] = useState<api.Kind>('ADMISSION_RESULT');
  const [pending, setPending] = useState(false);
  // Parent-level latch: a 401/403 in any panel blocks tab remounts until sessionGeneration changes.
  const [denied, setDenied] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (pending || denied || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? api.KINDS.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + api.KINDS.length) % api.KINDS.length;
    setKind(api.KINDS[next]); tabs.current[next]?.focus();
  }
  return <section className="mx-auto grid max-w-4xl gap-5 p-4" style={{ minWidth: 0, overflowWrap: 'anywhere' }} aria-labelledby="demo-services-title">
    <header><h1 id="demo-services-title" className="text-2xl font-semibold">가상 학생서비스</h1><p className="mt-2 rounded-lg bg-amber-50 p-3 font-medium">{WARNING}</p></header>
    <p>학교 공식 시스템과 연결되지 않은 처리 연습입니다. 실제 계좌·성적·사건 내용·연락처를 받지 않습니다. 가상 상담은 실제 상담 접수나 긴급 신고가 아닙니다.</p>
    <div role="tablist" aria-label="가상 학생서비스 종류" className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {api.KINDS.map((value, index) => <button key={value} ref={element => { tabs.current[index] = element; }} role="tab" id={`demo-tab-${value}`} aria-controls="demo-services-panel" aria-selected={kind === value} tabIndex={kind === value ? 0 : -1}
        disabled={pending || denied} className={`${BUTTON} ${kind === value ? 'bg-slate-900 text-white' : 'bg-white'}`} onKeyDown={event => move(event, index)} onClick={() => { if (!denied) setKind(value); }}>{LABELS[value]}</button>)}
    </div>
    <ServicePanel key={kind} kind={kind} onPending={setPending} onDenied={() => setDenied(true)} />
  </section>;
}
function ServicePanel({ kind, onPending, onDenied }: { kind: api.Kind; onPending: (pending: boolean) => void; onDenied: () => void }) {
  const [items, setItems] = useState<api.Item[]>([]), [scenario, setScenario] = useState<api.Scenario>('STANDARD');
  const [consent, setConsent] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [phase, setPhase] = useState<'read' | 'write' | null>('read');
  const [loaded, setLoaded] = useState(false);
  const [denied, setDenied] = useState(false), [stale, setStale] = useState(false), [retry, setRetry] = useState(false);
  const [confirm, setConfirm] = useState<{ type: 'advance' | 'remove'; item: api.Item } | null>(null);
  const intent = useRef<Intent | null>(null);
  const life = useRef({ alive: false, epoch: 0, busy: false, blocked: false, controller: null as AbortController | null });
  function current(epoch: number, controller: AbortController) { return life.current.alive && epoch === life.current.epoch && !controller.signal.aborted; }
  function fail(cause: unknown) {
    setError(explanation(cause));
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) {
      life.current.blocked = true; setDenied(true); onDenied(); setItems([]); setConsent(false); setScenario('STANDARD'); setConfirm(null); intent.current = null; setRetry(false);
    } else if (cause instanceof ApiError && [404, 409, 429].includes(cause.status)) { setStale(true); intent.current = null; setRetry(false); }
    else setRetry(intent.current !== null);
  }
  function start(type: 'read' | 'write') {
    const state = life.current;
    if (!state.alive || state.busy || state.blocked) return null;
    const controller = new AbortController(); state.controller = controller; state.busy = true;
    const epoch = ++state.epoch; setPhase(type); setError(''); setNotice(''); onPending(true);
    return { epoch, controller };
  }
  function finish(epoch: number, controller: AbortController) {
    if (current(epoch, controller)) { life.current.busy = false; setPhase(null); onPending(false); }
  }
  async function load() {
    const operation = start('read'); if (!operation) return;
    const { epoch, controller } = operation;
    setItems([]); setLoaded(false); setStale(true); setConfirm(null);
    try {
      const data = await api.list(controller.signal);
      if (!current(epoch, controller)) return;
      setItems(data.items); setLoaded(true); setStale(false); setConfirm(null);
    } catch (cause) { if (current(epoch, controller)) fail(cause); }
    finally { finish(epoch, controller); }
  }
  useLayoutEffect(() => {
    life.current.alive = true; life.current.epoch++; life.current.busy = false; void load();
    return () => { life.current.alive = false; life.current.epoch++; life.current.controller?.abort(); onPending(false); };
  }, []);
  async function execute(value: Intent) {
    const operation = start('write'); if (!operation) return;
    const { epoch, controller } = operation; intent.current = value; setRetry(false);
    try {
      let receipt: api.Item | undefined;
      if (value.type === 'create') receipt = await api.create(value.body, value.key, controller.signal);
      else if (value.type === 'advance') receipt = await api.advance(value.item, value.key, controller.signal);
      else await api.remove(value.item, controller.signal);
      if (!current(epoch, controller)) return;
      const data = await api.list(controller.signal);
      if (!current(epoch, controller)) return;
      const rank = { REQUESTED: 0, IN_PROGRESS: 1, COMPLETED: 2 };
      const observed = receipt && data.items.find(item => item.id === receipt.id);
      if (value.type === 'remove' ? data.items.some(item => item.id === value.item.id)
        : !receipt || !observed || observed.kind !== receipt.kind || observed.scenario !== receipt.scenario
          || observed.revision < receipt.revision || rank[observed.status] < rank[receipt.status]) throw new ApiError('INVALID_RESPONSE', 200);
      setItems(data.items); setLoaded(true); setConfirm(null); setConsent(false); setStale(false); intent.current = null;
      setNotice(value.type === 'remove' ? '가상 요청 취소 후 목록을 다시 확인했습니다. 실제 등록·납부·상담은 바뀌지 않습니다.' : '가상 처리 후 서버 목록을 다시 확인했습니다. 공식 효력은 없습니다.');
    } catch (cause) { if (current(epoch, controller)) fail(cause); }
    finally { finish(epoch, controller); }
  }
  function create(event: FormEvent) {
    event.preventDefault(); if (!consent || denied || stale || retry || life.current.busy) return;
    void execute({ type: 'create', body: { kind, scenario, consent: true }, key: crypto.randomUUID() });
  }
  const locked = phase !== null || denied || stale || retry;
  const visible = items.filter(item => item.kind === kind);
  return <section role="tabpanel" id="demo-services-panel" aria-labelledby={`demo-tab-${kind}`} className="grid min-w-0 gap-4">
    <h2 className="text-xl font-semibold">{LABELS[kind]} · 가상 처리 연습</h2>
    <button className={BUTTON} disabled={phase !== null || denied} onClick={() => void load()}>가상 요청 다시 조회</button>
    {phase && <p role="status">{phase === 'read' ? '가상 요청을 조회 중…' : '가상 처리와 목록을 확인 중…'}</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {retry && !denied && <button className={BUTTON} disabled={phase !== null} onClick={() => { if (intent.current) void execute(intent.current); }}>같은 요청 다시 확인</button>}
    {!denied && <>
      <form onSubmit={create} className="grid min-w-0 gap-3 rounded-xl border border-slate-200 p-4">
        <label className="grid gap-1">실제 정보 없는 가상 예시<select className="min-h-11 rounded border p-2" value={scenario} disabled={locked} onChange={event => { setScenario(event.target.value as api.Scenario); setConsent(false); }}>
          <option value="STANDARD">기본 가상 예시</option><option value="REVIEW_EXAMPLE">추가 확인 가상 예시</option>
        </select></label>
        <label className="flex min-h-11 items-start gap-2 py-2"><input type="checkbox" checked={consent} disabled={locked} onChange={event => setConsent(event.target.checked)} className="mt-1" />가상·공식 효력 없음·재시작 초기화를 이해하고 가상 요청을 만들겠습니다.</label>
        <button className={`${BUTTON} bg-blue-700 text-white`} disabled={locked || !consent}>확인하고 가상 요청 만들기</button>
      </form>
      {loaded && phase !== 'read' && !visible.length && <p>이 종류의 가상 요청이 없습니다. 조회만으로 요청이 생성되지 않습니다.</p>}
      <ul className="grid min-w-0 gap-3" aria-label={`${LABELS[kind]} 가상 요청 목록`}>
        {visible.map(item => <li key={item.id} className="grid min-w-0 gap-2 rounded-xl border border-slate-200 p-4">
          <h3 className="font-semibold">{item.title}</h3><p>{item.status_label} · 가상 개정 {item.revision}</p><p className="text-sm">{WARNING}</p>
          {item.outcome_text && <p>{item.outcome_text}</p>}{item.document_text && <pre className="whitespace-pre-wrap break-words rounded bg-slate-50 p-3 font-sans" style={{ overflowWrap: 'anywhere' }}>{item.document_text}</pre>}
          <div className="flex flex-wrap gap-2">
            {item.status !== 'COMPLETED' && <button className={BUTTON} disabled={locked} onClick={() => setConfirm({ type: 'advance', item })}>가상 처리 한 단계 진행</button>}
            <button className={BUTTON} disabled={locked} onClick={() => setConfirm({ type: 'remove', item })}>가상 요청 취소</button>
          </div>
          {confirm?.item.id === item.id && <fieldset className="grid gap-2 rounded border border-amber-300 p-3"><legend>가상 처리 확인</legend>
            <p>{confirm.type === 'remove' ? '이 가상 요청만 취소합니다. 실제 학교 업무를 취소하지 않습니다.' : '고정된 가상 상태를 한 단계 진행합니다. 실제 심사·납부·상담이 아닙니다.'}</p>
            <div className="flex flex-wrap gap-2"><button className={BUTTON} disabled={locked} onClick={() => void execute(confirm.type === 'remove' ? { type: 'remove', item } : { type: 'advance', item, key: crypto.randomUUID() })}>{confirm.type === 'remove' ? '확인하고 가상 요청 취소' : '확인하고 가상 단계 진행'}</button>
              <button className={BUTTON} disabled={phase !== null} onClick={() => setConfirm(null)}>가상 처리 돌아가기</button></div>
          </fieldset>}
        </li>)}
      </ul>
    </>}
  </section>;
}
