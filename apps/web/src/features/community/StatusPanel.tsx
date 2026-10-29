import type { IssueInfo } from "./api";

interface StatusPanelProps {
  issue: IssueInfo;
  onRetry: () => void;
}

const TONE: Record<IssueInfo["kind"], string> = {
  unavailable: "border-amber-300 bg-amber-50 text-amber-900",
  unauthenticated: "border-slate-300 bg-slate-50 text-slate-800",
  forbidden: "border-slate-300 bg-slate-50 text-slate-800",
  error: "border-red-300 bg-red-50 text-red-900",
};

export function StatusPanel({ issue, onRetry }: StatusPanelProps) {
  return (
    <div role="status" className={`rounded-lg border p-4 text-sm ${TONE[issue.kind]}`}>
      <p>{issue.message}</p>
      {issue.requestId && <p className="mt-1 text-xs opacity-70">요청 ID: {issue.requestId}</p>}
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-md border border-current px-3 py-1 text-xs font-medium"
      >
        다시 시도
      </button>
    </div>
  );
}

export function LoadingPanel({ label }: { label: string }) {
  return (
    <p role="status" aria-live="polite" className="py-6 text-center text-sm text-slate-500">
      {label} 불러오는 중…
    </p>
  );
}

export function EmptyPanel({ label }: { label: string }) {
  return <p className="py-6 text-center text-sm text-slate-500">{label}이(가) 아직 없습니다.</p>;
}

export function InlineIssue({ issue }: { issue: IssueInfo | null }) {
  if (!issue) return null;
  return (
    <p role="alert" className="text-sm text-red-700">
      {issue.message}
      {issue.requestId && <span className="ml-1 text-xs opacity-70">({issue.requestId})</span>}
    </p>
  );
}
