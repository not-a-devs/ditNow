import { useCallback, useEffect, useState, type FormEvent } from "react";
import { listDepartmentChannels, listMessages, sendMessage } from "./api";
import {
  MESSAGE_MAX_LENGTH,
  NOTICE_STATUS_LABEL,
  formatDateTime,
  newClientNonce,
  toErrorView,
  validateMessage,
} from "./model";
import { EmptyView, ErrorView, LoadingView } from "./StatusView";
import type { CampusErrorView, Channel, ChatMessage, LoadState } from "./types";

interface Props {
  departmentId: string;
  onOpenNotice: (noticeId: string) => void;
}

export function ChatPanel({ departmentId, onOpenNotice }: Props) {
  const [channels, setChannels] = useState<LoadState<Channel[]>>({ status: "loading" });
  const [selected, setSelected] = useState<string | null>(null);

  const loadChannels = useCallback(() => {
    setChannels({ status: "loading" });
    listDepartmentChannels(departmentId)
      .then((data) => {
        setChannels({ status: "ready", data: data.items });
        setSelected((current) => current ?? data.items[0]?.id ?? null);
      })
      .catch((error: unknown) => setChannels({ status: "error", error: toErrorView(error) }));
  }, [departmentId]);

  useEffect(loadChannels, [loadChannels]);

  if (channels.status === "loading") return <LoadingView label="채널" />;
  if (channels.status === "error") return <ErrorView error={channels.error} onRetry={loadChannels} />;
  if (channels.data.length === 0) return <EmptyView label="참여할 수 있는 학과·학년 채널이 없습니다." />;

  return (
    <div className="flex flex-col gap-3 md:flex-row">
      <nav aria-label="채널 목록" className="flex gap-2 overflow-x-auto md:w-48 md:flex-col">
        {channels.data.map((channel) => (
          <button
            key={channel.id}
            type="button"
            aria-pressed={selected === channel.id}
            onClick={() => setSelected(channel.id)}
            className={`whitespace-nowrap rounded-md px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
              selected === channel.id ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-800 hover:bg-slate-200"
            }`}
          >
            {channel.kind === "DEPARTMENT_ALL" ? "학과 전체" : `${channel.grade}학년`} · {channel.name}
          </button>
        ))}
      </nav>
      {selected && <MessageThread key={selected} channelId={selected} onOpenNotice={onOpenNotice} />}
    </div>
  );
}

function MessageThread({ channelId, onOpenNotice }: { channelId: string; onOpenNotice: Props["onOpenNotice"] }) {
  const [messages, setMessages] = useState<LoadState<ChatMessage[]>>({ status: "loading" });
  const [draft, setDraft] = useState("");
  // Kept across retries so a resend after a network failure is deduplicated by the server.
  const [nonce, setNonce] = useState(newClientNonce);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<CampusErrorView | string | null>(null);

  const load = useCallback(() => {
    setMessages({ status: "loading" });
    listMessages(channelId)
      .then((data) => setMessages({ status: "ready", data: [...data.items].reverse() }))
      .catch((error: unknown) => setMessages({ status: "error", error: toErrorView(error) }));
  }, [channelId]);

  useEffect(load, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = validateMessage(draft);
    if (problem) {
      setSendError(problem);
      return;
    }
    setSending(true);
    setSendError(null);
    try {
      const result = await sendMessage(channelId, draft.trim(), nonce);
      setMessages((current) => {
        if (current.status !== "ready") return current;
        if (current.data.some((m) => m.id === result.message.id)) return current;
        return { status: "ready", data: [...current.data, result.message] };
      });
      setDraft("");
      setNonce(newClientNonce());
    } catch (error) {
      setSendError(toErrorView(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <section aria-label="메시지" className="flex min-w-0 flex-1 flex-col rounded-lg border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-xs text-slate-500">
        <span>실시간 수신 미연결 · 새로고침으로 최신 메시지를 확인하세요.</span>
        <button type="button" onClick={load} className="rounded px-2 py-1 text-blue-700 hover:bg-blue-50">
          새로고침
        </button>
      </div>
      <div className="max-h-[60vh] min-h-48 overflow-y-auto p-3">
        {messages.status === "loading" && <LoadingView label="메시지" />}
        {messages.status === "error" && <ErrorView error={messages.error} onRetry={load} />}
        {messages.status === "ready" && messages.data.length === 0 && <EmptyView label="아직 메시지가 없습니다." />}
        {messages.status === "ready" && (
          <ol className="flex flex-col gap-2">
            {messages.data.map((message) => (
              <li key={message.id} className={message.is_mine ? "self-end" : "self-start"}>
                {message.kind === "NOTICE_CARD" ? (
                  <NoticeCardView message={message} onOpenNotice={onOpenNotice} />
                ) : (
                  <div
                    className={`max-w-[80vw] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm md:max-w-md ${
                      message.is_mine ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-900"
                    }`}
                  >
                    {message.body}
                    <time className="mt-1 block text-[11px] opacity-70" dateTime={message.created_at}>
                      {formatDateTime(message.created_at)}
                    </time>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 border-t border-slate-200 p-3">
        <label htmlFor={`campus-msg-${channelId}`} className="sr-only">
          메시지 입력
        </label>
        <textarea
          id={`campus-msg-${channelId}`}
          value={draft}
          maxLength={MESSAGE_MAX_LENGTH}
          rows={2}
          onChange={(event) => setDraft(event.target.value)}
          className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm focus:border-blue-500 focus:outline-none"
          placeholder="학과 채팅은 실명 공간입니다."
        />
        {sendError && (
          <p role="alert" className="text-sm text-red-700">
            {typeof sendError === "string" ? sendError : `${sendError.title} — ${sendError.detail}`}
          </p>
        )}
        <button
          type="submit"
          disabled={sending || messages.status !== "ready"}
          className="self-end rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {sending ? "전송 중…" : "보내기"}
        </button>
      </form>
    </section>
  );
}

function NoticeCardView({ message, onOpenNotice }: { message: ChatMessage; onOpenNotice: Props["onOpenNotice"] }) {
  if (!message.notice) {
    return (
      <div className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-500">
        볼 수 없는 공지입니다.
      </div>
    );
  }
  const notice = message.notice;
  return (
    <button
      type="button"
      onClick={() => onOpenNotice(notice.notice_id)}
      className="w-full max-w-md rounded-lg border-2 border-emerald-500 bg-emerald-50 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
    >
      <span className="text-xs font-semibold text-emerald-800">
        공식 공지 · {NOTICE_STATUS_LABEL[notice.status]} · 개정 {notice.revision}
      </span>
      <span className="mt-1 block font-medium text-slate-900">{notice.title}</span>
      <span className="mt-1 block text-xs text-emerald-700">원본 보기</span>
    </button>
  );
}
