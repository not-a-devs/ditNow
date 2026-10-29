import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { authFailure, isNotice, isPage, isSummaries, read, safeError, uuid, write, type Item, type Notice, type Page, type Summary } from './api';
import styles from './styles.module.css';

type State<T> = { data?: T; loading: boolean; error: boolean };
function useResource<T>(path: string | null, guard: (v: unknown) => v is T, onAuth: () => void) {
  const [state, setState] = useState<State<T>>({ loading: false, error: false });
  const [tick, update] = useState(0);
  useEffect(() => {
    if (path === null) { setState({ loading: false, error: false }); return; }
    const controller = new AbortController(); setState({ loading: true, error: false });
    read(path, guard, controller.signal).then(data => { if (!controller.signal.aborted) setState({ data, loading: false, error: false }); }, error => {
      if (controller.signal.aborted) return;
      if (authFailure(error)) onAuth();
      setState({ loading: false, error: true });
    });
    return () => controller.abort();
  }, [path, tick, guard, onAuth]);
  return { ...state, reload: () => update(n => n + 1) };
}

function Status({ state }: { state: State<unknown> & { reload: () => void } }) {
  return state.loading ? <p role="status">불러오는 중입니다.</p> : state.error ? <div role="alert"><p>{safeError()}</p><button onClick={state.reload}>다시 확인</button></div> : null;
}

export default function NoticeDiscussionPage({ departmentId }: { departmentId?: string }) {
  const [denied, setDenied] = useState(false);
  const [generation, setGeneration] = useState(0);
  const onAuth = useCallback(() => setDenied(true), []);
  return <section className={styles.page}><h1>공지와 학과 질문</h1><p className={styles.notice}>독립 플랫폼의 가상 흐름입니다. 학교 공식 연결·실명 표시 정책·공식 답변·읽음 통계·파일 저장은 연결되지 않았습니다.</p>
    {denied ? <div role="alert"><p>현재 접근 권한을 확인하지 못해 내용을 비웠습니다.</p><button onClick={() => { setDenied(false); setGeneration(g => g + 1); }}>권한 다시 확인</button></div> : <Workspace key={`${generation}-${departmentId ?? 'unconnected'}`} departmentId={departmentId} onAuth={onAuth} />}
  </section>;
}

function Workspace({ departmentId, onAuth }: { departmentId?: string; onAuth: () => void }) {
  const [tab, setTab] = useState<'notices' | 'questions'>('notices');
  const [draft, setDraft] = useState(''); const [query, setQuery] = useState('');
  const [noticeId, selectNotice] = useState<string | null>(null);
  const [question, selectQuestion] = useState<Item | null>(null);
  const [offset, setOffset] = useState(0);
  const department = departmentId && uuid(departmentId) ? departmentId : null;
  const base = department ? `/departments/${department}` : null;
  const notices = useResource<Summary[]>(tab === 'notices' ? `/notices?q=${encodeURIComponent(query)}&limit=25` : null, isSummaries, onAuth);
  const detail = useResource<Notice>(tab === 'notices' && noticeId ? `/notices/${noticeId}` : null, isNotice, onAuth);
  const questions = useResource<Page>(tab === 'questions' && base ? `${base}/questions?offset=${offset}&limit=10` : null, isPage, onAuth);
  const comments = useResource<Page>(tab === 'questions' && base && question ? `${base}/questions/${question.id}/comments?limit=50` : null, isPage, onAuth);
  function search(event: FormEvent) { event.preventDefault(); selectNotice(null); setQuery(draft.trim()); }
  function changed() { questions.reload(); comments.reload(); selectQuestion(null); }
  return <>
    <nav aria-label="공지와 질문 메뉴"><button aria-pressed={tab === 'notices'} onClick={() => setTab('notices')}>공지 원본</button><button aria-pressed={tab === 'questions'} onClick={() => setTab('questions')}>학과 질문</button></nav>
    {tab === 'notices' ? <>
      <form onSubmit={search}><label>공지 검색<input maxLength={100} value={draft} onChange={e => setDraft(e.target.value)} /></label><button>검색</button></form>
      <p>최근 접근 가능한 공지 최대 25건 안에서 검색합니다. 전체 학교 검색 결과가 아닙니다.</p>
      <Status state={notices} />{notices.data?.length === 0 && <p>표시할 공지가 없습니다.</p>}
      {notices.data?.map(n => <article key={n.id} className={styles.card}><h2>{n.title}</h2><p>개정 {n.revision} · {n.status === 'ARCHIVED' ? '보관' : '게시'}</p><button onClick={() => selectNotice(n.id)}>내용과 이력 보기</button></article>)}
      <Status state={detail} />{detail.data && detail.data.id === noticeId && <article className={styles.card}><h2>{detail.data.title}</h2><p className={styles.body}>{detail.data.body}</p><h3>첨부 메타데이터</h3><p>파일 저장·다운로드 미연결</p>{detail.data.attachments.map(a => <p key={a.id}>{a.filename} · {a.size_bytes} bytes</p>)}<h3>개정 메타데이터</h3><p>이전 본문·작성자 정보는 제공하지 않습니다.</p>{detail.data.history.map((h,i) => <p key={i}>개정 {h.revision} · {h.changed_at} · {h.event}</p>)}</article>}
    </> : !base ? <p role="status">승인된 공통 원장에서 현재 학과가 연결되면 질문 게시판을 사용할 수 있습니다. 가상 학과나 로그인으로 대체하지 않습니다.</p> : <>
      <Editor departmentId={department!} path={`${base}/questions`} questionMode onSaved={changed} onAuth={onAuth} />
      <Status state={questions} />{questions.data?.items.length === 0 && <p>표시할 질문이 없습니다.</p>}
      {questions.data?.items.filter(q => q.department_id === department && q.kind === 'QUESTION').map(q => <article key={q.id} className={styles.card}><h2>{q.title}</h2><p className={styles.body}>{q.body}</p><p>{q.is_mine ? '내가 작성한 시연 질문' : '시연 질문'} · 작성자 표시 정책 미연결</p><button onClick={() => selectQuestion(q)}>댓글 보기</button>{q.is_mine && <Editor item={q} departmentId={department!} path={`${base}/items/${q.id}`} questionMode onSaved={changed} onAuth={onAuth} />}</article>)}
      <nav aria-label="질문 페이지"><button disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset-10)); selectQuestion(null); }}>이전</button><button disabled={!questions.data || questions.data.items.length < 10} onClick={() => { setOffset(offset+10); selectQuestion(null); }}>다음</button></nav>
      {question && <section key={question.id} className={styles.card}><h2>{question.title} · 댓글</h2><Editor departmentId={department!} questionId={question.id} path={`${base}/questions/${question.id}/comments`} onSaved={() => comments.reload()} onAuth={onAuth} /><Status state={comments} />{comments.data?.items.filter(c => c.department_id === department && c.question_id === question.id && c.kind === 'COMMENT').map(c => <article key={c.id}><p className={styles.body}>{c.body}</p>{c.is_mine && <Editor item={c} departmentId={department!} questionId={question.id} path={`${base}/items/${c.id}`} onSaved={() => comments.reload()} onAuth={onAuth} />}</article>)}</section>}
    </>}
  </>;
}

