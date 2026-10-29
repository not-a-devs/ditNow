import { useEffect, useRef, useState, type FormEvent } from 'react';
import { requestData } from '../../lib/api';
import { isPage, type Kind, type Page } from './models';
import styles from './styles.module.css';

const labels: Record<Kind, string> = { all: '전체 공개 자료', guide: '대학·학과 안내', facility: '시설 스냅샷' };
interface Search { query: string; kind: Kind; offset: number }

export default function PublicDiscoveryPage() {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<Kind>('all');
  const [page, setPage] = useState<Page | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const attempt = useRef<Search | null>(null);
  const active = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement | null>(null);
  const valid = !!query.trim() && query.trim().length <= 200 && /[\p{L}\p{N}]/u.test(query);

  async function load(search: Search) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller; attempt.current = search;
    setPending(true); setPage(null); setError('');
    const params = new URLSearchParams({ q: search.query, kind: search.kind, offset: String(search.offset), limit: '8' });
    try {
      const data = await requestData<unknown>(`/discovery?${params}`, { signal: controller.signal });
      if (!isPage(data) || data.kind !== search.kind || data.offset !== search.offset || data.limit !== 8) throw new Error('Invalid public search response');
      if (!controller.signal.aborted) setPage(data);
    } catch {
      if (!controller.signal.aborted) setError('공개 검색을 불러오지 못했습니다. 같은 검색으로 다시 시도해 주세요.');
    } finally { if (!controller.signal.aborted) setPending(false); }
  }
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => { if (page) resultHeading.current?.focus(); }, [page]);
  function submit(event: FormEvent) { event.preventDefault(); if (valid) void load({ query: query.trim(), kind, offset: 0 }); }

  return <section className={styles.page} aria-labelledby="discovery-title">
    <header><p className={styles.eyebrow}>DIT NOW · 공개 자료 찾기</p><h1 id="discovery-title">통합 검색</h1><p>대학·학과 안내와 시설 자료를 한곳에서 찾아보세요.</p></header>
    <p className={styles.notice}>개인 시간표·성적·신청·대화 검색은 아직 제공하지 않습니다. 공개 자료만 조회하며, AI가 답변을 생성하지 않습니다.</p>
    <form onSubmit={submit} className={styles.form}>
      <label>검색어<input value={query} onChange={event => setQuery(event.target.value)} maxLength={200} placeholder="예: 도서관, 학과, 정보공개" /></label>
      <label>검색 범위<select value={kind} onChange={event => setKind(event.target.value as Kind)}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <button disabled={!valid || pending}>검색</button>
    </form>
    <div aria-live="polite" aria-busy={pending}>
      {pending && <p role="status">공개 자료를 찾고 있습니다.</p>}
      {error && <div role="alert"><p>{error}</p><button onClick={() => attempt.current && void load(attempt.current)}>같은 검색 재시도</button></div>}
      {!attempt.current && <p>검색어를 입력하면 공개 자료에서 찾습니다.</p>}
      {page && <>
        <h2 ref={resultHeading} tabIndex={-1}>“{page.query}” 검색 결과 {page.total}건{!page.complete && ' 이상 · 일부 범위'}</h2>
        <p>대학·학과 안내 {page.counts.guide}건 · 시설 스냅샷 {page.counts.facility}건</p>
        <p className={styles.notice}>{page.notice}</p>
        {!page.complete && <p>처리량 제한으로 일부 결과만 집계했습니다. 검색어를 구체적으로 바꿔 보세요.</p>}
        {page.total === 0 && <p>일치하는 공개 자료가 없습니다. 다른 검색어를 사용해 보세요.</p>}
        <div className={styles.results}>{page.items.map(item => <article key={item.id}>
          <p className={styles.eyebrow}>{labels[item.kind]}</p><h3>{item.title}</h3><p>{item.summary}</p>
          {item.source.kind === 'official_summary' ? <div className={styles.source}>
            <p>공식 공개 페이지 기반 편집 요약 · 페이지 존재 확인</p>
            <p>규칙 일부 확인 · 최신성 미검증 · 확인 {item.source.evidence.checked_at}</p>
            <a href={item.source.evidence.url} target="_blank" rel="noopener noreferrer">공식 근거 원문 ↗</a>
          </div> : <div className={styles.source}><p>시설 자료 · 출처 신뢰도 UNKNOWN</p><p>{item.source.notice}</p></div>}
          <a className={styles.detail} href={item.detail_path}>{item.kind === 'guide' ? '안내 상세로 이동' : '시설 검색에서 확인'} →</a>
        </article>)}</div>
        {page.total > page.limit && <nav className={styles.pagination} aria-label="검색 결과 페이지">
          <button disabled={pending || page.offset === 0} onClick={() => attempt.current && void load({ ...attempt.current, offset: Math.max(0, page.offset - page.limit) })}>이전</button>
          <button disabled={pending || page.offset + page.limit >= page.total} onClick={() => attempt.current && void load({ ...attempt.current, offset: page.offset + page.limit })}>다음</button>
        </nav>}
      </>}
    </div>
  </section>;
}
