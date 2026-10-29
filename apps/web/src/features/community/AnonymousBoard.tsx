import { useRequestLifetime } from '../../lib/useRequestLifetime';
import { useState, type FormEvent } from "react";
import { communityApi, createKeyTracker, describeError, type IssueInfo } from "./api";
import { EmptyPanel, InlineIssue, LoadingPanel, StatusPanel } from "./StatusPanel";
import { LIMITS, type AnonymousPost } from "./types";
import { useRemoteList } from "./useRemoteList";

// FR-COM-001. Author identity never reaches the client; only server-computed `is_mine`.
export function validatePost(title: string, body: string): string | null {
  const t = title.trim();
  const b = body.trim();
  if (t.length < LIMITS.titleMin || t.length > LIMITS.titleMax)
    return `제목은 ${LIMITS.titleMin}~${LIMITS.titleMax}자로 입력하세요.`;
  if (/[\r\n]/.test(t)) return "제목에는 줄바꿈을 넣을 수 없습니다.";
  if (b.length < 1 || b.length > LIMITS.bodyMax)
    return `본문은 1~${LIMITS.bodyMax}자로 입력하세요.`;
  return null;
}

export function AnonymousBoard() {
  const { state, reload } = useRemoteList(communityApi.listPosts);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pending, setPending] = useState(false);
  const lifetime = useRequestLifetime();
  const [formError, setFormError] = useState<string | null>(null);
  const [issue, setIssue] = useState<IssueInfo | null>(null);
  const [keys] = useState(() => createKeyTracker());

  async function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = validatePost(title, body);
    setFormError(invalid);
    setIssue(null);
    if (invalid) return;
    const request = lifetime.begin(); if (!request) return;
    setPending(true);
    try {
      const input = { title: title.trim(), body: body.trim() };
      await communityApi.createPost(input, keys.keyFor(input));
      if (!request.current()) return;
      keys.reset();
      setTitle("");
      setBody("");
      await reload(); // Show the server's list, not an optimistic local copy.
    } catch (error) {
      if (request.current()) setIssue(describeError(error));
    } finally {
      if (request.current()) setPending(false);
      request.finish();
    }
  }

  return (
    <section aria-labelledby="anon-heading" className="space-y-4">
      <header>
        <h2 id="anon-heading" className="text-lg font-semibold text-slate-900">
          익명 자유게시판
        </h2>
        <p className="text-sm text-slate-600">
          작성자는 모두 &lsquo;익명&rsquo;으로 표시되며 실명 모집글과 연결되지 않습니다.
        </p>
      </header>

      <form onSubmit={submit} className="space-y-2 rounded-lg border border-slate-200 p-4">
        <label className="block text-sm font-medium text-slate-700">
          제목
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={LIMITS.titleMax}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          본문
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={LIMITS.bodyMax}
            rows={4}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        {formError && (
          <p role="alert" className="text-sm text-red-700">
            {formError}
          </p>
        )}
        <InlineIssue issue={issue} />
        <button
          type="submit"
          disabled={pending || state.status !== "ready"}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "서버에 요청 중…" : "익명으로 등록 요청"}
        </button>
      </form>

      {state.status === "loading" && <LoadingPanel label="게시글" />}
      {state.status === "issue" && <StatusPanel issue={state.issue} onRetry={reload} />}
      {state.status === "ready" && state.items.length === 0 && <EmptyPanel label="게시글" />}
      {state.status === "ready" && state.items.length > 0 && (
        <ul className="space-y-3">
          {state.items.map((post) => (
            <PostItem key={post.id} post={post} onChanged={reload} />
          ))}
        </ul>
      )}
    </section>
  );
}

function PostItem({ post, onChanged }: { post: AnonymousPost; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const [pending, setPending] = useState(false);
  const lifetime = useRequestLifetime();
  const [issue, setIssue] = useState<IssueInfo | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    const request = lifetime.begin(); if (!request) return;
    setPending(true);
    setIssue(null);
    try {
      await action();
      if (!request.current()) return;
      setEditing(false);
      await onChanged();
    } catch (error) {
      if (request.current()) setIssue(describeError(error));
    } finally {
      if (request.current()) setPending(false);
      request.finish();
    }
  }

  function save() {
    const invalid = validatePost(title, body);
    setFormError(invalid);
    if (!invalid)
      void run(() =>
        communityApi.updatePost(post.id, post.revision, { title: title.trim(), body: body.trim() }),
      );
  }

  function remove() {
    if (window.confirm("이 글을 삭제할까요?"))
      void run(() => communityApi.deletePost(post.id, post.revision));
  }

  return (
    <li className="rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{post.display_name}</span>
        <time dateTime={post.created_at}>{new Date(post.created_at).toLocaleString("ko-KR")}</time>
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <input
            aria-label="제목 수정"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={LIMITS.titleMax}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
          <textarea
            aria-label="본문 수정"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={LIMITS.bodyMax}
            rows={3}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
          {formError && <p className="text-sm text-red-700">{formError}</p>}
        </div>
      ) : (
        <>
          {/* Rendered as text; React escapes HTML so injected markup is inert. */}
          <h3 className="mt-1 font-medium text-slate-900">{post.title}</h3>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{post.body}</p>
        </>
      )}
      <InlineIssue issue={issue} />
      {post.is_mine && (
        <div className="mt-3 flex gap-2 text-xs">
          {editing ? (
            <>
              <button type="button" disabled={pending} onClick={save} className="underline">
                수정 요청
              </button>
              <button type="button" onClick={() => setEditing(false)} className="underline">
                취소
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => setEditing(true)} className="underline">
                수정
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={remove}
                className="text-red-700 underline"
              >
                삭제
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}
