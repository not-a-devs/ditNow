import { useState, type FormEvent } from "react";
import { communityApi, describeError, type IssueInfo } from "./api";
import { EmptyPanel, InlineIssue, LoadingPanel, StatusPanel } from "./StatusPanel";
import { LIMITS, type Recruitment, type RecruitmentInput } from "./types";
import { useRemoteList } from "./useRemoteList";

// FR-COM-004. Real-name recruitment, shown with the allowed activity profile name only.
// Capacity counts the recruiter. Applications (FR-COM-005, P1) are not offered here.

const STATUS_LABEL: Record<Recruitment["status"], string> = {
  open: "모집 중",
  closed: "마감",
  cancelled: "취소",
};

interface Draft {
  title: string;
  body: string;
  field: string;
  roles: string;
  capacity: string;
  deadline: string;
}

const EMPTY: Draft = { title: "", body: "", field: "", roles: "", capacity: "3", deadline: "" };

export function parseRecruitment(draft: Draft, now = new Date()): RecruitmentInput | string {
  const title = draft.title.trim();
  const body = draft.body.trim();
  const field = draft.field.trim();
  const roles = draft.roles
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean);
  const capacity = Number(draft.capacity);
  const deadline = new Date(draft.deadline);
  if (title.length < LIMITS.titleMin || title.length > LIMITS.titleMax)
    return `제목은 ${LIMITS.titleMin}~${LIMITS.titleMax}자로 입력하세요.`;
  if (body.length < 1 || body.length > LIMITS.bodyMax)
    return `설명은 1~${LIMITS.bodyMax}자로 입력하세요.`;
  if (field.length < 1 || field.length > LIMITS.fieldMax) return "분야를 입력하세요.";
  if (roles.length < 1 || roles.length > LIMITS.rolesMax)
    return `모집 역할을 1~${LIMITS.rolesMax}개 입력하세요.`;
  if (roles.some((role) => role.length > LIMITS.roleMax))
    return `역할 이름은 ${LIMITS.roleMax}자 이하입니다.`;
  if (new Set(roles.map((role) => role.toLowerCase())).size !== roles.length)
    return "모집 역할이 중복되었습니다.";
  if (!Number.isInteger(capacity) || capacity < LIMITS.capacityMin || capacity > LIMITS.capacityMax)
    return `총 인원(모집자 포함)은 ${LIMITS.capacityMin}~${LIMITS.capacityMax}명입니다.`;
  if (Number.isNaN(deadline.getTime()) || deadline <= now)
    return "마감 일시는 현재 이후여야 합니다.";
  return { title, body, field, roles, capacity, deadline_at: deadline.toISOString() };
}

export function RecruitmentBoard() {
  const { state, reload } = useRemoteList(communityApi.listRecruitments);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [issue, setIssue] = useState<IssueInfo | null>(null);

  const set = (key: keyof Draft) => (value: string) => setDraft((d) => ({ ...d, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseRecruitment(draft);
    setIssue(null);
    if (typeof parsed === "string") {
      setFormError(parsed);
      return;
    }
    setFormError(null);
    setPending(true);
    try {
      await communityApi.createRecruitment(parsed);
      setDraft(EMPTY);
      await reload();
    } catch (error) {
      setIssue(describeError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="recruit-heading" className="space-y-4">
      <header>
        <h2 id="recruit-heading" className="text-lg font-semibold text-slate-900">
          실명 팀원 모집
        </h2>
        <p className="text-sm text-slate-600">
          모집글은 활동 프로필 이름으로 표시됩니다. 익명 게시글과 연결되지 않습니다.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-2 rounded-lg border border-slate-200 p-4 sm:grid-cols-2">
        <Field label="제목" value={draft.title} onChange={set("title")} max={LIMITS.titleMax} />
        <Field label="분야" value={draft.field} onChange={set("field")} max={LIMITS.fieldMax} />
        <Field label="모집 역할 (쉼표로 구분)" value={draft.roles} onChange={set("roles")} />
        <Field
          label="총 인원 (모집자 포함)"
          type="number"
          value={draft.capacity}
          onChange={set("capacity")}
        />
        <Field
          label="마감 일시"
          type="datetime-local"
          value={draft.deadline}
          onChange={set("deadline")}
        />
        <label className="block text-sm font-medium text-slate-700 sm:col-span-2">
          설명
          <textarea
            value={draft.body}
            onChange={(e) => set("body")(e.target.value)}
            maxLength={LIMITS.bodyMax}
            rows={3}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <div className="space-y-2 sm:col-span-2">
          {formError && (
            <p role="alert" className="text-sm text-red-700">
              {formError}
            </p>
          )}
          <InlineIssue issue={issue} />
          <button
            type="submit"
            disabled={pending || state.status !== "ready"}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "서버에 요청 중…" : "모집글 등록 요청"}
          </button>
        </div>
      </form>

      {state.status === "loading" && <LoadingPanel label="모집글" />}
      {state.status === "issue" && <StatusPanel issue={state.issue} onRetry={reload} />}
      {state.status === "ready" && state.items.length === 0 && <EmptyPanel label="모집글" />}
      {state.status === "ready" && state.items.length > 0 && (
        <ul className="space-y-3">
          {state.items.map((item) => (
            <RecruitmentItem key={item.id} item={item} onChanged={reload} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Field(props: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  max?: number;
}) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      {props.label}
      <input
        type={props.type ?? "text"}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        maxLength={props.max}
        min={props.type === "number" ? LIMITS.capacityMin : undefined}
        max={props.type === "number" ? LIMITS.capacityMax : undefined}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
      />
    </label>
  );
}

function RecruitmentItem({
  item,
  onChanged,
}: {
  item: Recruitment;
  onChanged: () => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [issue, setIssue] = useState<IssueInfo | null>(null);

  async function close() {
    if (!window.confirm("모집을 마감할까요? 마감 후에는 다시 열 수 없습니다.")) return;
    setPending(true);
    setIssue(null);
    try {
      await communityApi.closeRecruitment(item.id, item.revision);
      await onChanged();
    } catch (error) {
      setIssue(describeError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <li className="rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{item.owner.display_name ?? "프로필 비공개"}</span>
        <span className={item.status === "open" ? "text-emerald-700" : "text-slate-500"}>
          {STATUS_LABEL[item.status]}
        </span>
      </div>
      <h3 className="mt-1 font-medium text-slate-900">{item.title}</h3>
      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{item.body}</p>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-slate-600">
        <dt>분야</dt>
        <dd>{item.field}</dd>
        <dt>역할</dt>
        <dd>{item.roles.join(", ")}</dd>
        <dt>인원</dt>
        <dd>
          {1 + item.accepted_count} / {item.capacity}명
        </dd>
        <dt>마감</dt>
        <dd>
          <time dateTime={item.deadline_at}>
            {new Date(item.deadline_at).toLocaleString("ko-KR")}
          </time>
        </dd>
      </dl>
      <InlineIssue issue={issue} />
      {item.is_mine && item.status === "open" && (
        <button
          type="button"
          disabled={pending}
          onClick={close}
          className="mt-3 text-xs text-red-700 underline"
        >
          모집 마감
        </button>
      )}
    </li>
  );
}
