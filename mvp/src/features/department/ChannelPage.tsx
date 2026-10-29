import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { deleteMessage, getChannelWithMessages, sendMessage, type MessageView } from '../../shared/data/api';
import { formatDate, formatTime } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import { Badge, cx, ErrorState, InlineError, LoadingBlock, PageHeader } from '../../shared/ui';
import { MegaphoneIcon, SendIcon, ShieldIcon, TrashIcon } from '../../shared/ui/icons';

function NoticeCard({ m }: { m: MessageView }) {
  const c = m.card;
  if (!c) return null;
  const unavailable = c.status !== 'published';
  return (
    <div className="mx-auto w-full max-w-md">
      <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-2 ring-brand-200">
        <div className="flex items-center gap-2 bg-brand-600 px-4 py-2 text-white">
          <ShieldIcon className="h-4 w-4" />
          <span className="text-xs font-bold">공식 공지</span>
          <span className="ml-auto text-[11px] text-white/80">{formatTime(m.createdAt)}</span>
        </div>
        <div className="p-4">
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="brand">{c.category}</Badge>
            <Badge tone="navy">{c.audience}</Badge>
            {c.currentRevision > c.deliveredRevision && !unavailable && <Badge tone="sky">수정됨 · 최신판 보기</Badge>}
          </div>
          <p className={cx('mt-2 font-semibold', unavailable ? 'text-navy-400 line-through' : 'text-navy-900')}>{c.title}</p>
          <p className="mt-1 text-xs text-navy-500">작성: {c.authorRole}</p>
          {unavailable ? (
            <p className="mt-3 rounded-xl bg-navy-50 px-3 py-2 text-xs text-navy-500">
              {c.status === 'deleted' ? '작성자가 삭제한 공지입니다.' : '게시가 종료된 공지입니다.'}
            </p>
          ) : (
            <Link to={`/app/notices/${c.noticeId}`} className="mt-3 flex min-h-[40px] items-center justify-center rounded-xl bg-brand-50 text-sm font-semibold text-brand-700 hover:bg-brand-100">
              원문 보기
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function TextMessage({ m, onDelete }: { m: MessageView; onDelete: (id: string) => void }) {
  return (
    <div className={cx('group flex gap-2', m.isMine && 'flex-row-reverse')}>
      {!m.isMine && (
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-navy-100 text-xs font-bold text-navy-600" aria-hidden>
          {m.senderName.slice(0, 1)}
        </span>
      )}
      <div className={cx('max-w-[78%]', m.isMine && 'text-right')}>
        {!m.isMine && (
          <p className="mb-0.5 text-xs font-semibold text-navy-600">
            {m.senderName} {m.senderRole !== '학생' && <span className="text-brand-600">{m.senderRole}</span>}
          </p>
        )}
        <div className={cx('flex items-end gap-1.5', m.isMine && 'flex-row-reverse')}>
          <p
            className={cx(
              'whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-left text-[15px]',
              m.deleted ? 'bg-navy-50 italic text-navy-400' : m.isMine ? 'rounded-tr-sm bg-brand-600 text-white' : 'rounded-tl-sm bg-white text-navy-900 ring-1 ring-navy-100',
            )}
          >
            {m.deleted ? '삭제된 메시지입니다' : m.text}
          </p>
          <span className="shrink-0 text-[10px] text-navy-400">{formatTime(m.createdAt)}</span>
          {m.isMine && !m.deleted && (
            <button
              onClick={() => onDelete(m.id)}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-navy-300 opacity-100 hover:bg-navy-50 hover:text-brand-600 lg:opacity-0 lg:group-hover:opacity-100"
              aria-label="메시지 삭제"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function ChannelPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getChannelWithMessages(id), [id]);
  const [draft, setDraft] = useState('');
  const nonce = useRef(crypto.randomUUID());
  const send = useMutation(sendMessage);
  const del = useMutation(deleteMessage);
  const bottomRef = useRef<HTMLDivElement>(null);
  const count = data?.messages.length ?? 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [count]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!draft.trim()) return;
    // 실패 후 재전송해도 같은 nonce → 서버가 중복 저장하지 않음
    const ok = await send.mutate(id, draft, nonce.current);
    if (ok) {
      setDraft('');
      nonce.current = crypto.randomUUID();
    }
  };

  if (loading && !data) return <LoadingBlock rows={5} />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  let lastDay = '';
  return (
    <div className="flex h-[calc(100dvh-210px)] flex-col lg:h-[calc(100dvh-140px)]">
      <PageHeader
        back="/app/department"
        title={data.channel.name}
        subtitle={
          <span className="inline-flex items-center gap-1.5">
            {data.channel.official ? <Badge tone="brand">기본 채널</Badge> : <Badge tone="gray">자유 채널</Badge>}
            <span className="truncate">{data.channel.description}</span>
          </span>
        }
      />
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-2xl bg-navy-50/70 p-3 ring-1 ring-navy-100 sm:p-4" aria-live="polite">
        {data.hasMore && <p className="text-center text-xs text-navy-400">이전 메시지는 최근 50개까지만 표시됩니다.</p>}
        {data.messages.length === 0 && <p className="py-10 text-center text-sm text-navy-400">첫 메시지를 남겨 보세요.</p>}
        {data.messages.map((m) => {
          const day = formatDate(m.createdAt);
          const divider = day !== lastDay;
          lastDay = day;
          return (
            <div key={m.id}>
              {divider && <p className="my-2 text-center text-[11px] font-semibold text-navy-400">{day}</p>}
              {m.kind === 'notice_card' ? <NoticeCard m={m} /> : <TextMessage m={m} onDelete={(mid) => del.mutate(mid)} />}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
      <div className="pt-3">
        <InlineError error={send.error ?? del.error} />
        <form onSubmit={submit} className="mt-2 flex items-end gap-2">
          <label htmlFor="msg" className="sr-only">메시지</label>
          <textarea
            id="msg"
            rows={1}
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="메시지를 입력하세요 (Shift+Enter 줄바꿈)"
            className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border-0 bg-white px-3 py-2.5 text-[15px] ring-1 ring-inset ring-navy-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            type="submit"
            disabled={send.pending || !draft.trim()}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-600 text-white disabled:bg-brand-300"
            aria-label="보내기"
          >
            <SendIcon className="h-5 w-5" />
          </button>
        </form>
        <p className="mt-1.5 flex items-center gap-1 text-[11px] text-navy-400">
          <MegaphoneIcon className="h-3.5 w-3.5" /> 빨간 카드는 조교·교수가 게시한 공식 공지이며, 일반 대화와 구분됩니다.
        </p>
      </div>
    </div>
  );
}
