import { useLayoutEffect, useRef, useState } from 'react';
import { ApiError } from '../../lib/api';
import * as savedApi from '../opportunities/api';
import type { SavedOpportunity } from '../opportunities/types';
import * as api from './api';
import { STEP_LABEL } from './labels';
import type { Interests, OpportunityBrief } from './types';

type Row = { text: string; selected: boolean };
type Intent = { memo: string; saveAttempted: boolean; checks: { text: string; sort: number; key: string; id?: string }[] };

// Evaluation time is a clock, not a content revision. Compare every source/context field used
// by the draft instead; a changed deadline, scope, procedure or caution requires fresh consent.
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${stable(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
export function briefVersion(brief: OpportunityBrief): string {
  return stable([brief.opportunity, brief.match, brief.window, brief.freshness, brief.procedure, brief.cautions, brief.context, brief.provenance]);
}

function validBrief(brief: OpportunityBrief, id: string): boolean {
  return !!brief && brief.opportunity?.id === id && typeof brief.opportunity.title === 'string'
    && brief.provenance?.generator === 'deterministic_rules_v1' && brief.provenance.ai_generated === false
    && brief.provenance.eligibility_guaranteed === false && Array.isArray(brief.procedure);
}

function ownRow(items: SavedOpportunity[], id: string): SavedOpportunity | undefined {
  if (!Array.isArray(items)) throw new Error('Invalid preparation response');
  const row = items.find(item => item?.opportunity_id === id);
  if (row && (!Array.isArray(row.checks) || !Number.isSafeInteger(row.revision) || row.revision < 1
    || row.checks.some(check => typeof check.id !== 'string' || typeof check.text !== 'string'
      || !Number.isSafeInteger(check.sort_order) || check.sort_order < 0))) throw new Error('Invalid preparation response');
  return row;
}

export interface PreparationDraftProps {
  brief: OpportunityBrief;
  interests: Interests;
  onSaved: () => void;
}

/** Suggestions stay in component memory until two explicit review/consent steps. No AI calls. */
export default function PreparationDraft({ brief, interests, onSaved }: PreparationDraftProps) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>(() => brief.procedure.slice(0, 20).map(step => ({ text: STEP_LABEL[step.code], selected: step.available })));
  const [memo, setMemo] = useState('');
  const [source, setSource] = useState(brief);
  const [phase, setPhase] = useState<'edit' | 'review' | 'partial' | 'saved' | 'denied'>('edit');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [existing, setExisting] = useState(false);
  const intent = useRef<Intent | null>(null);
  const life = useRef({ alive: false, epoch: 0, busy: false, controller: null as AbortController | null });
  useLayoutEffect(() => {
    life.current.alive = true; life.current.epoch++;
    return () => { life.current.alive = false; life.current.epoch++; life.current.controller?.abort(); };
  }, []);

  function begin() {
    const state = life.current;
    if (!state.alive || state.busy) return null;
    state.busy = true;
    const epoch = state.epoch;
    const controller = new AbortController(); state.controller = controller;
    const current = () => life.current.alive && life.current.epoch === epoch && !controller.signal.aborted;
    setBusy(true); setError('');
    return { current, signal: controller.signal, finish: () => { if (current()) { state.busy = false; setBusy(false); } } };
  }

  function message(error: unknown): string {
    if (error instanceof ApiError && [401, 403].includes(error.status)) return '로그인 또는 권한이 변경되었습니다. 화면을 닫고 다시 로그인하세요.';
    if (error instanceof ApiError && error.status === 503) return '서버 연결 준비 중입니다. 완료된 저장으로 표시하지 않습니다. 잠시 후 다시 확인하세요.';
    if (error instanceof ApiError && error.status === 409) return '다른 변경과 충돌했습니다. 기존 준비 목록을 확인하세요. 같은 요청 키를 유지하며 자동으로 새 항목을 만들지 않습니다.';
    return '저장을 확인하지 못했습니다. 일부 항목이 이미 반영되었을 수 있습니다. 같은 요청으로 다시 확인하거나 내 준비 목록을 확인하세요.';
  }

  function discardDenied(failure: unknown): boolean {
    if (!(failure instanceof ApiError) || ![401, 403].includes(failure.status)) return false;
    intent.current = null; setRows([]); setMemo(''); setConsent(false); setBusy(false);
    setPhase('denied'); setError(message(failure));
    life.current.epoch++; life.current.controller?.abort();
    return true;
  }

  async function review() {
    const selected = rows.filter(row => row.selected);
    if (!selected.length || selected.some(row => !row.text.trim() || Array.from(row.text.trim()).length > 200)
      || Array.from(memo.trim()).length > 1000 || new Set(selected.map(row => row.text.trim())).size !== selected.length) { setError('서로 다른 준비 항목을 한 개 이상 선택하고 각 1~200자, 메모 1000자 이하로 입력하세요.'); return; }
    const request = begin(); if (!request) return;
    try {
      const fresh = await api.getBrief(brief.opportunity.id, interests, request.signal);
      if (!request.current()) return;
      if (!validBrief(fresh, brief.opportunity.id)) throw new Error('Invalid source');
      if (briefVersion(fresh) !== briefVersion(source)) {
        setSource(fresh); setConsent(false); setError('공고 또는 현재 소속·대상 정보가 바뀌었습니다. 최신 원문과 초안을 다시 검토한 뒤 검토 버튼을 누르세요.'); return;
      }
      const list = await savedApi.listSaved(request.signal);
      if (!request.current()) return;
      setExisting(!!ownRow(list.items, brief.opportunity.id));
      setConsent(false); setPhase('review');
    } catch (failure) { if (request.current() && !discardDenied(failure)) setError(message(failure)); }
    finally { request.finish(); }
  }

  async function save() {
    if (phase === 'saved' || (!intent.current && !consent)) return;
    const request = begin(); if (!request) return;
    let wrote = intent.current !== null;
    try {
      const fresh = await api.getBrief(brief.opportunity.id, interests, request.signal);
      if (!request.current()) return;
      if (!validBrief(fresh, brief.opportunity.id)) throw new Error('Invalid source');
      if (briefVersion(fresh) !== briefVersion(source)) {
        if (intent.current) { setPhase('partial'); setError('저장 도중 공고 정보가 바뀌었습니다. 추가 저장을 중단했습니다. 이미 반영된 항목은 내 준비 목록에서 확인하세요.'); }
        else { setSource(fresh); setPhase('edit'); setConsent(false); setError('확인 이후 공고 또는 현재 소속 정보가 바뀌었습니다. 다시 검토해야 하며 아직 저장하지 않았습니다.'); }
        return;
      }
      const list = await savedApi.listSaved(request.signal);
      if (!request.current()) return;
      let saved = ownRow(list.items, brief.opportunity.id);
      if (!intent.current) {
        let sort = saved?.checks.reduce((n, check) => Math.max(n, check.sort_order + 1), 0) ?? 0;
        const checks = rows.filter(row => row.selected).map(row => ({ text: row.text.trim(), sort: sort++, key: savedApi.newIdempotencyKey() }));
        if ((saved?.checks.length ?? 0) + checks.length > 50 || sort > 1000) throw new ApiError('CONFLICT', 409);
        intent.current = { memo: memo.trim(), saveAttempted: !!saved, checks };
      }
      const batch = intent.current;
      wrote = true; setPhase('partial');
      // PUT is insert-if-absent. A concurrent existing preparation is returned unchanged.
      if (!saved) {
        if (batch.saveAttempted) {
          setError('이전 저장 이후 준비 기록이 확인되지 않습니다. 삭제된 기록을 자동으로 다시 만들지 않습니다. 내 준비 목록을 확인하세요.'); return;
        }
        batch.saveAttempted = true;
        saved = await savedApi.saveOpportunity(brief.opportunity.id, batch.memo, request.signal);
        if (!request.current()) return;
        if (saved?.opportunity_id !== brief.opportunity.id) throw new Error('Invalid preparation');
      }
      for (const check of batch.checks) {
        if (check.id) continue;
        const result = await savedApi.addCheck(brief.opportunity.id, check.text, check.sort, check.key, request.signal);
        if (!request.current()) return;
        if (typeof result?.id !== 'string' || result.text !== check.text || result.sort_order !== check.sort) throw new Error('Invalid checklist');
        check.id = result.id;
      }
      const result = await savedApi.listSaved(request.signal);
      if (!request.current()) return;
      const current = ownRow(result.items, brief.opportunity.id);
      if (!current || !batch.checks.every(check => current.checks.some(row => row.id === check.id && row.text === check.text && row.sort_order === check.sort))) throw new Error('Readback not confirmed');
      setPhase('saved'); setConsent(false);
    } catch (failure) { if (request.current() && !discardDenied(failure)) { setPhase(wrote ? 'partial' : 'review'); setError(message(failure)); } }
    finally { request.finish(); }
  }

  if (phase === 'denied') return <p role="alert">{error}</p>;
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="rounded bg-slate-800 px-3 py-2 text-sm text-white">준비 초안 만들기</button>;
  return <section aria-label="준비 초안 편집" aria-busy={busy} className="space-y-3 rounded border border-sky-300 p-3 text-sm">
    <h3 className="font-semibold">준비 초안 — {source.opportunity.title}</h3>
    <p>규칙 기반 초안이며 AI 생성 결과가 아닙니다. 지원 자격·기관 제출을 확인하지 않습니다. 선택한 항목만 본인 준비 기록에 추가합니다.</p>
    <details><summary>현재 확인한 공고 근거</summary><p>주관: {source.opportunity.organization.trim() || '미확인'}</p><p className="whitespace-pre-wrap">{source.opportunity.eligibility}</p><p>마감: {source.opportunity.deadline_at ?? '미확인'}</p><ul>{source.procedure.map(step => <li key={step.order}>{STEP_LABEL[step.code]} · {step.evidence_value ?? '원문 확인 필요'}</li>)}</ul></details>
    {phase === 'edit' && <fieldset disabled={busy} className="space-y-2">
      <label className="block">준비 메모 초안<textarea value={memo} onChange={e => setMemo(e.target.value)} className="block w-full rounded border p-2" /></label>
      <p className="text-xs">이미 저장한 공고의 메모·상태·기존 체크는 바꾸지 않습니다.</p>
      {rows.length === 0 && <p>사용할 수 있는 절차 초안이 없습니다. 직접 준비 목록에서 항목을 작성하세요.</p>}
      {rows.map((row, index) => <div key={index} className="space-y-1">
        <label><input type="checkbox" checked={row.selected} onChange={e => setRows(all => all.map((r, i) => i === index ? { ...r, selected: e.target.checked } : r))} /> 초안 항목 {index + 1} 저장</label>
        <label className="block">준비 항목 초안 {index + 1}<textarea value={row.text} onChange={e => setRows(all => all.map((r, i) => i === index ? { ...r, text: e.target.value } : r))} className="block w-full rounded border p-2" /></label>
      </div>)}
      <button type="button" disabled={busy} onClick={() => void review()} className="rounded border px-3 py-2">준비 초안 검토</button>
      <button type="button" disabled={busy} onClick={() => { setOpen(false); setError(''); }} className="ml-2 rounded border px-3 py-2">초안 취소</button>
    </fieldset>}
    {phase === 'review' && <section aria-label="저장 전 확인" className="space-y-2">
      <p>{existing ? '기존 메모·상태·체크는 유지하고 아래 항목만 추가합니다.' : '새 준비 기록과 아래 선택한 항목을 저장합니다.'}</p>
      <p className="whitespace-pre-wrap">메모: {existing ? '기존 메모 유지' : memo || '(없음)'}</p>
      <ul>{rows.filter(row => row.selected).map((row, i) => <li key={i} className="whitespace-pre-wrap">{row.text.trim()}</li>)}</ul>
      <label className="block"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> 선택한 준비 항목을 내 기록에 추가하는 데 동의합니다</label>
      <button type="button" disabled={busy || !consent} onClick={() => void save()} className="rounded bg-slate-800 px-3 py-2 text-white">확인하고 내 준비에 저장</button>
      <button type="button" disabled={busy} onClick={() => { setPhase('edit'); setConsent(false); }} className="ml-2 rounded border px-3 py-2">초안 다시 편집</button>
      <button type="button" disabled={busy} onClick={() => { setPhase('edit'); setOpen(false); setConsent(false); }} className="ml-2 rounded border px-3 py-2">초안 취소</button>
    </section>}
    {phase === 'partial' && <>
      <p>일부 요청이 이미 반영되었을 수 있습니다. 항목별 요청 키를 유지하며 새 복사본을 자동 생성하지 않습니다.</p>
      <button type="button" disabled={busy} onClick={() => void save()} className="rounded border px-3 py-2">같은 요청으로 저장 다시 확인</button>
      <button type="button" disabled={busy} onClick={onSaved} className="ml-2 rounded border px-3 py-2">내 준비 목록으로 이동</button>
    </>}
    {phase === 'saved' && <><p role="status">선택한 준비 항목을 서버에서 다시 확인했습니다.</p><button type="button" onClick={onSaved} className="rounded border px-3 py-2">내 준비 목록으로 이동</button></>}
    {error && <p role="alert" className="text-red-800">{error}</p>}
  </section>;
}
