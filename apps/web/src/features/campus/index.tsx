// TASK-CAMPUS feature entry. The shell (another branch) supplies the server-resolved department.
import { useState } from "react";
import { AcademicPanel } from "./AcademicPanel";
import { ChatPanel } from "./ChatPanel";
import { NoticePanel } from "./NoticePanel";
import { EmptyView } from "./StatusView";

type Tab = "chat" | "notices" | "academic";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "학과·학년 채팅" },
  { id: "notices", label: "공지" },
  { id: "academic", label: "학사 일정" },
];

export interface CampusPageProps {
  /** Current department from the authenticated session; never a user-typed value. */
  departmentId?: string | null;
}

export default function CampusPage({ departmentId = null }: CampusPageProps) {
  const [tab, setTab] = useState<Tab>("chat");
  const [openNoticeId, setOpenNoticeId] = useState<string | null>(null);

  function openNotice(noticeId: string | null) {
    setOpenNoticeId(noticeId);
    if (noticeId) setTab("notices");
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4">
      <h1 className="text-xl font-bold text-slate-900">학과 소통</h1>
      <div role="tablist" aria-label="학과 소통 메뉴" className="flex gap-1 border-b border-slate-200">
        {TABS.map((item) => (
          <button
            key={item.id}
            id={`campus-tab-${item.id}`}
            role="tab"
            type="button"
            aria-selected={tab === item.id}
            aria-controls={`campus-panel-${item.id}`}
            onClick={() => setTab(item.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
              tab === item.id ? "border-blue-600 font-semibold text-blue-700" : "border-transparent text-slate-600"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <section id={`campus-panel-${tab}`} role="tabpanel" aria-labelledby={`campus-tab-${tab}`}>
        {tab === "chat" &&
          (departmentId ? (
            <ChatPanel departmentId={departmentId} onOpenNotice={openNotice} />
          ) : (
            <EmptyView label="소속 학과 정보가 아직 연결되지 않았습니다. 로그인·소속 연동 후 이용할 수 있습니다." />
          ))}
        {tab === "notices" && <NoticePanel openNoticeId={openNoticeId} onOpenNotice={openNotice} />}
        {tab === "academic" && <AcademicPanel />}
      </section>
    </main>
  );
}
