// FR-DEPT-003/004 first pass: free channels + official-channel request submission.
// Not mounted in the shell; root passes the session's department/grade when wiring it.
// Every decision is made by the server; buttons only reflect the role the server returned.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { formatDateTime, intentAfterFailure, intentFor, isUncertainSendFailure, toErrorView, type PendingSend } from "../campus/model";
import { EmptyView, ErrorView, LoadingView } from "../campus/StatusView";
import type { CampusErrorView } from "../campus/types";
import { channelsApi, validateDescription, validateName, validateReason } from "./api";
import type { FreeChannel, OfficialRequest } from "./types";

export function errorView(error: unknown): CampusErrorView {
  const view = toErrorView(error);
  if (error instanceof ApiError && error.code === "UNAVAILABLE") {
    return { ...view, detail: "자유 채널 API가 아직 인증/DB와 연결되지 않았습니다." };
  }
  if (error instanceof ApiError && error.code === "CONFLICT") {
    return { ...view, detail: "이름 중복·보관·정원·중복 신청 또는 다른 변경과 충돌했습니다. 새로고침 후 확인하세요." };
  }
  return view;
}

const scopeLabel = (channel: FreeChannel) => (channel.grade === null ? "학과 전체" : `${channel.grade}학년`);
const REQUEST_LABEL = { PENDING: "접수됨 · 승인 절차 보류", CANCELLED: "취소됨(채널 보관)" } as const;

function replaceIn(list: FreeChannel[], next: FreeChannel) {
  return list.map((item) => (item.id === next.id ? next : item));
}

const inputClass = "w-full rounded-md border border-slate-300 px-2 py-1 text-sm";
const buttonClass =
  "rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500";

