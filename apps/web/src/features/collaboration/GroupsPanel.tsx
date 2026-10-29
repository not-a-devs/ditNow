import { useMemo, useState, type FormEvent } from "react";
import { collaborationApi, createKeyTracker, type Issue } from "./api";
import { safeLink } from "./guards";
import type { Group, GroupInput, GroupKind } from "./types";
import { InlineIssue, RemoteView, button, field, formatTime, primary, useIssueHandler, useRemote } from "./ui";

const KIND_LABEL: Record<GroupKind, string> = { study: "스터디", club: "동아리" };
const EMPTY_INPUT: GroupInput = { kind: "study", name: "", description: "", join_mode: "approval", capacity: 5 };

// FR-COM-006/007: virtual study/club groups and their members-only activity space (real name).
export function GroupsPanel() {
  const [kind, setKind] = useState<GroupKind | "">("");
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const { state, reload } = useRemote(signal => collaborationApi.listGroups(kind || undefined, undefined, signal),`${kind}:${version}`);

  return (
    <div className="space-y-6">
      <section aria-labelledby="group-list" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 id="group-list" className="text-lg font-semibold">스터디·동아리</h2>
          <label className="text-sm">
            <span className="sr-only">종류</span>
            <select className="rounded-md border border-slate-300 px-2 py-1" value={kind} onChange={e => setKind(e.target.value as GroupKind | "")}>
              <option value="">전체</option>
              <option value="study">스터디</option>
              <option value="club">동아리</option>
            </select>
          </label>
        </div>
        <p className="text-xs text-slate-500">가입·정원 규칙은 시연용 기본값이며 학교 동아리 규정이 아닙니다.</p>
        <RemoteView remote={state} label="모임" isEmpty={p => p.items.length === 0} onRetry={reload}>
          {page => (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
              {page.items.map(group => (
                <li key={group.id} className="flex items-center justify-between gap-2 p-3 text-sm">
                  <span>
                    <span className="font-medium">{group.name}</span>{" "}
                    <span className="text-slate-500">{KIND_LABEL[group.kind]} · {group.member_count}/{group.capacity}명 · 모임장 {group.leader.display_name ?? "이름 비공개"}</span>
                  </span>
                  <button type="button" className={button} onClick={() => setSelected(group.id)}>열기</button>
                </li>
              ))}
            </ul>
          )}
        </RemoteView>
      </section>
      <CreateGroup onCreated={id => { setVersion(v => v + 1); setSelected(id); }} />
      {selected && <GroupDetail key={selected} groupId={selected} onChanged={() => setVersion(v => v + 1)} />}
    </div>
  );
}

