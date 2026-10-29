import { useRef, useState, type FormEvent } from 'react';
import { api, intentFor, type Intent } from './api';
import { MARK_LABEL, type AttendanceOffering, type AttendanceRecord, type Correction, type FinalMark, type Session } from './models';
import { Alert, Loaded, useAction, useLoader, when, type OnAuthFailure } from './shared';
import styles from './academics.module.css';

const FINAL: FinalMark[] = ['PRESENT', 'LATE', 'ABSENT'];
const DISCLAIMER = '시연 출결 원장입니다. 화면 코드는 현장 재실을 인증하지 않으며 블루투스·캠퍼스락 신원 확인은 차단되어 있습니다. 출석·지각·결석 표시는 공식 판정이 아닙니다.';

export function AttendancePanel({ onAuth }: { onAuth: OnAuthFailure }) {
  const offerings = useLoader(signal => api.attendanceOfferings(signal), [], onAuth);
  const [selected, setSelected] = useState<AttendanceOffering | null>(null);
  return <section aria-labelledby="attendance-title" className={styles.card}>
    <h2 id="attendance-title">시연 출결</h2>
    <p className={styles.notice}>{DISCLAIMER}</p>
    {selected ? <>
      <button type="button" onClick={() => setSelected(null)}>← 분반 목록</button>
      <h3>{selected.title} · {selected.role === 'teacher' ? '담당 교수' : '수강생'}</h3>
      {selected.role === 'teacher' ? <TeacherView offeringId={selected.offering_id} onAuth={onAuth} /> : <StudentView offeringId={selected.offering_id} onAuth={onAuth} />}
    </> : <Loaded state={offerings.state} reload={offerings.reload} empty={d => d.length === 0}>{rows => <div className={styles.grid}>
      {rows.map(o => <button type="button" key={o.offering_id} className={styles.card} onClick={() => setSelected(o)}>{o.title} · {o.role === 'teacher' ? '담당 교수' : '수강생'}</button>)}
    </div>}</Loaded>}
  </section>;
}

function TeacherView({ offeringId, onAuth }: { offeringId: string; onAuth: OnAuthFailure }) {
  const sessions = useLoader(signal => api.sessions(offeringId, signal), [offeringId], onAuth);
  const corrections = useLoader(signal => api.corrections(offeringId, signal), [offeringId], onAuth);
  const action = useAction(onAuth);
  const [label, setLabel] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const intent = useRef<Intent | null>(null);

  function merge(row: Session) {
    if (sessions.state.status !== 'ready') return sessions.reload();
    sessions.replace([...sessions.state.data.filter(s => s.id !== row.id), row]);
  }
  async function start(event: FormEvent) {
    event.preventDefault();
    intent.current = intentFor(intent.current, { label: label.trim() });
    const key = intent.current.key;
    if (await action.run(() => api.openSession(offeringId, label.trim(), key), merge)) { intent.current = null; setLabel(''); }
  }
  return <div className={styles.card}>
    <form onSubmit={start} className={styles.row}>
      <label>세션 이름<input value={label} maxLength={80} required disabled={action.busy} onChange={e => setLabel(e.target.value)} /></label>
      <button type="submit" disabled={action.busy || !label.trim()}>시연 출석 세션 시작</button>
    </form>
    <Alert message={action.error} />
    <Loaded state={sessions.state} reload={sessions.reload} empty={d => d.length === 0}>{rows => <ul>
      {rows.map(s => <li key={s.id} className={styles.card}>
        <strong>{s.label}</strong> <span className={styles.badge}>{s.status === 'OPEN' ? '진행 중' : '종료'}</span>
        {s.status === 'OPEN' && s.check_in_code && <p>시연 코드 <span className={styles.code} aria-label="시연 체크인 코드">{s.check_in_code}</span> · 체크인 마감 {when(s.check_in_closes_at)}</p>}
        <div className={styles.row}>
          {s.status === 'OPEN' && <button type="button" disabled={action.busy} onClick={() => action.run(() => api.closeSession(offeringId, s.id, s.revision), merge)}>세션 종료</button>}
          <button type="button" onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? '기록 닫기' : '기록 보기'}</button>
        </div>
        {open === s.id && <SessionRecords offeringId={offeringId} sessionId={s.id} onAuth={onAuth} />}
      </li>)}
    </ul>}</Loaded>
    <h4>학생 정정 요청</h4>
    <Loaded state={corrections.state} reload={corrections.reload} empty={d => d.length === 0}>{rows => <ul>
      {rows.map(c => <CorrectionItem key={c.id} offeringId={offeringId} correction={c} onAuth={onAuth}
        onSaved={saved => corrections.state.status === 'ready' && corrections.replace(corrections.state.data.map(x => x.id === saved.id ? saved : x))} />)}
    </ul>}</Loaded>
  </div>;
}

function SessionRecords({ offeringId, sessionId, onAuth }: { offeringId: string; sessionId: string; onAuth: OnAuthFailure }) {
  const records = useLoader(signal => api.records(offeringId, sessionId, signal), [offeringId, sessionId], onAuth);
  return <Loaded state={records.state} reload={records.reload} empty={d => d.length === 0}>{rows => <ul>
    {rows.map(r => <MarkRow key={r.member_ref ?? r.id} offeringId={offeringId} record={r} onAuth={onAuth}
      onSaved={saved => records.state.status === 'ready' && records.replace(records.state.data.map(x => x.member_ref === saved.member_ref ? saved : x))} />)}
  </ul>}</Loaded>;
}

