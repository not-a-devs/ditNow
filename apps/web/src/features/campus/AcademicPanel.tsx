import { useCallback, useEffect, useState } from "react";
import { listTermEvents, listTerms } from "./api";
import { SOURCE_LABEL, toErrorView } from "./model";
import { EmptyView, ErrorView, LoadingView } from "./StatusView";
import type { AcademicEventList, AcademicTerm, LoadState } from "./types";

// FR-ACA-001 read-only calendar. Records are DEMO or cited public snapshots, never school ledgers.
export function AcademicPanel() {
  const [terms, setTerms] = useState<LoadState<AcademicTerm[]>>({ status: "loading" });
  const [termId, setTermId] = useState<string | null>(null);

  const load = useCallback(() => {
    setTerms({ status: "loading" });
    listTerms()
      .then((data) => {
        setTerms({ status: "ready", data: data.items });
        setTermId((current) => current ?? data.items[0]?.id ?? null);
      })
      .catch((error: unknown) => setTerms({ status: "error", error: toErrorView(error) }));
  }, []);

  useEffect(load, [load]);

  if (terms.status === "loading") return <LoadingView label="학기" />;
  if (terms.status === "error") return <ErrorView error={terms.error} onRetry={load} />;
  if (terms.data.length === 0) return <EmptyView label="등록된 학기 일정이 없습니다." />;

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-slate-600">학기</span>
        <select
          value={termId ?? ""}
          onChange={(event) => setTermId(event.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1"
        >
          {terms.data.map((term) => (
            <option key={term.id} value={term.id}>
              {term.name}
            </option>
          ))}
        </select>
      </label>
      {termId && <TermEvents key={termId} termId={termId} />}
    </div>
  );
}

function TermEvents({ termId }: { termId: string }) {
  const [state, setState] = useState<LoadState<AcademicEventList>>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    listTermEvents(termId)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => setState({ status: "error", error: toErrorView(error) }));
  }, [termId]);

  useEffect(load, [load]);

  if (state.status === "loading") return <LoadingView label="학사 일정" />;
  if (state.status === "error") return <ErrorView error={state.error} onRetry={load} />;
  if (state.data.items.length === 0) return <EmptyView label="이 학기에 등록된 일정이 없습니다." />;

  return (
    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
      {state.data.items.map((event) => (
        <li key={event.id} className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="font-medium text-slate-900">{event.title}</span>
          <span className="text-slate-600">
            {event.starts_on === event.ends_on ? event.starts_on : `${event.starts_on} ~ ${event.ends_on}`}
          </span>
          <span className="text-xs text-slate-500">
            {SOURCE_LABEL[event.source_kind]}
            {event.source_url && (
              <>
                {" · "}
                <a href={event.source_url} target="_blank" rel="noopener noreferrer" className="underline">
                  출처
                </a>
              </>
            )}
            {event.checked_at && ` · 확인 ${event.checked_at}`}
          </span>
        </li>
      ))}
    </ul>
  );
}
