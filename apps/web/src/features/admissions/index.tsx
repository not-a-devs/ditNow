import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { ALIASES, MOTIVATIONS, STATES, intentTracker, loadGuides, loadOverview, writeApplication, type Alias, type Application, type GuidePage, type Motivation, type Overview } from './api';

const date = (v: string) => new Intl.DateTimeFormat('ko-KR', {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(v));
const errorText = (e: unknown) => e instanceof ApiError && e.status === 503 ? '입학 안내·가상 지원 저장소와 인증 연결을 준비하고 있습니다.' : e instanceof ApiError && e.code === 'INVALID_RESPONSE' ? '응답의 출처나 자료 형식을 확인하지 못했습니다.' : e instanceof ApiError ? e.message : '요청을 확인하지 못했습니다. 다시 시도하세요.';

export default function AdmissionsPage() {
  const [guides, setGuides] = useState<GuidePage | null>(null);
  const [me, setMe] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [cycle, setCycle] = useState(''); const [track, setTrack] = useState('');
  const [alias, setAlias] = useState<Alias>(ALIASES[0]);
  const [motivation, setMotivation] = useState<Motivation>('career_exploration');
  const [editing, setEditing] = useState<Application | null>(null);
  const keys = useRef(intentTracker());
  const reads = useRef<AbortController | null>(null);
  const alive = useRef(true);

  async function reload() {
    reads.current?.abort(); const controller = new AbortController(); reads.current = controller;
    setLoading(true); setErrors({});
    await Promise.all([
      loadGuides(controller.signal).then(data => { if (!controller.signal.aborted) setGuides(data); }).catch(e => { if (!controller.signal.aborted) { setGuides(null); setErrors(old => ({...old, guides: errorText(e)})); } }),
      loadOverview(controller.signal).then(data => { if (!controller.signal.aborted) { setMe(data); setCycle(old => old || data.policies[0]?.cycle_id || ''); setTrack(old => old || data.policies[0]?.tracks[0]?.id || ''); } }).catch(e => { if (!controller.signal.aborted) { setMe(null); setErrors(old => ({...old, me: errorText(e)})); } }),
    ]);
    if (!controller.signal.aborted) setLoading(false);
  }
  useEffect(() => { alive.current = true; void reload(); return () => { alive.current = false; reads.current?.abort(); }; }, []);
  const policy = me?.policies.find(p => p.cycle_id === cycle);
  function edit(row: Application) { setEditing(row); setCycle(row.cycle_id); setTrack(row.track_id); setAlias(row.demo_alias); setMotivation(row.motivation); }
  async function mutate(path: string, body: object, method = 'POST') {
    setBusy(true); setNotice(''); setErrors(old => ({...old, action: ''}));
    try {
      const row = await writeApplication(path, body, keys.current.key(path, body), method);
      if (!alive.current) return;
      keys.current.done(path);
      setMe(old => old ? {...old, applications: [...old.applications.filter(a => a.id !== row.id), row]} : old);
      if (editing?.id === row.id) setEditing(row);
      setNotice('가상 지원 기록이 반영되었습니다. 실제 입학 지원·접수·환불이 아닙니다.');
    } catch (e) {
      if (!alive.current) return;
      setErrors(old => ({...old, action: errorText(e)}));
      if (e instanceof ApiError && [401, 403].includes(e.status)) { setMe(null); setEditing(null); }
    } finally { if (alive.current) setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!policy || busy) return;
    const fields = {demo_alias: alias, track_id: track, motivation, expected_policy_revision: policy.revision};
    if (editing) await mutate(`/admissions/me/applications/${editing.id}`, {...fields, expected_revision: editing.revision}, 'PATCH');
    else await mutate('/admissions/me/applications', {...fields, cycle_id: cycle});
  }
  function transition(row: Application, action: 'submit' | 'withdraw') {
    const p = me?.policies.find(item => item.cycle_id === row.cycle_id);
    if (p) void mutate(`/admissions/me/applications/${row.id}/${action}`, {expected_revision: row.revision, expected_policy_revision: p.revision});
  }

  return <section aria-labelledby="admissions-title" className="mx-auto flex max-w-5xl flex-col gap-5 p-4">
    <header><h1 id="admissions-title" className="text-2xl font-semibold">입학 안내 · 가상 지원</h1><p>공개 자료의 출처와 나의 가상 준비 상태를 구분해 확인하세요.</p></header>
    <p className="rounded bg-amber-50 p-3">시연 전용입니다. 실명·주민번호·주소·전화·성적·서류를 입력하거나 업로드하지 마세요. 합격 판정·납부·환불·민감 상담·공식 내신 산출은 제공하지 않습니다.</p>
    <button type="button" onClick={() => void reload()} disabled={loading || busy} className="self-start rounded border px-3 py-2">다시 확인</button>
    {loading && <p role="status">입학 안내와 가상 지원 내역을 확인하고 있어요…</p>}
    {Object.entries(errors).filter(([,text]) => text).map(([key,text]) => <p role="alert" key={key}>{text}</p>)}
    {notice && <p role="status">{notice}</p>}
    <section className="rounded border p-4"><h2 className="text-lg font-medium">공개 모집 안내 · 일정 · FAQ</h2>
      {guides?.items.length === 0 && <p>검증해 등록한 안내 자료가 없습니다. 공식 일정이나 모집 조건을 추측하지 않습니다.</p>}
      {guides?.items.map(g => <article key={g.id} className="my-3 border-t pt-3"><h3>{g.title}</h3><p>{g.summary}</p><p>버전 {g.revision} · {g.source_kind === 'OFFICIAL_PUBLIC' ? '공개 원문 근거' : g.source_kind === 'DEMO' ? '가상 자료' : '출처 미확인'}</p>
        {g.source_url && <a href={g.source_url} target="_blank" rel="noopener noreferrer" className="underline">근거 원문</a>}{g.checked_at && <p>확인일 {date(g.checked_at)}</p>}
        <ul>{g.schedules.map((s,i) => <li key={i}>{s.label}: {date(s.starts_at)} ~ {date(s.ends_at)}</li>)}</ul>
        {g.faqs.map((f,i) => <details key={i}><summary>{f.question}</summary><p>{f.answer}</p></details>)}</article>)}
      {guides?.has_more && <p>현재는 첫 20개 안내를 표시합니다. 전체 공개 자료 탐색은 후속 태스크입니다.</p>}
    </section>
    <section className="rounded border p-4"><h2 className="text-lg font-medium">본인 가상 지원서</h2>
      {me?.policies.length === 0 && <p>승인해 주입한 가상 전형·정책이 없습니다. 지원서를 생성하지 않습니다.</p>}
      {me && policy && <form onSubmit={save} className="my-3 flex max-w-lg flex-col gap-2">
        <p>가상 정책: {policy.name} · 버전 {policy.revision} · {date(policy.opens_at)} ~ {date(policy.closes_at)}. 학교 규정이 아닙니다.</p>
        <label htmlFor="admissions-cycle">가상 모집</label><select id="admissions-cycle" value={cycle} disabled={busy || editing !== null} onChange={e => {setCycle(e.target.value); setTrack(me.policies.find(p => p.cycle_id === e.target.value)?.tracks[0]?.id || '');}}>{me.policies.map(p => <option key={p.cycle_id} value={p.cycle_id}>{p.name}</option>)}</select>
        <label htmlFor="admissions-alias">가상 별칭</label><select id="admissions-alias" value={alias} disabled={busy} onChange={e => setAlias(e.target.value as Alias)}>{ALIASES.map(a => <option key={a}>{a}</option>)}</select>
        <label htmlFor="admissions-track">가상 전형</label><select id="admissions-track" value={track} disabled={busy} onChange={e => setTrack(e.target.value)}>{policy.tracks.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
        <label htmlFor="admissions-motivation">가상 지원 동기</label><select id="admissions-motivation" value={motivation} disabled={busy} onChange={e => setMotivation(e.target.value as Motivation)}>{Object.entries(MOTIVATIONS).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
        <button disabled={busy || !track || (editing !== null && editing.state !== 'draft')} className="rounded bg-blue-700 px-3 py-2 text-white">{editing ? '가상 초안 수정' : '가상 초안 저장'}</button>
        {editing && <button type="button" disabled={busy} onClick={() => setEditing(null)}>새 가상 지원서 작성</button>}
      </form>}
      {me?.applications.length === 0 && <p>본인 가상 지원서가 없습니다.</p>}
      <ul>{me?.applications.map(row => <li key={row.id} className="my-3 rounded bg-slate-50 p-3"><h3>{row.demo_alias} · {STATES[row.state]}</h3><p>개정 {row.revision} · {MOTIVATIONS[row.motivation]}</p><p>서류 도착·면접·합격·납부·환불: 미구현. 가상 접수 상태도 실제 학교 접수를 뜻하지 않습니다.</p>
        {row.state === 'draft' && <div className="flex gap-2"><button disabled={busy} onClick={() => edit(row)}>초안 수정</button><button disabled={busy || !me.policies.some(p => p.cycle_id === row.cycle_id)} onClick={() => transition(row,'submit')}>가상 제출</button></div>}
        {['submitted','received'].includes(row.state) && <button disabled={busy || !me.policies.some(p => p.cycle_id === row.cycle_id)} onClick={() => transition(row,'withdraw')}>가상 취소 요청</button>}
      </li>)}</ul>
    </section>
  </section>;
}
