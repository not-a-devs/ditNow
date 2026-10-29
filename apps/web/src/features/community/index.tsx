import { useState } from "react";
import { AnonymousBoard } from "./AnonymousBoard";
import { RecruitmentBoard } from "./RecruitmentBoard";

type Tab = "anonymous" | "recruitment";

const TABS: { id: Tab; label: string }[] = [
  { id: "anonymous", label: "익명 게시판" },
  { id: "recruitment", label: "실명 모집" },
];

// Anonymous and real-name areas are separate components with separate API calls and state.
export default function CommunityFeature() {
  const [tab, setTab] = useState<Tab>("anonymous");

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-slate-900">커뮤니티</h1>
      <div role="tablist" aria-label="커뮤니티 영역" className="flex gap-2 border-b border-slate-200">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`community-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`community-panel-${id}`}
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === id ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`community-panel-${tab}`} aria-labelledby={`community-tab-${tab}`}>
        {tab === "anonymous" ? <AnonymousBoard /> : <RecruitmentBoard />}
      </div>
    </main>
  );
}
