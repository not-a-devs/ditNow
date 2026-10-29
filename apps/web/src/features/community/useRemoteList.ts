import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, type IssueInfo } from "./api";
import type { Page } from "./types";

export type ListState<T> =
  | { status: "loading" }
  | { status: "issue"; issue: IssueInfo }
  | { status: "ready"; items: T[]; hasMore: boolean };

// Loads a page from the server only; there is no local or mock fallback.
export function useRemoteList<T>(load: () => Promise<Page<T>>) {
  const [state, setState] = useState<ListState<T>>({ status: "loading" });
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const page = await loadRef.current();
      setState({ status: "ready", items: page.items, hasMore: page.has_more });
    } catch (error) {
      setState({ status: "issue", issue: describeError(error) });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { state, reload };
}
