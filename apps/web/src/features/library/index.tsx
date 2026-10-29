import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, requestData } from '../../lib/api';
import { isBooking, isCatalog, isLoan, isOverview, isSlots, isWish, type Booking, type Catalog, type Loan, type Overview, type Slot, type Wish } from './models';
import styles from './styles.module.css';

const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
function safeError(error: unknown) { return error instanceof ApiError && error.status === 503 ? '승인된 도서관 저장소·가상 정책·인증 연결을 준비하고 있습니다.' : error instanceof ApiError ? error.message : '응답 형식을 확인하지 못했습니다. 다시 확인해 주세요.'; }

export default function LibraryPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [me, setMe] = useState<Overview | null>(null);
  const [query, setQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [title, setTitle] = useState(''); const [author, setAuthor] = useState(''); const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState('');
  const reads = useRef(new Map<string, AbortController>());
  const writes = useRef(new Set<AbortController>());
  const attempts = useRef(new Map<string, { payload: string; key: string }>());

  async function load(part: 'catalog' | 'slots' | 'me', search = activeQuery, offset = 0) {
    reads.current.get(part)?.abort(); const controller = new AbortController(); reads.current.set(part, controller);
    setPending(p => ({ ...p, [part]: true })); setErrors(e => ({ ...e, [part]: '' }));
    try {
      const path = part === 'catalog' ? `/library/catalog?${new URLSearchParams({ q: search.trim(), offset: String(offset), limit: '20' })}` : `/library/${part}`;
      const data = await requestData<unknown>(path, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (part === 'catalog') { if (!isCatalog(data)) throw new Error(); setCatalog(data); setActiveQuery(search.trim()); }
      if (part === 'slots') { if (!isSlots(data)) throw new Error(); setSlots(data); }
      if (part === 'me') { if (!isOverview(data)) throw new Error(); setMe(data); }
    } catch (error) {
      if (!controller.signal.aborted) { setErrors(e => ({ ...e, [part]: safeError(error) })); if (part === 'me') setMe(null); }
    } finally { if (!controller.signal.aborted) setPending(p => ({ ...p, [part]: false })); }
  }
  useEffect(() => {
    void load('catalog', '', 0); void load('slots'); void load('me');
    return () => { for (const c of reads.current.values()) c.abort(); for (const c of writes.current) c.abort(); };
  }, []);

  async function mutate<T>(path: string, body: object, guard: (value: unknown) => value is T): Promise<T> {
    const payload = JSON.stringify(body); const previous = attempts.current.get(path);
    const attempt = previous?.payload === payload ? previous : { payload, key: crypto.randomUUID() };
    attempts.current.set(path, attempt);
    const controller = new AbortController(); writes.current.add(controller); setBusy(true); setNotice(''); setErrors(e => ({ ...e, action: '' }));
    try {
      const data = await requestData<unknown>(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': attempt.key }, body: payload, signal: controller.signal });
      if (!guard(data)) throw new Error();
      attempts.current.delete(path); return data;
    } catch (error) {
      if (!controller.signal.aborted) {
        setErrors(e => ({ ...e, action: safeError(error) }));
        if (error instanceof ApiError && [401, 403].includes(error.status)) setMe(null);
      }
      throw error;
    } finally { writes.current.delete(controller); if (!controller.signal.aborted) setBusy(false); }
  }

  async function renew(loan: Loan) {
    try { const data = await mutate(`/library/me/loans/${loan.id}/renew`, { expected_revision: loan.revision }, isLoan); setMe(previous => previous ? { ...previous, loans: previous.loans.map(l => l.id === data.id ? data : l) } : previous); setNotice('가상 대출 연장 기록을 저장했습니다.'); } catch { /* safe error retained above */ }
  }
  async function requestTitle(event: FormEvent) {
    event.preventDefault();
    try { const data = await mutate('/library/me/wishes', { title, author, reason }, isWish); setMe(previous => previous ? { ...previous, wishes: [...previous.wishes.filter(w => w.id !== data.id), data] } : previous); setTitle(''); setAuthor(''); setReason(''); setNotice('가상 희망도서 요청을 저장했습니다. 실제 구입 신청이 아닙니다.'); } catch { /* preserve input and retry key */ }
  }
  async function reserve(slot: Slot) {
    try { const data = await mutate(`/library/me/slots/${slot.id}/reserve`, { expected_revision: slot.revision }, isBooking); updateBooking(data); setNotice('가상 공간 예약을 저장했습니다. 실제 시설 이용 권한이 아닙니다.'); void load('slots'); } catch { /* safe error retained above */ }
  }
  function updateBooking(data: Booking) { setMe(previous => previous ? { ...previous, bookings: [...previous.bookings.filter(b => b.id !== data.id), data] } : previous); }
  async function cancel(booking: Booking) {
    try { const data = await mutate(`/library/me/bookings/${booking.id}/cancel`, { expected_revision: booking.revision }, isBooking); updateBooking(data); setNotice('가상 공간 예약을 취소했습니다.'); void load('slots'); } catch { /* safe error retained above */ }
  }
  function issue(part: 'catalog' | 'slots' | 'me') { return errors[part] && <div role="alert"><p>{errors[part]}</p><button onClick={() => load(part)}>다시 확인</button></div>; }

  return <section className={styles.page} aria-labelledby="library-title">
    <header><span className={styles.eyebrow}>LIBRARY & SPACE</span><h1 id="library-title">도서관 · 공간</h1><p>읽고 싶은 책과 함께 공부할 공간을 찾아요.</p></header>
    <p className={styles.notice}>가상 도서·대출·공간 원장의 시연 모듈입니다. 실제 학교 도서관·전자정보·시설 예약과 연결되지 않습니다. 개인 신상 정보를 입력하지 마세요.</p>
    {errors.action && <p role="alert">{errors.action}</p>}{notice && <p role="status">{notice}</p>}
    <section className={styles.surface}><h2>자료 검색</h2><form onSubmit={event => { event.preventDefault(); void load('catalog', query, 0); }}><label htmlFor="library-search">도서명 또는 저자</label><div className={styles.inline}><input id="library-search" maxLength={120} value={query} onChange={e => setQuery(e.target.value)} /><button disabled={pending.catalog}>검색</button></div></form>
      {pending.catalog && <p role="status">도서를 검색하고 있어요…</p>}{issue('catalog')}
      {catalog && <><ul className={styles.list}>{catalog.items.map(book => <li key={book.id}><h3>{book.title}</h3><p>{book.author} · 가상 이용 가능 {book.available_copies}권</p>{book.public_reference_url && <a href={book.public_reference_url} target="_blank" rel="noopener noreferrer">공개 참고 원문 ↗</a>}</li>)}</ul>{catalog.items.length === 0 && <p>일치하는 가상 자료가 없습니다.</p>}<div className={styles.inline}><button disabled={pending.catalog || catalog.offset === 0} onClick={() => load('catalog', activeQuery, Math.max(0, catalog.offset - 20))}>이전 자료</button><button disabled={pending.catalog || !catalog.has_more} onClick={() => load('catalog', activeQuery, catalog.offset + 20)}>다음 자료</button></div></>}
    </section>
    <section className={styles.surface}><h2>나의 도서 이용</h2>{pending.me && <p role="status">본인 이용 내역을 확인하고 있어요…</p>}{issue('me')}
      {me && <><p className={styles.policy}>주입된 가상 정책: {me.policy.name} · 연장 {me.policy.renewal_days}일/최대 {me.policy.max_renewals}회 · 활성 예약 {me.policy.max_active_bookings}건. 학교 공식 규정이 아닙니다.</p>
        {me.loans.length === 0 && <p>본인 가상 대출 내역이 없습니다.</p>}<ul className={styles.list}>{me.loans.map(loan => <li key={loan.id}><h3>{loan.title}</h3><p>{loan.state === 'returned' ? '가상 반납됨' : '가상 대출 중'} · 기한 {formatDate(loan.due_at)} · 연장 {loan.renewal_count}회</p><button disabled={busy || loan.state !== 'active' || !loan.renewable || loan.renewal_count >= me.policy.max_renewals} onClick={() => renew(loan)}>시연 연장</button></li>)}</ul>
        <form onSubmit={requestTitle}><h3>희망도서 시연 요청</h3><label htmlFor="wish-title">도서명</label><input id="wish-title" required maxLength={200} disabled={busy} value={title} onChange={e => setTitle(e.target.value)} /><label htmlFor="wish-author">저자</label><input id="wish-author" required maxLength={100} disabled={busy} value={author} onChange={e => setAuthor(e.target.value)} /><label htmlFor="wish-reason">요청 사유 (선택·500자 이내)</label><textarea id="wish-reason" maxLength={500} disabled={busy} value={reason} onChange={e => setReason(e.target.value)} /><button disabled={busy || !title.trim() || !author.trim()}>시연 요청 저장</button></form>
        <ul className={styles.list}>{me.wishes.map(wish => <li key={wish.id}><h3>{wish.title}</h3><p>{wish.author} · {wish.state === 'requested' ? '가상 요청됨' : wish.state === 'reviewing' ? '가상 검토 중' : wish.state === 'completed' ? '가상 처리됨' : '가상 취소됨'}</p></li>)}</ul>
      </>}
    </section>
    <section className={styles.surface}><h2>공간 시간대</h2><p className={styles.note}>시간은 기기 시간대로 표시하며 서버가 UTC 시각과 중복을 재검증합니다. 실제 시설 사용이 보장되지 않습니다.</p>{pending.slots && <p role="status">시간대를 확인하고 있어요…</p>}{issue('slots')}
      {slots?.length === 0 && <p>가상 예약 가능 시간대가 없습니다.</p>}<ul className={styles.list}>{slots?.map(slot => <li key={slot.id}><h3>{slot.space_name}</h3><p>{formatDate(slot.starts_at)} ~ {formatDate(slot.ends_at)}</p><button disabled={busy || !slot.available || !me} onClick={() => reserve(slot)}>{slot.available ? '시연 예약' : '가상 예약 불가'}</button></li>)}</ul>
      {me && <><h3>나의 가상 예약</h3>{me.bookings.length === 0 && <p>본인 가상 예약이 없습니다.</p>}<ul className={styles.list}>{me.bookings.map(booking => <li key={booking.id}><h3>{booking.space_name}</h3><p>{formatDate(booking.starts_at)} · {booking.state === 'reserved' ? '가상 예약됨' : '가상 취소됨'}</p>{booking.state === 'reserved' && <button disabled={busy} onClick={() => cancel(booking)}>시연 예약 취소</button>}</li>)}</ul></>}
    </section>
  </section>;
}
