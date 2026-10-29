import { useRef, useState, type FormEvent } from 'react';
import { api, intentFor, type Intent } from './api';
import { officialLink, type Enrollment, type Offering } from './models';
import { Alert, Loaded, useAction, useLoader, when, type OnAuthFailure } from './shared';
import styles from './academics.module.css';

const DAYS = ['', '월', '화', '수', '목', '금', '토', '일'];
const time = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

export function CoursesPanel({ onAuth }: { onAuth: OnAuthFailure }) {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const offerings = useLoader(signal => api.offerings(query, undefined, signal), [query], onAuth);
  const enrollments = useLoader(signal => api.enrollments(signal), [], onAuth);
  const action = useAction(onAuth);
  const intents = useRef(new Map<string, Intent>());
  const [notice, setNotice] = useState('');

  function merge(row: Enrollment) {
    if (enrollments.state.status !== 'ready') return enrollments.reload();
    enrollments.replace([...enrollments.state.data.filter(e => e.id !== row.id), row]);
  }
  async function enroll(offering: Offering) {
    setNotice('');
    const intent = intentFor(intents.current.get(offering.id) ?? null, { offering_id: offering.id });
    intents.current.set(offering.id, intent);
    const ok = await action.run(() => api.enroll(offering.id, intent.key), row => {
      merge(row);
      setNotice(row.status === 'ENROLLED' ? `${offering.title} 시연 수강 신청이 저장되었습니다.` : `${offering.title} 신청은 이미 취소된 기록입니다.`);
    });
    if (ok) { intents.current.delete(offering.id); offerings.reload(); }
  }
  async function drop(row: Enrollment) {
    setNotice('');
    const ok = await action.run(() => api.drop(row.id, row.revision), saved => { merge(saved); setNotice('시연 수강 취소가 저장되었습니다. 기록은 보존됩니다.'); });
    if (ok) offerings.reload();
  }
  function search(event: FormEvent) { event.preventDefault(); setQuery(draft.trim()); }

  const titleOf = (id: string) => offerings.state.status === 'ready' ? offerings.state.data.find(o => o.id === id)?.title ?? '가상 개설강좌' : '가상 개설강좌';
  return <section aria-labelledby="courses-title" className={styles.card}>
    <h2 id="courses-title">가상 개설강좌 · 수강신청/정정</h2>
    <p className={styles.muted}>정원·시간 충돌·학점 한도·기간은 주입된 시연 정책으로 서버가 판단합니다. 실제 학교 수강신청과 연결되지 않습니다.</p>
    <form onSubmit={search} className={styles.row} role="search">
      <label>강좌 검색<input value={draft} maxLength={80} onChange={e => setDraft(e.target.value)} /></label>
      <button type="submit">검색</button>
    </form>
    {notice && <p role="status">{notice}</p>}
    <Alert message={action.error} />
    <Loaded state={offerings.state} reload={offerings.reload} empty={d => d.length === 0}>{list => <div className={styles.grid}>
      {list.map(o => {
        const link = officialLink(o.syllabus_source);
        const enrolled = enrollments.state.status === 'ready' && enrollments.state.data.some(e => e.offering_id === o.id && e.status === 'ENROLLED');
        return <article key={o.id} className={styles.card}>
          <span className={styles.badge}>시연 강좌 · {o.course_code}-{o.section}</span>
          <h3>{o.title}</h3>
          <p>{o.instructor_name} · {o.credits}학점 · 정원 {o.enrolled_count}/{o.capacity}</p>
          <p className={styles.muted}>{o.meetings.map(m => `${DAYS[m.weekday]} ${time(m.starts_minute)}–${time(m.ends_minute)}`).join(', ') || '시간 미정'}</p>
          <p>{o.syllabus_summary}</p>
          {link ? <p className={styles.muted}><a href={link.url} target="_blank" rel="noopener noreferrer">공개 강의계획 원문 ↗</a> (확인 {when(link.checkedAt)})</p>
            : <p className={styles.muted}>{o.syllabus_source.source_kind === 'DEMO' ? '가상 강의계획(DEMO)' : '출처 미확인(UNKNOWN)'}</p>}
          <button type="button" disabled={action.busy || enrolled} onClick={() => enroll(o)}>{enrolled ? '신청됨' : '시연 수강 신청'}</button>
        </article>;
      })}
    </div>}</Loaded>
    <h3>내 시연 수강 내역</h3>
    <Loaded state={enrollments.state} reload={enrollments.reload} empty={d => d.length === 0}>{rows => <ul>
      {rows.map(row => <li key={row.id} className={styles.row}>
        <span>{titleOf(row.offering_id)} · {row.status === 'ENROLLED' ? '신청됨' : `취소됨(기록 보존, ${when(row.dropped_at)})`}</span>
        {row.status === 'ENROLLED' && <button type="button" disabled={action.busy} onClick={() => drop(row)}>수강 취소</button>}
      </li>)}
    </ul>}</Loaded>
  </section>;
}

export function RecordsPanel({ onAuth }: { onAuth: OnAuthFailure }) {
  const transcript = useLoader(signal => api.transcript(signal), [], onAuth);
  return <section aria-labelledby="records-title" className={styles.card}>
    <h2 id="records-title">본인 가상 성적·이수 조회</h2>
    <p className={styles.notice}>시연용 가상 기록입니다. 공식 성적·졸업 판정·증명 효력이 없으며 합계는 표시 목록의 단순 합입니다.</p>
    <Loaded state={transcript.state} reload={transcript.reload}>{data => <>
      {data.grades.length === 0 ? <p className={styles.muted}>표시할 시연 기록이 없습니다.</p>
        : <table className={styles.table}><thead><tr><th>과목</th><th>학점</th><th>시연 등급</th><th>기록 시각</th></tr></thead>
          <tbody>{data.grades.map(g => <tr key={g.id}><td>{g.course_title}</td><td>{g.credits}</td><td>{g.grade_label}</td><td>{when(g.recorded_at)}</td></tr>)}</tbody></table>}
      <p>표시 학점 합계: {data.listed_credit_total} · 졸업 판정: 제공하지 않음</p>
    </>}</Loaded>
  </section>;
}