function Editor({ item, departmentId, questionId = null, path, questionMode = false, onSaved, onAuth }: { item?: Item; departmentId: string; questionId?: string | null; path: string; questionMode?: boolean; onSaved: () => void; onAuth: () => void }) {
  const [title, setTitle] = useState(item?.title ?? ''); const [body, setBody] = useState(item?.body ?? '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(false);
  const request = useRef<AbortController | null>(null);
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function save(event?: FormEvent, remove = false) {
    event?.preventDefault(); if (request.current || busy) return;
    const payload = remove ? null : { ...(questionMode ? { title: title.trim() } : {}), body: body.trim(), ...(item ? { expected_revision: item.revision } : {}) };
    const fingerprint = JSON.stringify(payload);
    if (!intent.current || intent.current.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
    const controller = new AbortController(); request.current = controller; setBusy(true); setError(false);
    try {
      const saved = await write(remove ? `${path}?expected_revision=${item!.revision}` : path, remove ? 'DELETE' : item ? 'PATCH' : 'POST', payload, item ? null : intent.current.key, controller.signal);
      if (controller.signal.aborted) return;
      if (saved && (saved.department_id !== departmentId || saved.question_id !== questionId || saved.kind !== (questionMode ? 'QUESTION' : 'COMMENT') || !saved.is_mine || (item && saved.id !== item.id))) throw new Error('Invalid context');
      intent.current = null; if (!item) { setTitle(''); setBody(''); } onSaved();
    } catch (failure) { if (!controller.signal.aborted) { if (authFailure(failure)) onAuth(); setError(true); } }
    finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); } }
  }
  return <form onSubmit={save} className={styles.editor} aria-label={questionMode ? '시연 질문 작성·수정' : '시연 댓글 작성·수정'}>
    {questionMode && <label>질문 제목<input required maxLength={160} value={title} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>}
    <label>{questionMode ? '질문 내용' : '댓글 내용'}<textarea required maxLength={4000} value={body} disabled={busy} onChange={e => setBody(e.target.value)} /></label>
    <button disabled={busy || !body.trim() || (questionMode && !title.trim())}>{busy ? '처리 중' : item ? '수정 저장' : '시연 글 저장'}</button>
    {item && <button type="button" disabled={busy} onClick={() => save(undefined, true)}>내 글 삭제</button>}
    {error && <p role="alert">{safeError()}</p>}
  </form>;
}
