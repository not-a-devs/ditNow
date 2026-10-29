import { useMemo, useState, type FormEvent } from "react";
import { collaborationApi, createKeyTracker, type Issue } from "./api";
import { REPORT_REASONS, type PostSummary, type ReportReason, type ReportTargetType } from "./types";
import { InlineIssue, RemoteView, button, field, formatTime, primary, useIssueHandler, useRemote } from "./ui";

const COMMENT_MAX = 1000;

// FR-COM-002/003: search, anonymous comments, bookmarks and reason-only report requests.
export function AnonymousPanel() {
  const [text, setText] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const [selected, setSelected] = useState<PostSummary | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = text.trim();
    if (q.length < 2 || q.length > 50) {
      setHint("검색어는 2~50자로 입력하세요.");
      return;
    }
    setHint(null);
    setSelected(null);
    setQuery(q);
  };

  return (
    <section aria-labelledby="anon-search" className="space-y-4">
      <h2 id="anon-search" className="text-lg font-semibold">익명 글 검색·댓글</h2>
      <form onSubmit={submit} className="flex gap-2">
        <label className="sr-only" htmlFor="anon-query">검색어</label>
        <input id="anon-query" className={field} value={text} onChange={e => setText(e.target.value)} placeholder="제목·본문 검색" />
        <button type="submit" className={primary}>검색</button>
      </form>
      {hint && <p role="alert" className="text-sm text-red-700">{hint}</p>}
      {query && <SearchResults query={query} onOpen={setSelected} />}
      {selected && <Thread key={selected.id} post={selected} />}
    </section>
  );
}

function SearchResults({ query, onOpen }: { query: string; onOpen: (post: PostSummary) => void }) {
  const { state, reload } = useRemote(() => collaborationApi.searchPosts(query), query);
  return (
    <RemoteView remote={state} label="검색 결과" isEmpty={page => page.items.length === 0} onRetry={reload}>
      {page => (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
          {page.items.map(post => (
            <li key={post.id} className="space-y-1 p-3">
              <p className="font-medium">{post.title}</p>
              <p className="text-sm text-slate-600">{post.excerpt}</p>
              <p className="text-xs text-slate-500">{post.display_name} · {formatTime(post.created_at)} · 댓글 {post.comment_count}</p>
              <div className="flex gap-2">
                <button type="button" className={button} onClick={() => onOpen(post)}>댓글 보기</button>
                <BookmarkButton postId={post.id} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </RemoteView>
  );
}

function BookmarkButton({ postId }: { postId: string }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const handle = useIssueHandler();
  const toggle = async () => {
    setBusy(true);
    setIssue(null);
    try {
      const state = saved ? await collaborationApi.removeBookmark(postId) : await collaborationApi.addBookmark(postId);
      setSaved(state.bookmarked); // only the server's answer changes the label
    } catch (error) {
      setIssue(handle(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="flex items-center gap-2">
      <button type="button" className={button} disabled={busy} aria-pressed={saved} onClick={toggle}>
        {saved ? "북마크 해제" : "북마크"}
      </button>
      <InlineIssue issue={issue} />
    </span>
  );
}

function Thread({ post }: { post: PostSummary }) {
  const [version, setVersion] = useState(0);
  const { state, reload } = useRemote(() => collaborationApi.listComments(post.id), `${post.id}:${version}`);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const keys = useMemo(() => createKeyTracker(), []);
  const handle = useIssueHandler();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = body.trim();
    if (!text || text.length > COMMENT_MAX) {
      setIssue({ kind: "error", message: `댓글은 1~${COMMENT_MAX}자로 입력하세요.` });
      return;
    }
    setBusy(true);
    setIssue(null);
    try {
      await collaborationApi.createComment(post.id, text, keys.keyFor({ post: post.id, text }));
      keys.reset();
      setBody("");
      setVersion(v => v + 1);
    } catch (error) {
      setIssue(handle(error)); // input and key are kept for an identical retry
    } finally {
      setBusy(false);
    }
  };

  const remove = async (commentId: string, revision: number) => {
    setIssue(null);
    try {
      await collaborationApi.deleteComment(post.id, commentId, revision);
      setVersion(v => v + 1);
    } catch (error) {
      setIssue(handle(error));
    }
  };

  return (
    <article aria-label="댓글 스레드" className="space-y-3 rounded-lg border border-slate-200 p-3">
      <header className="space-y-1">
        <h3 className="font-semibold">{post.title}</h3>
        <ReportControl targetType="anonymous_post" targetId={post.id} label="글 신고" />
      </header>
      <RemoteView remote={state} label="댓글" isEmpty={page => page.items.length === 0} onRetry={reload}>
        {page => (
          <ul className="space-y-2">
            {page.items.map(comment => (
              <li key={comment.id} className="rounded-md bg-slate-50 p-2 text-sm">
                <p className="whitespace-pre-wrap">{comment.body}</p>
                <p className="text-xs text-slate-500">{comment.display_name} · {formatTime(comment.created_at)}</p>
                <div className="mt-1 flex gap-2">
                  {comment.is_mine ? (
                    <button type="button" className={button} onClick={() => remove(comment.id, comment.revision)}>내 댓글 삭제</button>
                  ) : (
                    <ReportControl targetType="anonymous_comment" targetId={comment.id} label="댓글 신고" />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </RemoteView>
      <form onSubmit={submit} className="space-y-2">
        <label className="block text-sm font-medium" htmlFor={`comment-${post.id}`}>익명 댓글</label>
        <textarea id={`comment-${post.id}`} className={field} rows={3} value={body} onChange={e => setBody(e.target.value)} />
        <button type="submit" className={primary} disabled={busy || state.status !== "ready"}>익명 댓글 등록 요청</button>
        <InlineIssue issue={issue} />
      </form>
    </article>
  );
}

function ReportControl({ targetType, targetId, label }: { targetType: ReportTargetType; targetId: string; label: string }) {
  const [reason, setReason] = useState<ReportReason>("spam");
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const [done, setDone] = useState(false);
  const keys = useMemo(() => createKeyTracker(), []);
  const handle = useIssueHandler();

  const send = async () => {
    setBusy(true);
    setIssue(null);
    try {
      await collaborationApi.createReport(targetType, targetId, reason, keys.keyFor({ targetType, targetId, reason }));
      keys.reset();
      setDone(true);
    } catch (error) {
      setIssue(handle(error));
    } finally {
      setBusy(false);
    }
  };

  if (done) return <p className="text-xs text-slate-600">신고 요청이 접수되었습니다. 검토·제재 절차는 운영 정책 승인 전이라 아직 진행되지 않습니다.</p>;
  return (
    <span className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor={`reason-${targetId}`}>{label} 사유</label>
      <select id={`reason-${targetId}`} className="rounded-md border border-slate-300 px-2 py-1 text-xs" value={reason} onChange={e => setReason(e.target.value as ReportReason)}>
        {REPORT_REASONS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
      <button type="button" className={button} disabled={busy} onClick={send}>{label}</button>
      <InlineIssue issue={issue} />
    </span>
  );
}
