import { useEffect, useRef, useState, type FormEvent } from 'react';
import { requestData } from '../../lib/api';
import { categories, isGuide, isGuidePage, sites, type Category, type Guide, type GuidePage, type Site, type Source } from './models';
import styles from './styles.module.css';

function Evidence({ source }: { source: Source }) {
  return <aside className={styles.evidence}>
    <p><strong>{sites[source.site]}</strong> · 반환본 확인 {source.checked_at}</p>
    <p>페이지 존재 확인 · 처리 규칙 일부 확인 · 최신성 미검증</p>
    <p>{source.checked_scope}</p>
    <a href={source.url} target="_blank" rel="noopener noreferrer">공식 원문 확인 ↗</a>
  </aside>;
}

export default function PublicCampusPage() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<Category | ''>('');
  const [site, setSite] = useState<Site | ''>('');
  const [page, setPage] = useState<GuidePage | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const applied = useRef({ query: '', category: '' as Category | '', site: '' as Site | '' });
  const detailHeading = useRef<HTMLHeadingElement | null>(null);

  async function load(offset = 0) {
    request.current?.abort();
    const current = new AbortController(); request.current = current;
    setPending(true); setError(''); setGuide(null); setPage(null);
    if (offset === 0) applied.current = { query: query.trim(), category, site };
    const filter = applied.current;
    const params = new URLSearchParams({ q: filter.query, offset: String(offset), limit: '6' });
    if (filter.category) params.set('category', filter.category);
    if (filter.site) params.set('site', filter.site);
    try {
      const data = await requestData<unknown>(`/public-campus?${params}`, { signal: current.signal });
      if (!isGuidePage(data)) throw new Error('Invalid public guide response');
      if (!current.signal.aborted) setPage(data);
    } catch { if (!current.signal.aborted) setError('대학 안내를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.'); }
    finally { if (!current.signal.aborted) setPending(false); }
  }
  async function open(id: string) {
    request.current?.abort();
    const current = new AbortController(); request.current = current;
    setPending(true); setError('');
    try {
      const data = await requestData<unknown>(`/public-campus/${encodeURIComponent(id)}`, { signal: current.signal });
      if (!isGuide(data) || data.id !== id) throw new Error('Invalid public guide response');
      if (!current.signal.aborted) setGuide(data);
    } catch { if (!current.signal.aborted) setError('안내 내용을 불러오지 못했습니다. 목록에서 다시 선택해 주세요.'); }
    finally { if (!current.signal.aborted) setPending(false); }
  }
  useEffect(() => { void load(); return () => request.current?.abort(); }, []);
  useEffect(() => { if (guide) detailHeading.current?.focus(); }, [guide]);
  function search(event: FormEvent) { event.preventDefault(); void load(); }

  return <section className={styles.page} aria-labelledby="public-campus-title">
    <header><p className={styles.eyebrow}>DIT NOW · 대학 안내</p><h1 id="public-campus-title">대학·학과 정보</h1><p>대학과 학과의 공개 안내를 주제별로 살펴보세요.</p></header>
    <p className={styles.notice}>공식 공개 페이지를 참고한 DIT NOW의 편집 요약입니다. 학교가 운영하는 공식 서비스가 아니며, 실제 처리와 최신 내용은 원문을 확인하세요.</p>
    {!guide && <form onSubmit={search} className={styles.filters}>
      <label>안내 검색<input maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="예: 교육과정, 정보공개" /></label>
      <label>주제<select value={category} onChange={event => setCategory(event.target.value as Category | '')}><option value="">전체 주제</option>{Object.entries(categories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>자료 출처<select value={site} onChange={event => setSite(event.target.value as Site | '')}><option value="">전체 출처</option>{Object.entries(sites).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <button disabled={pending}>검색</button>
    </form>}
    <div aria-live="polite" aria-busy={pending}>
      {pending && <p role="status">공개 안내를 확인하고 있습니다.</p>}
      {error && <div role="alert"><p>{error}</p><button onClick={() => void load()}>목록 다시 확인</button></div>}
      {guide ? <article className={styles.detail}>
        <button onClick={() => setGuide(null)}>← 목록으로 돌아가기</button>
        <p className={styles.eyebrow}>{categories[guide.category]}</p>
        <h2 ref={detailHeading} tabIndex={-1}>{guide.title}</h2><p>{guide.summary}</p>
        {guide.sections.map((section, index) => <section key={index}><h3>{section.heading}</h3>{section.paragraphs.map((paragraph, paragraphIndex) => <p key={paragraphIndex}>{paragraph}</p>)}</section>)}
        <h3>출처와 확인 범위</h3><p>{guide.source.evidence}</p><Evidence source={guide.source} />
      </article> : page && <>
        <p className={styles.notice}>{page.notice}</p><p role="status">검색 결과 {page.total}건 · {page.snapshot_version}</p>
        {page.items.length === 0 && <p>일치하는 안내가 없습니다. 검색어나 분류를 바꿔 보세요.</p>}
        <div className={styles.cards}>{page.items.map(card => <article key={card.id} className={styles.card}>
          <p className={styles.eyebrow}>{categories[card.category]}</p><h2>{card.title}</h2><p>{card.summary}</p>
          <p className={styles.tags}>{card.tags.join(' · ')}</p><p className={styles.meta}>{sites[card.source.site]} · 확인 {card.source.checked_at}</p>
          <button onClick={() => void open(card.id)} disabled={pending} aria-label={`${card.title} 내용 읽기`}>내용 읽기 →</button>
        </article>)}</div>
        {page.total > page.limit && <nav aria-label="안내 페이지 이동" className={styles.pagination}>
          <button disabled={pending || page.offset === 0} onClick={() => void load(Math.max(0, page.offset - page.limit))}>이전</button>
          <button disabled={pending || page.offset + page.limit >= page.total} onClick={() => void load(page.offset + page.limit)}>다음</button>
        </nav>}
      </>}
    </div>
  </section>;
}
