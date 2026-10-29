import type { CampusErrorView } from "./types";

export function LoadingView({ label }: { label: string }) {
  return (
    <p role="status" aria-live="polite" className="py-6 text-center text-sm text-slate-500">
      {label} 불러오는 중…
    </p>
  );
}

export function EmptyView({ label }: { label: string }) {
  return <p className="py-6 text-center text-sm text-slate-500">{label}</p>;
}

export function ErrorView({ error, onRetry }: { error: CampusErrorView; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
      <p className="font-semibold text-amber-900">{error.title}</p>
      <p className="mt-1 text-amber-800">{error.detail}</p>
      {error.requestId && <p className="mt-1 text-xs text-amber-700">요청 ID: {error.requestId}</p>}
      {error.retryable && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-amber-400 px-3 py-1 text-amber-900 hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}
