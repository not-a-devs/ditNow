import { useEffect, useRef, useState, type FormEvent } from 'react';
import { requestData } from '../../lib/api';
import styles from './campus-search.module.css';

interface CampusHit {
  source_id: string;
  name: string;
  category: string;
  text: string;
  building: string | null;
  floor: string | null;
  room: string | null;
  hours: string | null;
  score: number;
  matched_by: 'alias' | 'fuzzy' | 'keyword';
}

interface CampusSearchData {
  mode: 'retrieval_only';
  found: boolean;
  hits: CampusHit[];
  verification: 'UNKNOWN';
  source_notice: string;
  generated: false;
  personal_data_access: false;
}

function isCampusSearchData(value: unknown): value is CampusSearchData {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (data.mode !== 'retrieval_only' || typeof data.found !== 'boolean'
    || data.verification !== 'UNKNOWN' || data.generated !== false
    || data.personal_data_access !== false || typeof data.source_notice !== 'string'
    || !data.source_notice.trim() || data.source_notice.length > 1000
    || !Array.isArray(data.hits) || data.hits.length > 10 || data.found !== (data.hits.length > 0)) return false;
  return data.hits.every((value: unknown) => {
    if (!value || typeof value !== 'object') return false;
    const hit = value as Record<string, unknown>;
    return ['source_id', 'name', 'category', 'text'].every((key) => typeof hit[key] === 'string' && hit[key].length <= 10000)
      && ['building', 'floor', 'room', 'hours'].every((key) => hit[key] === null || (typeof hit[key] === 'string' && hit[key].length <= 1000))
      && typeof hit.score === 'number' && Number.isFinite(hit.score) && hit.score >= 0 && hit.score <= 1
      && ['alias', 'fuzzy', 'keyword'].includes(String(hit.matched_by));
  });
}

interface AskLocation { id: string; name: string; building: string; distance_m: number | null; walk_minutes: number | null }
interface AskData { answer: string; found: boolean; locations: AskLocation[] }

const nullableInt = (v: unknown) => v === null || (Number.isInteger(v) && (v as number) >= 0);

function isAskData(value: unknown): value is AskData {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return typeof data.answer === 'string' && data.answer.length <= 4000 && typeof data.found === 'boolean'
    && Array.isArray(data.locations) && data.locations.length <= 10
    && data.locations.every((value: unknown) => {
      const loc = value as Record<string, unknown> | null;
      return !!loc && ['id', 'name', 'building'].every((key) => typeof loc[key] === 'string')
        && nullableInt(loc.distance_m) && nullableInt(loc.walk_minutes);
    });
}