function CreateForm({ departmentId, grade, onCreated }: { departmentId: string; grade: number | null; onCreated: (c: FreeChannel) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [gradeScoped, setGradeScoped] = useState(false);
  const [pending, setPending] = useState<PendingSend | null>(null);
  const [error, setError] = useState<string | CampusErrorView | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const problem = validateName(name) ?? validateDescription(description);
    if (problem) return setError(problem);
    const input = { department_id: departmentId, grade: gradeScoped && grade ? grade : null, name: name.trim(), description: description.trim() };
    // Same payload after an unclear failure reuses the key, so the server replays, not duplicates.
    const intent = intentFor(pending, JSON.stringify(input));
    setPending(intent);
    setBusy(true);
    setError(null);
    try {
      const created = await channelsApi.create(input, intent.nonce);
      setPending(null);
      setUncertain(false);
      setName("");
      setDescription("");
      onCreated(created.channel);
    } catch (failure) {
      setPending(intentAfterFailure(intent, failure));
      setUncertain(isUncertainSendFailure(failure));
      setError(errorView(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-label="자유 채널 만들기" className="space-y-2 rounded-lg border border-slate-200 p-3">
      <label className="block text-sm">
        채널 이름
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="block text-sm">
        설명(선택)
        <textarea className={inputClass} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {grade ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={gradeScoped} onChange={(e) => setGradeScoped(e.target.checked)} />
          {grade}학년만 참여
        </label>
      ) : null}
      {typeof error === "string" && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {error && typeof error !== "string" && <ErrorView error={error} />}
      {uncertain && <p className="text-xs text-amber-800">이전 요청이 이미 처리되었을 수 있습니다. 같은 내용으로 다시 만들면 중복 없이 확인됩니다.</p>}
      <button type="submit" className={buttonClass} disabled={busy}>
        만들기
      </button>
    </form>
  );
}

function OwnerTools({ channel, onChanged, onRequested }: { channel: FreeChannel; onChanged: (c: FreeChannel) => void; onRequested: (r: OfficialRequest) => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(channel.name);
  const [description, setDescription] = useState(channel.description);
  const [reason, setReason] = useState("");
  const [requestIntent, setRequestIntent] = useState<PendingSend | null>(null);
  const [error, setError] = useState<string | CampusErrorView | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (failure) {
      setError(errorView(failure));
    } finally {
      setBusy(false);
    }
  };

  const save = (event: FormEvent) => {
    event.preventDefault();
    const problem = validateName(name) ?? validateDescription(description);
    if (problem) return setError(problem);
    void run(async () => {
      onChanged(await channelsApi.update(channel.id, name.trim(), description.trim(), channel.revision));
      setEditing(false);
    });
  };

  const request = (event: FormEvent) => {
    event.preventDefault();
    const problem = validateReason(reason);
    if (problem) return setError(problem);
    const intent = intentFor(requestIntent, reason.trim());
    setRequestIntent(intent);
    void run(async () => {
      try {
        const created = await channelsApi.requestOfficial(channel.id, intent.body, intent.nonce);
        setRequestIntent(null);
        setReason("");
        onRequested(created.request);
      } catch (failure) {
        setRequestIntent(intentAfterFailure(intent, failure));
        throw failure;
      }
    });
  };

  if (channel.status !== "ACTIVE") return null;
  return (
    <div className="mt-2 space-y-2 border-t border-slate-100 pt-2">
      {editing ? (
        <form onSubmit={save} aria-label="채널 수정" className="space-y-2">
          <input aria-label="새 채널 이름" className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          <textarea aria-label="새 설명" className={inputClass} value={description} onChange={(e) => setDescription(e.target.value)} />
          <button type="submit" className={buttonClass} disabled={busy}>저장</button>
        </form>
      ) : (
        <div className="flex gap-2">
          <button type="button" className={buttonClass} onClick={() => setEditing(true)}>수정</button>
          <button
            type="button"
            className={buttonClass}
            disabled={busy}
            onClick={() => void run(async () => onChanged(await channelsApi.archive(channel.id, channel.revision)))}
          >
            보관
          </button>
        </div>
      )}
      <form onSubmit={request} aria-label="공식 채널 신청" className="space-y-1">
        <textarea aria-label="공식 채널 신청 사유" className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} />
        <button type="submit" className={buttonClass} disabled={busy}>공식 채널 신청</button>
        <p className="text-xs text-slate-500">신청만 접수됩니다. 승인 권한자·공식 배지 정책이 확정되기 전에는 승인되지 않습니다.</p>
      </form>
      {typeof error === "string" && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {error && typeof error !== "string" && <ErrorView error={error} />}
    </div>
  );
}

function ChannelItem({ channel, onChanged, onRequested }: { channel: FreeChannel; onChanged: (c: FreeChannel) => void; onRequested: (r: OfficialRequest) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<CampusErrorView | null>(null);
  const membership = async (action: "join" | "leave") => {
    setBusy(true);
    setError(null);
    try {
      onChanged((await channelsApi[action](channel.id)).channel);
    } catch (failure) {
      setError(errorView(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="rounded-lg border border-slate-200 p-3" aria-label={channel.name}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{channel.name}</span>
        <span className="rounded bg-slate-100 px-1.5 text-xs">자유 채널 · {scopeLabel(channel)}</span>
        {channel.status === "ARCHIVED" && <span className="rounded bg-slate-200 px-1.5 text-xs">보관됨</span>}
        {channel.my_role === "OWNER" && <span className="text-xs text-sky-700">개설자</span>}
        <span className="text-xs text-slate-500">{channel.member_count}명</span>
      </div>
      {channel.description && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{channel.description}</p>}
      <div className="mt-2 flex gap-2">
        {channel.my_role === null && channel.status === "ACTIVE" && (
          <button type="button" className={buttonClass} disabled={busy} onClick={() => void membership("join")}>참여</button>
        )}
        {channel.my_role === "MEMBER" && (
          <button type="button" className={buttonClass} disabled={busy} onClick={() => void membership("leave")}>나가기</button>
        )}
      </div>
      {error && <ErrorView error={error} />}
      {channel.my_role === "OWNER" && <OwnerTools channel={channel} onChanged={onChanged} onRequested={onRequested} />}
    </li>
  );
}

export default function ChannelsPage({ departmentId, grade = null }: { departmentId?: string; grade?: number | null }) {
  const [channels, setChannels] = useState<FreeChannel[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [requests, setRequests] = useState<OfficialRequest[]>([]);
  const [error, setError] = useState<CampusErrorView | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (!departmentId) return;
    const controller = new AbortController();
    setChannels(null);
    setError(null);
    Promise.all([
      channelsApi.listDepartment(departmentId, null, controller.signal),
      channelsApi.myRequests(controller.signal),
    ])
      .then(([page, mine]) => {
        setChannels(page.items);
        setNext(page.next_before);
        setRequests(mine.items);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(errorView(failure));
      });
    return () => controller.abort();
  }, [departmentId, attempt]);

  const changed = useCallback((channel: FreeChannel) => setChannels((list) => (list ? replaceIn(list, channel) : list)), []);
  const created = useCallback((channel: FreeChannel) => setChannels((list) => [channel, ...(list ?? []).filter((c) => c.id !== channel.id)]), []);
  const requested = useCallback((request: OfficialRequest) => setRequests((list) => [request, ...list.filter((r) => r.id !== request.id)]), []);

  const more = async () => {
    if (!departmentId || next === null) return;
    setLoadingMore(true);
    try {
      const page = await channelsApi.listDepartment(departmentId, next);
      setChannels((list) => [...(list ?? []), ...page.items.filter((c) => !(list ?? []).some((x) => x.id === c.id))]);
      setNext(page.next_before);
    } catch (failure) {
      setError(errorView(failure));
    } finally {
      setLoadingMore(false);
    }
  };

  if (!departmentId) {
    return <EmptyView label="소속 학과 정보가 아직 연결되지 않았습니다. 로그인 연동 후 이용할 수 있습니다." />;
  }

  return (
    <section aria-labelledby="free-channels-title" className="space-y-4">
      <h2 id="free-channels-title" className="text-lg font-semibold">학과 자유 채널</h2>
      <p className="rounded-md bg-slate-50 p-2 text-xs text-slate-600">
        학과 전체·학년 기본 채널은 학과 채팅에서 자동으로 제공되며 여기서 수정할 수 없습니다. 자유 채널의 실시간 대화 전송은 아직 연결되지 않았습니다.
      </p>
      {error && <ErrorView error={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {!error && channels === null && <LoadingView label="자유 채널" />}
      {channels !== null && (
        <>
          <CreateForm departmentId={departmentId} grade={grade} onCreated={created} />
          {channels.length === 0 ? (
            <EmptyView label="아직 자유 채널이 없습니다." />
          ) : (
            <ul className="space-y-2">
              {channels.map((channel) => (
                <ChannelItem key={channel.id} channel={channel} onChanged={changed} onRequested={requested} />
              ))}
            </ul>
          )}
          {next !== null && (
            <button type="button" className={buttonClass} disabled={loadingMore} onClick={() => void more()}>
              더 보기
            </button>
          )}
          <section aria-labelledby="official-requests-title">
            <h3 id="official-requests-title" className="font-medium">내 공식 채널 신청</h3>
            {requests.length === 0 ? (
              <EmptyView label="신청 내역이 없습니다." />
            ) : (
              <ul className="space-y-1 text-sm">
                {requests.map((request) => (
                  <li key={request.id}>
                    {REQUEST_LABEL[request.status]} · {formatDateTime(request.created_at)}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
