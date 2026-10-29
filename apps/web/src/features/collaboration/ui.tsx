import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { describeError, isAuthIssue, type Issue } from "./api";

// A 401/403 anywhere is lifted to the feature root, which removes every personal view.
export const AuthIssueContext = createContext<(issue: Issue) => void>(() => {});

/** Returns an error handler that lifts auth issues and gives back the described issue. */
export function useIssueHandler() {
  const lift = useContext(AuthIssueContext);
  return useCallback(
    (error: unknown): Issue => {
      const issue = describeError(error);
      if (isAuthIssue(issue)) lift(issue);
      return issue;
    },
    [lift],
  );
}

export type Remote<T> = { status: "loading" } | { status: "issue"; issue: Issue } | { status: "ready"; data: T };

// Server data only; there is no local, mock or cached fallback. Each load is one generation with
// its own AbortController: a newer load, a key change or unmount aborts it, and a superseded
// generation's result or error (including 401/403) is dropped instead of overwriting state or
// lifting an auth issue.
export function useRemote<T>(load: (signal: AbortSignal) => Promise<T>, reloadKey: string) {
  const [state, setState] = useState<Remote<T>>({ status: "loading" });
  const loadRef = useRef(load);
  loadRef.current = load;
  const current = useRef<AbortController | null>(null);
  const handle = useIssueHandler();

  const reload = useCallback(async () => {
    current.current?.abort();
    const generation = new AbortController();
    current.current = generation;
    setState({ status: "loading" });
    try {
      const data = await loadRef.current(generation.signal);
      if (current.current === generation) setState({ status: "ready", data });
    } catch (error) {
      if (current.current === generation) setState({ status: "issue", issue: handle(error) });
    }
  }, [handle]);

  useEffect(() => {
    void reload();
    return () => {
      current.current?.abort();
      current.current = null;
    };
  }, [reload, reloadKey]);

  return { state, reload };
}

const TONE: Record<Issue["kind"], string> = {
  unavailable: "border-amber-300 bg-amber-50 text-amber-900",
  unauthenticated: "border-slate-300 bg-slate-50 text-slate-800",
  forbidden: "border-slate-300 bg-slate-50 text-slate-800",
  error: "border-red-300 bg-red-50 text-red-900",
};

export function IssueBox({ issue, onRetry }: { issue: Issue; onRetry?: () => void }) {
  return (
    <div role="status" className={`rounded-lg border p-3 text-sm ${TONE[issue.kind]}`}>
      <p>{issue.message}</p>
      {issue.requestId && <p className="mt-1 text-xs opacity-70">요청 ID: {issue.requestId}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 rounded-md border border-current px-3 py-1 text-xs font-medium">
          다시 시도
        </button>
      )}
    </div>
  );
}

export function InlineIssue({ issue }: { issue: Issue | null }) {
  if (!issue) return null;
  return (
    <p role="alert" className="text-sm text-red-700">
      {issue.message}
      {issue.requestId && <span className="ml-1 text-xs opacity-70">({issue.requestId})</span>}
    </p>
  );
}

export function RemoteView<T>({
  remote,
  label,
  isEmpty,
  onRetry,
  children,
}: {
  remote: Remote<T>;
  label: string;
  isEmpty: (data: T) => boolean;
  onRetry: () => void;
  children: (data: T) => ReactNode;
}) {
  if (remote.status === "loading")
    return <p role="status" aria-live="polite" className="py-4 text-center text-sm text-slate-500">{label} 불러오는 중…</p>;
  if (remote.status === "issue") return <IssueBox issue={remote.issue} onRetry={onRetry} />;
  if (isEmpty(remote.data)) return <p className="py-4 text-center text-sm text-slate-500">{label}이(가) 없습니다.</p>;
  return <>{children(remote.data)}</>;
}

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "short" });

export const button = "rounded-md border border-slate-300 px-3 py-1 text-sm disabled:opacity-50";
export const primary = "rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50";
export const field = "w-full rounded-md border border-slate-300 px-3 py-2 text-sm";