/** 권한을 허락하면 현재 위치, 거부·미지원·시간 초과면 null (질문은 위치 없이 보낸다). */
function currentLocation(): Promise<{ lat: number; lng: number } | null> {
  if (!('geolocation' in navigator)) return Promise.resolve(null);
  return new Promise((resolve) => navigator.geolocation.getCurrentPosition(
    (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
    () => resolve(null),
    { timeout: 8000, maximumAge: 60_000 },
  ));
}

/** 신규 플랫폼 화면. 기존 MVP 및 챗봇의 별도 로그인 화면을 사용하지 않는다. */
export default function CampusAssistantPage() {
  const [query, setQuery] = useState(() => {
    const value = new URLSearchParams(window.location.search).get('q')?.trim() ?? '';
    return value.length <= 200 && /[\p{L}\p{N}]/u.test(value) && !/[\p{Cc}\p{Cf}]/u.test(value) ? value : '';
  });
  const [result, setResult] = useState<CampusSearchData | null>(null);
  const [answer, setAnswer] = useState<AskData | null>(null);
  const [useLocation, setUseLocation] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    if (query) void searchQuery(query);
    return () => controller.current?.abort();
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await searchQuery(query);
  }

  async function searchQuery(value: string) {
    const trimmed = value.trim();
    if (!trimmed || trimmed.length > 200) return;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setPending(true);
    setError('');
    setResult(null);
    setAnswer(null);
    try {
      const params = new URLSearchParams({ q: trimmed, limit: '5' });
      const data = await requestData<unknown>(`/ai/campus/search?${params}`, {
        signal: current.signal,
      });
      if (!isCampusSearchData(data)) throw new Error('Invalid campus search response');
      if (!current.signal.aborted) setResult(data);
    } catch {
      if (!current.signal.aborted) setError('시설 정보를 불러오지 못했습니다. 잠시 후 다시 검색해 주세요.');
    } finally {
      if (!current.signal.aborted) setPending(false);
    }
  }

  async function askAi() {
    const trimmed = query.trim();
    if (!trimmed || trimmed.length > 200) return;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setPending(true);
    setError('');
    setResult(null);
    setAnswer(null);
    try {
      const location = useLocation ? await currentLocation() : null;
      const data = await requestData<unknown>('/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, ...(location && { user_location: location }) }),
        signal: current.signal,
      });
      if (!isAskData(data)) throw new Error('Invalid ask response');
      if (!current.signal.aborted) setAnswer(data);
    } catch {
      if (!current.signal.aborted) setError('AI 답변을 받지 못했습니다. 잠시 후 다시 물어봐 주세요.');
    } finally {
      if (!current.signal.aborted) setPending(false);
    }
  }

  return (
    <section className={styles.page} aria-labelledby="campus-assistant-title">
      <header>
        <p className={styles.eyebrow}>DIT NOW · 캠퍼스 안내</p>
        <h1 id="campus-assistant-title">어디를 찾고 있나요?</h1>
        <p>건물, 학과 사무실, 편의시설을 검색해 보세요.</p>
      </header>

      <form onSubmit={search} className={styles.form}>
        <label htmlFor="campus-search-query">시설 이름 또는 질문</label>
        <div className={styles.controls}>
          <input
            id="campus-search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={200}
            placeholder="예: 도서관 어디 있어?"
            autoComplete="off"
          />
          <button type="submit" disabled={pending || !query.trim()}>
            {pending ? '처리 중…' : '검색'}
          </button>
          <button type="button" onClick={() => void askAi()} disabled={pending || !query.trim()}>
            AI에게 묻기
          </button>
        </div>
        <label className={styles.check}>
          <input type="checkbox" checked={useLocation} onChange={(event) => setUseLocation(event.target.checked)} />
          내 위치로 도보 시간 계산 (위치는 계산에만 쓰고 저장하지 않습니다)
        </label>
      </form>

      <p className={styles.notice}>
        현재 시설 자료를 검색할 수 있습니다. 개인 시간표·성적 안내는 공통 로그인과 학적 데이터 연결 후 제공됩니다.
      </p>
      <div aria-live="polite" aria-busy={pending}>
        {pending && <p role="status">답을 찾고 있습니다.</p>}
        {error && <p role="alert" className={styles.error}>{error}</p>}
        {answer && (
          <article className={styles.card} aria-label="AI 답변">
            <p className={styles.category}>AI 답변 · 교내 자료 근거, 틀릴 수 있어요</p>
            <p className={styles.answer}>{answer.answer}</p>
            {answer.locations.some((loc) => loc.walk_minutes !== null) && (
              <ul>
                {answer.locations.filter((loc) => loc.walk_minutes !== null).map((loc) => (
                  <li key={loc.id}>{loc.name} ({loc.building}): 걸어서 약 {loc.walk_minutes}분 · 약 {loc.distance_m}m (직선 거리 기반 추정)</li>
                ))}
              </ul>
            )}
          </article>
        )}
        {result && (
          <>
            <p className={styles.notice}>{result.source_notice}</p>
            {!result.found && <p>일치하는 시설이 없습니다. 시설 이름이나 별칭으로 검색해 주세요.</p>}
            <ul className={styles.results}>
              {result.hits.map((hit) => (
                <li key={hit.source_id} className={styles.card}>
                  <p className={styles.category}>{hit.category}</p>
                  <h2>{hit.name}</h2>
                  <p>{hit.text}</p>
                  {[hit.building, hit.floor, hit.room].some(Boolean) && (
                    <p>위치: {[hit.building, hit.floor, hit.room].filter(Boolean).join(' ')}</p>
                  )}
                  {hit.hours && <p>운영 시간: {hit.hours}</p>}
                  <small>시설 자료: {hit.source_id} · 최신성 확인 필요</small>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
