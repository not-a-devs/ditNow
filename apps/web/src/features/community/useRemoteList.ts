import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, type IssueInfo } from "./api";
import type { Page } from "./types";

export type ListState<T> =
  | { status: "loading" }
  | { status: "issue"; issue: IssueInfo }
  | { status: "ready"; items: T[]; hasMore: boolean };

// No fallback store. Cleanup prevents a completed old mutation from querying a new session.
export function useRemoteList<T>(load: (signal?: AbortSignal) => Promise<Page<T>>) {
  const [state, setState] = useState<ListState<T>>({ status: "loading" });
  const loadRef = useRef(load); loadRef.current = load;
  const lifetime = useRef(0), alive = useRef(false), request = useRef<AbortController | null>(null);
  const reload = useCallback(async () => {
    if (!alive.current) return;
    const version = ++lifetime.current;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const current = () => alive.current && lifetime.current === version && !controller.signal.aborted;
    setState({ status: "loading" });
    try {
      const page = await loadRef.current(controller.signal);
      if (current()) setState({ status: "ready", items: page.items, hasMore: page.has_more });
    } catch (error) {
      if (current()) setState({ status: "issue", issue: describeError(error) });
    }
  }, []);
  useEffect(() => {
    alive.current = true; void reload();
    return () => { alive.current = false; lifetime.current++; request.current?.abort(); };
  }, [reload]);
  return { state, reload };
}
