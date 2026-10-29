import { useCallback, useState } from 'react';
import { api, messageOf } from './api';
import { AttendancePanel } from './AttendancePanel';
import { CoursesPanel, RecordsPanel } from './CoursesPanel';
import { RequestsPanel } from './RequestsPanel';
import { Loaded, useLoader, when, type OnAuthFailure } from './shared';
import styles from './academics.module.css';

const TABS = [
  ['courses', '개설강좌·수강'],
  ['records', '성적·이수'],
  ['requests', '학적 요청'],
  ['attendance', '출결'],
] as const;
type Tab = (typeof TABS)[number][0];

function PolicyBanner({ onAuth }: { onAuth: OnAuthFailure }) {
  const policy = useLoader(signal => api.policy(signal), [], onAuth);
  return <Loaded state={policy.state} reload={policy.reload}>{p => <div className={styles.notice} aria-label="시연 정책">
    <p><strong>{p.label}</strong> · 학교 규정 연결: 없음(NOT_CONNECTED)</p>
    <p className={styles.muted}>시연 학점 한도 {p.max_credits_per_term} · 체크인 {p.check_in_window_minutes}분 · 수강신청 기간 {Object.values(p.registration_windows).map(w => `${when(w.opens_at)}–${when(w.closes_at)}`).join(', ') || '미설정'}</p>
    <p className={styles.muted}>차단된 기능: 운영 승인·공식 성적 변경·졸업 판정·증명서·등록금·블루투스 신원 확인</p>
  </div>}</Loaded>;
}

export default function AcademicsPage() {
  const [tab, setTab] = useState<Tab>('courses');
  const [authError, setAuthError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const onAuth = useCallback<OnAuthFailure>(error => setAuthError(messageOf(error)), []);

  return <section className={styles.page} aria-labelledby="academics-title">
    <header>
      <span className={styles.eyebrow}>ACADEMICS · DEMO</span>
      <h1 id="academics-title">학사·출결</h1>
      <p>가상 개설강좌 수강, 본인 가상 성적, 학적 요청 초안과 시연 출결을 확인해요. 실제 학교 학사 시스템과 연결되지 않습니다.</p>
    </header>
    {authError ? <div role="alert" className={styles.alert}>
      <p>{authError}</p>
      <p className={styles.muted}>개인 학사·출결 화면을 비웠습니다. 권한이 확인되면 다시 불러옵니다.</p>
      <button type="button" onClick={() => { setAuthError(null); setGeneration(g => g + 1); }}>다시 확인</button>
    </div> : <div key={generation} className={styles.page}>
      <PolicyBanner onAuth={onAuth} />
      <div role="tablist" aria-label="학사 기능" className={styles.tabs}>
        {TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>)}
      </div>
      <div role="tabpanel">
        {tab === 'courses' && <CoursesPanel onAuth={onAuth} />}
        {tab === 'records' && <RecordsPanel onAuth={onAuth} />}
        {tab === 'requests' && <RequestsPanel onAuth={onAuth} />}
        {tab === 'attendance' && <AttendancePanel onAuth={onAuth} />}
      </div>
    </div>}
  </section>;
}
