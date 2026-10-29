import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { addAnonComment, createAnonPost, deleteAnonComment, deleteAnonPost, getAnonPost, updateAnonPost } from '../../shared/data/api';
import { formatDateTime, timeAgo } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import { Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, InlineError, Input, LoadingBlock, PageHeader, Textarea } from '../../shared/ui';
import { useToast } from '../../shared/ui/toast';

export function AnonPostDetailPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getAnonPost(id), [id]);
  const [comment, setComment] = useState('');
  const [confirm, setConfirm] = useState(false);
  const add = useMutation(addAnonComment);
  const delComment = useMutation(deleteAnonComment);
  const del = useMutation(deleteAnonPost);
  const navigate = useNavigate();
  const toast = useToast();

  if (loading && !data) return <LoadingBlock rows={3} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const { post, comments } = data;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/app/community" title={post.title} />
      <Card>
        <div className="flex items-center gap-2 text-xs text-navy-500">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-navy-100 font-bold text-navy-500" aria-hidden>?</span>
          <span className="font-semibold text-navy-700">익명</span>
          <span>{formatDateTime(post.createdAt)}</span>
          {post.updatedAt !== post.createdAt && <span>(수정됨)</span>}
        </div>
        <p className="mt-4 whitespace-pre-wrap break-words text-[15px] leading-7 text-navy-900">{post.body}</p>
        {post.isMine && (
          <div className="mt-5 flex gap-2 border-t border-navy-100 pt-4">
            <Link to={`/app/community/anonymous/${post.id}/edit`} className="inline-flex min-h-[36px] items-center rounded-xl px-3 text-xs font-semibold text-navy-700 ring-1 ring-inset ring-navy-200 hover:bg-navy-50">수정</Link>
            <Button size="sm" variant="danger" onClick={() => setConfirm(true)}>삭제</Button>
          </div>
        )}
      </Card>

      <section className="mt-6">
        <h2 className="mb-3 font-bold text-navy-900">댓글 {comments.length}</h2>
        <InlineError error={delComment.error} />
        {comments.length === 0 ? (
          <p className="rounded-2xl bg-white px-4 py-6 text-center text-sm text-navy-400 ring-1 ring-navy-100">첫 댓글을 남겨 보세요.</p>
        ) : (
          <Card className="divide-y divide-navy-100 p-0 sm:p-0">
            {comments.map((c) => (
              <div key={c.id} className="px-4 py-3">
                <div className="flex items-center gap-2 text-xs">
                  <span className={c.alias === '글쓴이' ? 'font-bold text-brand-600' : 'font-semibold text-navy-700'}>{c.alias}</span>
                  <span className="text-navy-400">{timeAgo(c.createdAt)}</span>
                  {c.isMine && (
                    <button className="ml-auto min-h-[32px] px-2 text-navy-400 hover:text-brand-600" onClick={() => delComment.mutate(c.id)}>삭제</button>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm text-navy-900">{c.body}</p>
              </div>
            ))}
          </Card>
        )}
        <form
          className="mt-3 flex items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await add.mutate(post.id, comment)) setComment('');
          }}
        >
          <label htmlFor="comment" className="sr-only">댓글</label>
          <Textarea id="comment" className="min-h-[44px]" rows={1} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="익명으로 댓글 달기" />
          <Button type="submit" loading={add.pending} disabled={!comment.trim()}>등록</Button>
        </form>
        <div className="mt-2"><InlineError error={add.error} /></div>
      </section>

      <ConfirmDialog
        open={confirm}
        danger
        title="글을 삭제할까요?"
        description="삭제한 글은 목록과 검색에서 사라지며 되돌릴 수 없습니다."
        confirmLabel="삭제"
        loading={del.pending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          if (await del.mutate(post.id)) {
            toast('글을 삭제했어요');
            navigate('/app/community', { replace: true });
          } else setConfirm(false);
        }}
      />
      {del.error && <div className="mt-3"><InlineError error={del.error} /></div>}
    </div>
  );
}

function PostForm({ initial, postId }: { initial: { title: string; body: string }; postId?: string }) {
  const [form, setForm] = useState(initial);
  const create = useMutation(createAnonPost);
  const update = useMutation(updateAnonPost);
  const m = postId ? update : create;
  const navigate = useNavigate();
  const toast = useToast();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const res = postId ? await update.mutate(postId, form) : await create.mutate(form);
    if (!res) return;
    toast(postId ? '수정했어요' : '익명으로 게시했어요');
    navigate(`/app/community/anonymous/${res.id}`, { replace: true });
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Card className="space-y-4">
        <Field label="제목" htmlFor="title" error={m.fieldErrors.title} counter={{ value: form.title, max: 120 }}>
          <Input id="title" value={form.title} invalid={!!m.fieldErrors.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <Field label="본문" htmlFor="body" error={m.fieldErrors.body} counter={{ value: form.body, max: 5000 }}>
          <Textarea id="body" rows={10} value={form.body} invalid={!!m.fieldErrors.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </Field>
      </Card>
      <p className="rounded-xl bg-navy-50 px-3 py-2 text-xs text-navy-600">
        이 글은 <b>익명</b>으로 게시됩니다. 다른 학생에게 이름·학과가 보이지 않으며, 게시 후 실명으로 전환할 수 없습니다. 운영 정책 위반 신고 시 관리자만 제한된 절차로 확인할 수 있습니다.
      </p>
      <InlineError error={m.error && !m.error.fieldErrors ? m.error : null} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => navigate(-1)}>취소</Button>
        <Button type="submit" loading={m.pending}>{postId ? '수정 저장' : '익명으로 게시'}</Button>
      </div>
    </form>
  );
}

export function AnonPostNewPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/app/community" title="익명 글쓰기" />
      <PostForm initial={{ title: '', body: '' }} />
    </div>
  );
}

export function AnonPostEditPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getAnonPost(id), [id]);
  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  if (!data.post.isMine) return <EmptyState title="작성자만 수정할 수 있습니다" />;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back={`/app/community/anonymous/${id}`} title="익명 글 수정" />
      <PostForm key={id} postId={id} initial={{ title: data.post.title, body: data.post.body }} />
    </div>
  );
}
