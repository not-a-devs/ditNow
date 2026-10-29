import { useRef, useState, type FormEvent } from 'react';
import { api, intentFor, type Intent } from './api';
import { isUuid, KIND_LABEL, KINDS, targetField, type AcademicRequest, type RequestKind } from './models';
import { Alert, Loaded, useAction, useLoader, when, type OnAuthFailure } from './shared';
import styles from './academics.module.css';

const TARGET_LABEL = { target_term_id: '대상 학기 ID', target_department_id: '희망 학과 ID', target_grade_id: '정정 대상 시연 성적 ID' } as const;
const STATUS_LABEL = { DRAFT: '임시 저장', SUBMITTED: '시연 제출됨(심사 미연결)', WITHDRAWN: '철회됨(기록 보존)' } as const;

export function RequestsPanel({ onAuth }: { onAuth: OnAuthFailure }) {
  const requests = useLoader(signal => api.requests(signal), [], onAuth);
  const action = useAction(onAuth);
  const [kind, setKind] = useState<RequestKind>('LEAVE_OF_ABSENCE');
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState('');
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');
  const intent = useRef<Intent | null>(null);
  const field = targetField(kind);

  function merge(row: AcademicRequest) {
    if (requests.state.status !== 'ready') return requests.reload();
    requests.replace([row, ...requests.state.data.filter(r => r.id !== row.id)]);
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setFormError(''); setNotice('');
    if (!isUuid(target.trim())) { setFormError(`${TARGET_LABEL[field]}는 UUID 형식이어야 합니다.`); return; }
    const body = { kind, target_term_id: null, target_department_id: null, target_grade_id: null, [field]: target.trim(), reason: reason.trim() };
    intent.current = intentFor(intent.current, body);
    const key = intent.current.key;
    const ok = await action.run(() => api.createRequest(body, key), row => { merge(row); setNotice(`${KIND_LABEL[row.kind]} 시연 요청이 ${STATUS_LABEL[row.status]} 상태로 저장되었습니다.`); });
    if (ok) { intent.current = null; setTarget(''); setReason(''); }
  }
  async function change(row: AcademicRequest, step: 'submit' | 'withdraw') {
    setNotice('');
    await action.run(() => step === 'submit' ? api.submitRequest(row.id, row.revision) : api.withdrawRequest(row.id, row.revision),
      saved => { merge(saved); setNotice(`${KIND_LABEL[saved.kind]} 요청: ${STATUS_LABEL[saved.status]}`); });
  }

  return <section aria-labelledby="requests-title" className={styles.card}>
    <h2 id="requests-title">학적 변동·성적 정정 가상 요청</h2>
    <p className={styles.notice}>휴학·복학·재입학·전과·성적 정정은 시연 임시저장/제출/철회만 제공합니다. 학교 승인·학적 반영·성적 변경 권한은 연결되지 않으며 제출이 접수나 승인을 뜻하지 않습니다.</p>
    <form onSubmit={create} className={styles.card} aria-label="가상 요청 작성">
      <label>요청 종류<select value={kind} disabled={action.busy} onChange={e => { setKind(e.target.value as RequestKind); setTarget(''); }}>
        {KINDS.map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
      </select></label>
      <label>{TARGET_LABEL[field]}<input value={target} disabled={action.busy} onChange={e => setTarget(e.target.value)} required /></label>
      <label>사유<textarea value={reason} maxLength={2000} disabled={action.busy} onChange={e => setReason(e.target.value)} required /></label>
      <p className={styles.muted}>증빙 파일·민감 서류는 받지 않습니다.</p>
      <button type="submit" disabled={action.busy || !reason.trim() || !target.trim()}>{action.busy ? '저장 중…' : '임시 저장'}</button>
      <Alert message={formError} />
    </form>
    {notice && <p role="status">{notice}</p>}
    <Alert message={action.error} />
    <Loaded state={requests.state} reload={requests.reload} empty={d => d.length === 0}>{rows => <ul>
      {rows.map(row => <li key={row.id} className={styles.card}>
        <strong>{KIND_LABEL[row.kind]}</strong> <span className={styles.badge}>{STATUS_LABEL[row.status]}</span>
        {row.reason && <p>{row.reason}</p>}
        <p className={styles.muted}>작성 {when(row.created_at)}{row.submitted_at ? ` · 제출 ${when(row.submitted_at)}` : ''}{row.withdrawn_at ? ` · 철회 ${when(row.withdrawn_at)}` : ''}</p>
        <div className={styles.row}>
          {row.status === 'DRAFT' && <button type="button" disabled={action.busy} onClick={() => change(row, 'submit')}>시연 제출</button>}
          {row.status !== 'WITHDRAWN' && <button type="button" disabled={action.busy} onClick={() => change(row, 'withdraw')}>철회</button>}
        </div>
      </li>)}
    </ul>}</Loaded>
  </section>;
}
