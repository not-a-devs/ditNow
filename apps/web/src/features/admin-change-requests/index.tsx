import { useLayoutEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import {
  REASONS, SCOPES, TARGETS, createProposal, intentTracker, loadProposals, matchesReceipt, submitProposal, withdrawProposal,
  type Proposal, type ProposalList, type Reason, type Scope, type Target,
} from './api';

const LABEL: Record<string, string> = {
  STUDENT_DEMO_A: '가상 학생 A', STUDENT_DEMO_B: '가상 학생 B', DEPARTMENT_STUDENT: '학과 학생 범위(가상)', YEAR_STUDENT: '학년 학생 범위(가상)',
  ACADEMIC_DEMO: '학사 시연 사유', CORRECTION_DEMO: '정정 시연 사유', DRAFT: '초안', SUBMITTED: '제출됨(승인 아님)', WITHDRAWN: '철회됨(기록 보존)',
};
const FORM = { target: TARGETS[0] as Target, scope: SCOPES[0] as Scope, reason: REASONS[0] as Reason };
const message = (error: unknown) => !(error instanceof ApiError) ? '결과를 확인하지 못했습니다. 자동 재시도하지 않습니다. 목록을 다시 조회해 주세요.'
  : error.status === 503 ? '시연 제안 기능이 아직 연결되지 않았습니다(기본 비활성).'
  : error.status === 401 ? '로그인이 만료되어 화면의 개인 정보를 지웠습니다.'
  : error.status === 403 ? '현재 계정에 시연 제안 권한이 없어 화면을 지웠습니다. 권한은 이 화면에서 부여되지 않습니다.'
  : error.status === 404 ? '해당 제안을 찾을 수 없습니다.'
  : error.status === 409 ? '제안 상태나 개정이 바뀌었습니다. 목록을 다시 조회해 주세요.'
  : error.status === 429 ? '시연 메모리 기술 한도에 도달했습니다.'
  : error.status === 400 ? '고정 선택지와 동의를 확인해 주세요.'
  : error.code === 'INVALID_RESPONSE' ? '서버 응답 형식을 확인하지 못했습니다.'
  : '결과를 확인하지 못했습니다. 자동 재시도하지 않습니다. 같은 입력으로 다시 보내면 같은 요청으로 확인합니다.';

/** The shared auth owner must bump sessionGeneration on every account/session change. */
export default function AdminChangeRequestsPage({ sessionGeneration = 0 }: { sessionGeneration?: number }) {
  const [workspace, setWorkspace] = useState<{ generation: number; list: ProposalList } | null>(null);
  const [form, setForm] = useState(FORM), [consent, setConsent] = useState(false);
  const [pending, setPending] = useState<'read' | 'write' | null>('read');
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [denied, setDenied] = useState<number | null>(null);
  const alive = useRef(false), epoch = useRef(0), busy = useRef(false), generation = useRef(sessionGeneration);
  const controller = useRef<AbortController | null>(null), intent = useRef(intentTracker());
  const locked = denied === sessionGeneration;
  const list = workspace?.generation === sessionGeneration ? workspace.list : null;

  function reset() { setWorkspace(null); setForm(FORM); setConsent(false); setError(''); setNotice(''); intent.current.clear(); }
  function begin(kind: 'read' | 'write') {
    const version = ++epoch.current; controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    busy.current = true; setPending(kind); setError(''); setNotice('');
    return { version, request, current: () => alive.current && version === epoch.current && !request.signal.aborted };
  }
  function finish(version: number) { if (alive.current && version === epoch.current) { busy.current = false; setPending(null); } }
  function fail(cause: unknown) {
    if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
      reset(); setDenied(generation.current); controller.current?.abort();
    } else if (cause instanceof ApiError && cause.status === 409) intent.current.clear();
    setError(message(cause));
  }
  async function load() {
    if (busy.current) return;
    const { version, request, current } = begin('read');
    try { const data = await loadProposals(request.signal); if (current()) setWorkspace({ generation: generation.current, list: data }); }
    catch (cause) { if (current()) { setWorkspace(null); fail(cause); } }
    finally { finish(version); }
  }
  async function mutate(run: (signal: AbortSignal) => Promise<Proposal>, done: string) {
    if (busy.current || locked) return;
    const { version, request, current } = begin('write');
    try {
      const receipt = await run(request.signal);
      if (!current()) return;
      const fresh = await loadProposals(request.signal);
      if (!current()) return;
      setWorkspace({ generation: generation.current, list: fresh });
      if (matchesReceipt(fresh, receipt)) { intent.current.clear(); setConsent(false); setNotice(done); }
      else setError('응답과 새 조회 결과가 일치하지 않아 성공으로 표시하지 않았습니다. 다시 조회해 주세요.');
    } catch (cause) { if (current()) fail(cause); }
    finally { finish(version); }
  }
  useLayoutEffect(() => {
    alive.current = true; generation.current = sessionGeneration; busy.current = false; reset(); void load();
    return () => { alive.current = false; epoch.current++; controller.current?.abort(); busy.current = false; };
  }, [sessionGeneration]);

  function create(event: FormEvent) {
    event.preventDefault(); if (!consent) return;
    const body = { target_code: form.target, proposal_scope: form.scope, reason_code: form.reason, consent: true as const };
    const key = intent.current.key({ op: 'create', ...body });
    void mutate(signal => createProposal(body, key, signal), '시연 초안을 만들었고 새 조회로 확인했습니다. 실제 권한 변경은 없습니다.');
  }
  function submit(item: Proposal) {
    const key = intent.current.key({ op: 'submit', id: item.id, revision: item.revision });
    void mutate(signal => submitProposal(item.id, item.revision, key, signal), '시연 제안을 제출 상태로 바꿨습니다. 승인·실행되지 않습니다.');
  }
  const withdraw = (item: Proposal) => void mutate(signal => withdrawProposal(item.id, item.revision, signal), '시연 제안을 철회했습니다. 기록은 보존됩니다.');
  const disabled = pending !== null || locked;

  return <section className="mx-auto grid max-w-3xl gap-4 p-4" aria-labelledby="acr-title">
    <header><h1 id="acr-title" className="text-2xl font-semibold">관리 변경 제안 (시연)</h1>
      <p>실제 관리자 기능이 아니며 실제 역할·권한·계정을 바꾸지 않습니다. 가상 대상 코드만 사용하며 승인·실행 단계가 없습니다.</p></header>
    <p className="rounded bg-amber-50 p-3">DEMO · PROCESS_MEMORY · 공식 효력 없음 · 서버 재시작 시 초기화됩니다. 실명·학번 등 개인 정보를 입력하는 칸은 없습니다.</p>
    <button className="rounded border p-3" disabled={disabled} onClick={() => void load()}>목록 다시 조회</button>
    {pending === 'read' && <p role="status">본인 제안을 조회 중…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {locked && <p>새 로그인 세션이 확인될 때까지 이 화면은 비활성입니다.</p>}
    {list && !locked && <>
      <form className="grid gap-3 rounded border p-3" onSubmit={create}>
        <label className="grid gap-1">가상 대상<select value={form.target} disabled={disabled} onChange={event => setForm(value => ({ ...value, target: event.target.value as Target }))}>
          {TARGETS.map(code => <option key={code} value={code}>{LABEL[code]}</option>)}</select></label>
        <label className="grid gap-1">제안 범위<select value={form.scope} disabled={disabled} onChange={event => setForm(value => ({ ...value, scope: event.target.value as Scope }))}>
          {SCOPES.map(code => <option key={code} value={code}>{LABEL[code]}</option>)}</select></label>
        <label className="grid gap-1">사유 코드<select value={form.reason} disabled={disabled} onChange={event => setForm(value => ({ ...value, reason: event.target.value as Reason }))}>
          {REASONS.map(code => <option key={code} value={code}>{LABEL[code]}</option>)}</select></label>
        <label><input type="checkbox" checked={consent} disabled={disabled} onChange={event => setConsent(event.target.checked)} /> 시연용 기록이며 실제 권한 변경이 아님을 확인합니다</label>
        <button className="rounded bg-blue-700 p-3 text-white" disabled={disabled || !consent}>{pending === 'write' ? '확인 중…' : '시연 초안 만들기'}</button>
      </form>
      <p>보관 {list.items.length}/{list.owner_cap}건 (기술 한도, 철회 기록 포함)</p>
      {!list.items.length && <p>본인 제안이 없습니다.</p>}
      <ul className="grid gap-2">{list.items.map(item => <li key={item.id} className="rounded border p-3">
        <p>{LABEL[item.target_code]} · {LABEL[item.proposal_scope]} · {LABEL[item.reason_code]}</p>
        <p>{LABEL[item.state]} · 개정 {item.revision}</p>
        {item.state === 'DRAFT' && <button disabled={disabled} onClick={() => submit(item)}>제출</button>}
        {item.state !== 'WITHDRAWN' && <button disabled={disabled} onClick={() => withdraw(item)}>철회</button>}
      </li>)}</ul>
    </>}
  </section>;
}
