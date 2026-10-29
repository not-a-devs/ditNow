import { useCallback, useEffect, useState } from "react";
import { getNotice, listNotices } from "./api";
import { NOTICE_STATUS_LABEL, audienceLabel, formatDateTime, toErrorView } from "./model";
import { EmptyView, ErrorView, LoadingView } from "./StatusView";
import type { LoadState, Notice } from "./types";

interface Props {
  openNoticeId: string | null;
  onOpenNotice: (noticeId: string | null) => void;
}

// Read-only first pass. Authoring UI waits for the shared auth/role layer (RBAC-NOT).
export function NoticePanel({ openNoticeId, onOpenNotice }: Props) {
  const [list, setList] = useState<LoadState<Notice[]>>({ status: "loading" });

  const load = useCallback(() => {
    setList({ status: "loading" });
    listNotices()
      .then((data) => setList({ status: "ready", data: data.items }))
      .catch((error: unknown) => setList({ status: "error", error: toErrorView(error) }));
  }, []);

  useEffect(load, [load]);

  if (openNoticeId) return <NoticeDetail noticeId={openNoticeId} onBack={() => onOpenNotice(null)} />;
  if (list.status === "loading") return <LoadingView label="공지" />;
  if (list.status === "error") return <ErrorView error={list.error} onRetry={load} />;
  if (list.data.length === 0) return <EmptyView label="받은 공지가 없습니다." />;

  return (
    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
      {list.data.map((notice) => (
        <li key={notice.id}>
          <button
            type="button"
            onClick={() => onOpenNotice(notice.id)}
            className="flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <span className="text-xs text-slate-500">
              {audienceLabel(notice.audience)} · {NOTICE_STATUS_LABEL[notice.status]}
            </span>
            <span className="font-medium text-slate-900">{notice.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function NoticeDetail({ noticeId, onBack }: { noticeId: string; onBack: () => void }) {
  const [state, setState] = useState<LoadState<Notice>>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getNotice(noticeId)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => setState({ status: "error", error: toErrorView(error) }));
  }, [noticeId]);

  useEffect(load, [load]);

  return (
    <article className="rounded-lg border border-slate-200 p-4">
      <button type="button" onClick={onBack} className="mb-3 text-sm text-blue-700 hover:underline">
        ← 공지 목록
      </button>
      {state.status === "loading" && <LoadingView label="공지" />}
      {state.status === "error" && <ErrorView error={state.error} onRetry={load} />}
      {state.status === "ready" && (
        <>
          <p className="text-xs text-slate-500">
            {audienceLabel(state.data.audience)} · {NOTICE_STATUS_LABEL[state.data.status]} · 개정 {state.data.revision}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">{state.data.title}</h2>
          {state.data.published_at && (
            <p className="text-xs text-slate-500">게시 {formatDateTime(state.data.published_at)}</p>
          )}
          <p className="mt-3 whitespace-pre-wrap break-words text-sm text-slate-800">{state.data.body}</p>
        </>
      )}
    </article>
  );
}