function MarkRow({ offeringId, record, onAuth, onSaved }: { offeringId: string; record: AttendanceRecord; onAuth: OnAuthFailure; onSaved: (r: AttendanceRecord) => void }) {
  const action = useAction(onAuth);
  const [mark, setMark] = useState<FinalMark>('PRESENT');
  const [reason, setReason] = useState('');
  const name = record.student_label ?? '수강생';
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!record.member_ref) return;
    const ref = record.member_ref;
    if (await action.run(() => api.mark(offeringId, record.session_id, ref, mark, reason.trim(), record.revision), onSaved)) setReason('');
  }
  return <li className={styles.row}>
    <span>{name} · {MARK_LABEL[record.mark]}</span>
    <form onSubmit={save} className={styles.row} aria-label={`${name} 출결 수정`}>
      <select aria-label={`${name} 표시`} value={mark} onChange={e => setMark(e.target.value as FinalMark)}>{FINAL.map(m => <option key={m} value={m}>{MARK_LABEL[m]}</option>)}</select>
      <input aria-label={`${name} 변경 사유`} value={reason} maxLength={500} required onChange={e => setReason(e.target.value)} />
      <button type="submit" disabled={action.busy || !reason.trim()}>저장</button>
    </form>
    <Alert message={action.error} />
  </li>;
}

function CorrectionItem({ offeringId, correction, onAuth, onSaved }: { offeringId: string; correction: Correction; onAuth: OnAuthFailure; onSaved: (c: Correction) => void }) {
  const action = useAction(onAuth);
  const [reason, setReason] = useState('');
  const resolve = (decision: 'ACCEPTED' | 'REJECTED') => action.run(() => api.resolveCorrection(offeringId, correction.id, decision, reason.trim(), correction.revision), onSaved);
  return <li className={styles.card}>
    <span>{correction.student_label ?? '수강생'} · 요청 {MARK_LABEL[correction.requested_mark]} · {correction.status === 'REQUESTED' ? '대기' : correction.status === 'ACCEPTED' ? '반영' : '반려'}</span>
    <p>{correction.reason}</p>
    {correction.status === 'REQUESTED' && <div className={styles.row}>
      <input aria-label="처리 사유" value={reason} maxLength={500} onChange={e => setReason(e.target.value)} />
      <button type="button" disabled={action.busy || !reason.trim()} onClick={() => resolve('ACCEPTED')}>반영</button>
      <button type="button" disabled={action.busy || !reason.trim()} onClick={() => resolve('REJECTED')}>반려</button>
    </div>}
    <Alert message={action.error} />
  </li>;
}

function StudentView({ offeringId, onAuth }: { offeringId: string; onAuth: OnAuthFailure }) {
  const mine = useLoader(signal => api.myAttendance(offeringId, signal), [offeringId], onAuth);
  return <Loaded state={mine.state} reload={mine.reload}>{data => <>
    {data.sessions.length === 0 && <p className={styles.muted}>열린 시연 출석 세션이 없습니다.</p>}
    <ul>{data.sessions.map(s => {
      const record = data.records.find(r => r.session_id === s.id);
      const pending = data.corrections.find(c => c.session_id === s.id && c.status === 'REQUESTED');
      return <li key={s.id} className={styles.card}>
        <strong>{s.label}</strong> <span className={styles.badge}>{record ? MARK_LABEL[record.mark] : '미기록'}</span>
        {s.status === 'OPEN' && (!record || record.mark === 'UNMARKED') && <CheckIn offeringId={offeringId} session={s} onAuth={onAuth} onDone={mine.reload} />}
        {record?.id && ['PRESENT', 'LATE', 'ABSENT'].includes(record.mark) && (pending
          ? <p className={styles.muted}>정정 요청 대기 중: {MARK_LABEL[pending.requested_mark]}</p>
          : <CorrectionForm offeringId={offeringId} recordId={record.id} onAuth={onAuth} onDone={mine.reload} />)}
      </li>;
    })}</ul>
  </>}</Loaded>;
}

function CheckIn({ offeringId, session, onAuth, onDone }: { offeringId: string; session: Session; onAuth: OnAuthFailure; onDone: () => void }) {
  const action = useAction(onAuth);
  const [code, setCode] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await action.run(() => api.checkIn(offeringId, session.id, code), () => undefined)) { setCode(''); onDone(); }
  }
  return <form onSubmit={submit} className={styles.row}>
    <label>시연 체크인 코드<input value={code} inputMode="numeric" pattern="\d{6}" maxLength={6} required onChange={e => setCode(e.target.value)} /></label>
    <button type="submit" disabled={action.busy || !/^\d{6}$/.test(code)}>체크인</button>
    <Alert message={action.error} />
  </form>;
}

function CorrectionForm({ offeringId, recordId, onAuth, onDone }: { offeringId: string; recordId: string; onAuth: OnAuthFailure; onDone: () => void }) {
  const action = useAction(onAuth);
  const [mark, setMark] = useState<FinalMark>('PRESENT');
  const [reason, setReason] = useState('');
  const intent = useRef<Intent | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    intent.current = intentFor(intent.current, { requested_mark: mark, reason: reason.trim() });
    const key = intent.current.key;
    if (await action.run(() => api.requestCorrection(offeringId, recordId, mark, reason.trim(), key), () => undefined)) { intent.current = null; onDone(); }
  }
  return <form onSubmit={submit} className={styles.row} aria-label="출결 정정 요청">
    <select aria-label="요청 표시" value={mark} onChange={e => setMark(e.target.value as FinalMark)}>{FINAL.map(m => <option key={m} value={m}>{MARK_LABEL[m]}</option>)}</select>
    <input aria-label="정정 사유" value={reason} maxLength={1000} required onChange={e => setReason(e.target.value)} />
    <button type="submit" disabled={action.busy || !reason.trim()}>정정 요청</button>
    <Alert message={action.error} />
  </form>;
}