function CreateGroup({ onCreated }: { onCreated: (id: string) => void }) {
  const [input, setInput] = useState<GroupInput>(EMPTY_INPUT);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const keys = useMemo(() => createKeyTracker(), []);
  const handle = useIssueHandler();
  const set = <K extends keyof GroupInput>(key: K, value: GroupInput[K]) => setInput(prev => ({ ...prev, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = { ...input, name: input.name.trim(), description: input.description.trim() };
    if (body.name.length < 2 || body.name.length > 60 || !Number.isInteger(body.capacity) || body.capacity < 2 || body.capacity > 30) {
      setIssue({ kind: "error", message: "이름은 2~60자, 정원은 2~30명(모임장 포함)으로 입력하세요." });
      return;
    }
    setBusy(true);
    setIssue(null);
    try {
      const group = await collaborationApi.createGroup(body, keys.keyFor(body));
      keys.reset();
      setInput(EMPTY_INPUT);
      onCreated(group.id);
    } catch (error) {
      setIssue(handle(error)); // the form keeps its values and the same key for a retry
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-labelledby="group-create" className="space-y-2 rounded-lg border border-slate-200 p-3">
      <h2 id="group-create" className="font-semibold">가상 모임 개설</h2>
      <label className="block text-sm">이름<input className={field} value={input.name} onChange={e => set("name", e.target.value)} /></label>
      <label className="block text-sm">소개<textarea className={field} rows={2} value={input.description} onChange={e => set("description", e.target.value)} /></label>
      <div className="flex flex-wrap gap-3 text-sm">
        <label>종류{" "}
          <select value={input.kind} onChange={e => set("kind", e.target.value as GroupKind)} className="rounded-md border border-slate-300 px-2 py-1">
            <option value="study">스터디</option><option value="club">동아리</option>
          </select>
        </label>
        <label>가입 방식{" "}
          <select value={input.join_mode} onChange={e => set("join_mode", e.target.value as GroupInput["join_mode"])} className="rounded-md border border-slate-300 px-2 py-1">
            <option value="approval">모임장 승인</option><option value="open">바로 참여</option>
          </select>
        </label>
        <label>정원{" "}
          <input type="number" min={2} max={30} value={input.capacity} onChange={e => set("capacity", Number(e.target.value))} className="w-20 rounded-md border border-slate-300 px-2 py-1" />
        </label>
      </div>
      <button type="submit" className={primary} disabled={busy}>개설 요청</button>
      <InlineIssue issue={issue} />
    </form>
  );
}

function SourceLabel({ group }: { group: Group }) {
  const { kind, url, checked_at } = group.source;
  const link = kind === "OFFICIAL_PUBLIC" ? safeLink(url) : null;
  if (kind === "OFFICIAL_PUBLIC" && link && checked_at)
    return <p className="text-xs">공개 출처: <a className="underline" href={link} target="_blank" rel="noopener noreferrer">원문</a> · 확인 {formatTime(checked_at)} · 이 앱에서는 안내만 제공</p>;
  if (kind === "DEMO") return <p className="text-xs">가상 시연 데이터</p>;
  if (kind === "USER_DEMO") return <p className="text-xs">학생이 만든 가상 모임 · 학교 공인 단체 아님</p>;
  return <p className="text-xs">출처 확인 필요</p>;
}

function GroupDetail({ groupId, onChanged }: { groupId: string; onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const { state, reload } = useRemote(signal => collaborationApi.getGroup(groupId, signal),`${groupId}:${version}`);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const keys = useMemo(() => createKeyTracker(), []);
  const handle = useIssueHandler();
  const refresh = () => { setVersion(v => v + 1); onChanged(); };

  const act = async (run: () => Promise<unknown>, onSuccess?: () => void) => {
    setBusy(true);
    setIssue(null);
    try {
      await run();
      onSuccess?.();
      refresh();
    } catch (error) {
      setIssue(handle(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <RemoteView remote={state} label="모임 정보" isEmpty={() => false} onRetry={reload}>
      {group => {
        const mine = group.my_membership;
        const member = mine?.status === "active";
        const canJoin = !mine || mine.status === "left";
        return (
          <article aria-label="모임 상세" className="space-y-3 rounded-lg border border-slate-200 p-3">
            <h3 className="font-semibold">{group.name}</h3>
            {group.description && <p className="whitespace-pre-wrap text-sm">{group.description}</p>}
            <SourceLabel group={group} />
            <p className="text-sm text-slate-600">{group.member_count}/{group.capacity}명 · {group.join_mode === "open" ? "바로 참여" : "모임장 승인"}{mine ? ` · 내 상태: ${mine.status === "active" ? "참여 중" : mine.status === "pending" ? "승인 대기" : mine.status === "rejected" ? "거절됨" : "탈퇴함"}` : ""}</p>
            <div className="flex gap-2">
              {canJoin && (
                <button type="button" className={primary} disabled={busy} onClick={() => act(() => collaborationApi.requestJoin(group.id, keys.keyFor({ join: group.id })), keys.reset)}>
                  참여 요청
                </button>
              )}
              {mine && mine.role === "member" && (mine.status === "active" || mine.status === "pending") && (
                <button type="button" className={button} disabled={busy} onClick={() => act(() => collaborationApi.leaveGroup(group.id, mine.revision))}>
                  {mine.status === "pending" ? "요청 취소" : "탈퇴"}
                </button>
              )}
            </div>
            <InlineIssue issue={issue} />
            {member && mine?.role === "leader" && <JoinRequests groupId={group.id} onDecided={refresh} />}
            {member && <Space groupId={group.id} />}
          </article>
        );
      }}
    </RemoteView>
  );
}

function JoinRequests({ groupId, onDecided }: { groupId: string; onDecided: () => void }) {
  const { state, reload } = useRemote(signal => collaborationApi.listJoinRequests(groupId, signal),groupId);
  const [issue, setIssue] = useState<Issue | null>(null);
  const handle = useIssueHandler();
  const decide = async (id: string, decision: "approve" | "reject", revision: number) => {
    setIssue(null);
    try {
      await collaborationApi.decideJoin(groupId, id, decision, revision);
      onDecided();
      void reload();
    } catch (error) {
      setIssue(handle(error));
    }
  };
  return (
    <section aria-label="참여 요청" className="space-y-2">
      <h4 className="text-sm font-semibold">참여 요청</h4>
      <RemoteView remote={state} label="참여 요청" isEmpty={p => p.items.length === 0} onRetry={reload}>
        {page => (
          <ul className="space-y-1 text-sm">
            {page.items.map(req => (
              <li key={req.id} className="flex items-center gap-2">
                <span>{req.applicant.display_name ?? "이름 비공개"}</span>
                <button type="button" className={button} onClick={() => decide(req.id, "approve", req.revision)}>승인</button>
                <button type="button" className={button} onClick={() => decide(req.id, "reject", req.revision)}>거절</button>
              </li>
            ))}
          </ul>
        )}
      </RemoteView>
      <InlineIssue issue={issue} />
    </section>
  );
}

function Space({ groupId }: { groupId: string }) {
  const [version, setVersion] = useState(0);
  const { state, reload } = useRemote(signal => collaborationApi.listSpacePosts(groupId, signal),`${groupId}:${version}`);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const keys = useMemo(() => createKeyTracker(), []);
  const handle = useIssueHandler();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = body.trim();
    if (!text || text.length > 2000) {
      setIssue({ kind: "error", message: "활동 기록은 1~2000자로 입력하세요." });
      return;
    }
    setBusy(true);
    setIssue(null);
    try {
      await collaborationApi.createSpacePost(groupId, text, keys.keyFor({ groupId, text }));
      keys.reset();
      setBody("");
      setVersion(v => v + 1);
    } catch (error) {
      setIssue(handle(error));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (postId: string, revision: number) => {
    setIssue(null);
    try {
      await collaborationApi.deleteSpacePost(groupId, postId, revision);
      setVersion(v => v + 1);
    } catch (error) {
      setIssue(handle(error));
    }
  };

  return (
    <section aria-label="팀 활동 공간" className="space-y-2">
      <h4 className="text-sm font-semibold">팀 활동 공간 (참여자 전용, 실시간 아님)</h4>
      <RemoteView remote={state} label="활동 기록" isEmpty={p => p.items.length === 0} onRetry={reload}>
        {page => (
          <ul className="space-y-2">
            {page.items.map(post => (
              <li key={post.id} className="rounded-md bg-slate-50 p-2 text-sm">
                <p className="whitespace-pre-wrap">{post.body}</p>
                <p className="text-xs text-slate-500">{post.author.display_name ?? "이름 비공개"} · {formatTime(post.created_at)}</p>
                {post.is_mine && <button type="button" className={button} onClick={() => remove(post.id, post.revision)}>내 기록 삭제</button>}
              </li>
            ))}
          </ul>
        )}
      </RemoteView>
      <form onSubmit={submit} className="space-y-2">
        <label className="block text-sm" htmlFor={`space-${groupId}`}>활동 기록</label>
        <textarea id={`space-${groupId}`} className={field} rows={2} value={body} onChange={e => setBody(e.target.value)} />
        <button type="submit" className={primary} disabled={busy || state.status !== "ready"}>기록 등록 요청</button>
        <InlineIssue issue={issue} />
      </form>
    </section>
  );
}
