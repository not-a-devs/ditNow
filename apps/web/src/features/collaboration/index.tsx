import { useCallback, useState } from "react";
import type { Issue } from "./api";
import { AnonymousPanel } from "./AnonymousPanel";
import { GroupsPanel } from "./GroupsPanel";
import { MyActivityPanel } from "./MyActivityPanel";
import { AuthIssueContext, IssueBox } from "./ui";

type Tab = "anonymous" | "mine" | "groups";

const TABS: { id: Tab; label: string }[] = [
  { id: "anonymous", label: "익명 검색·댓글" },
  { id: "mine", label: "내 북마크·신고" },
  { id: "groups", label: "스터디·동아리" },
];

// Anonymous-zone and real-name-zone panels never share state or identifiers.
export default function CollaborationFeature() {
  const [tab, setTab] = useState<Tab>("anonymous");
  const [authIssue, setAuthIssue] = useState<Issue | null>(null);
  const [session, setSession] = useState(0);
  const lift = useCallback((issue: Issue) => setAuthIssue(prev => prev ?? issue), []);

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-slate-900">커뮤니티 협업</h1>
      {authIssue ? (
        // Every personal view is unmounted; only this notice remains.
        <IssueBox issue={authIssue} onRetry={() => { setAuthIssue(null); setSession(s => s + 1); }} />
      ) : (
        <AuthIssueContext.Provider value={lift}>
          <div role="tablist" aria-label="협업 영역" className="flex gap-2 border-b border-slate-200">
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`collab-tab-${id}`}
                aria-selected={tab === id}
                aria-controls={`collab-panel-${id}`}
                onClick={() => setTab(id)}
                className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === id ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div key={session} role="tabpanel" id={`collab-panel-${tab}`} aria-labelledby={`collab-tab-${tab}`}>
            {tab === "anonymous" && <AnonymousPanel />}
            {tab === "mine" && <MyActivityPanel />}
            {tab === "groups" && <GroupsPanel />}
          </div>
        </AuthIssueContext.Provider>
      )}
    </main>
  );
}
