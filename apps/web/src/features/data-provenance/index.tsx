import { useEffect, useRef, useState } from 'react';
import { requestData } from '../../lib/api';
import { isOverview, type ProvenanceOverview } from './models';
import { SourceLabel } from './SourceLabel';
import styles from './styles.module.css';

export { SourceLabel } from './SourceLabel';

export default function DataProvenancePage() {
  const [overview, setOverview] = useState<ProvenanceOverview | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);

  async function load() {
    request.current?.abort();
    const current = new AbortController(); request.current = current;
    setPending(true); setError(''); setOverview(null);
    try {
      const data = await requestData<unknown>('/data-provenance', { signal: current.signal });
      if (!isOverview(data)) throw new Error('Invalid provenance response');
      if (!current.signal.aborted) setOverview(data);
    } catch { if (!current.signal.aborted) setError('출처 표시 안내를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'); }
    finally { if (!current.signal.aborted) setPending(false); }
  }
  useEffect(() => { void load(); return () => request.current?.abort(); }, []);

  return <section className={styles.page} aria-labelledby="data-provenance-title">
    <p className={styles.eyebrow}>읽기 전용 안내</p>
    <h1 id="data-provenance-title">자료 출처 표시 안내</h1>
    <p>화면의 출처 배지가 무엇을 뜻하는지 설명합니다. 출처를 등록하거나 바꾸는 관리 기능은 제공하지 않습니다.</p>
    <div role="status" aria-live="polite" className={styles.live}>
      {pending ? '출처 표시 안내를 불러오는 중입니다.' : error}
    </div>
    {error && <button type="button" onClick={() => void load()}>다시 시도</button>}
    {overview && <>
      <section aria-labelledby="provenance-status-title" className={styles.panel}>
        <h2 id="provenance-status-title">현재 상태</h2>
        <ul className={styles.statusList}>
          <li>학교 통합 로그인(SSO): 연결되지 않음</li>
          <li>금전적 효력: 없음</li>
          <li>저장 방식: 서버 실행 중 고정 안내만 제공(재시작 시 동일 내용)</li>
          <li>출처 관리 기능: 구현되지 않음</li>
        </ul>
        <p className={styles.notice}>{overview.notice}</p>
      </section>
      <section aria-labelledby="provenance-labels-title">
        <h2 id="provenance-labels-title">출처 배지 종류</h2>
        <ul className={styles.labels}>
          {overview.labels.map((item) => <li key={item.label} className={styles.panel}>
            <SourceLabel label={item.label} />
            <h3>{item.title}</h3>
            <p>{item.description}</p>
            <p className={styles.notice}>{item.user_guidance}</p>
          </li>)}
        </ul>
      </section>
    </>}
  </section>;
}
