import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../app/auth';
import {
  createNotice,
  deleteNotice,
  getNotice,
  listManagedNotices,
  NOTICE_CATEGORIES,
  setNoticeArchived,
  updateNotice,
  type NoticeInput,
  type NoticeView,
} from '../../shared/data/api';
import { timeAgo } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import type { AudienceType, NoticeCategory } from '../../shared/types';
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, InlineError, Input, LoadingBlock, PageHeader, Select, Textarea } from '../../shared/ui';
import { PlusIcon } from '../../shared/ui/icons';
import { useToast } from '../../shared/ui/toast';

export function StaffNoticesPage() {
  const { data, error, loading, reload } = useApi(listManagedNotices, []);
  const [target, setTarget] = useState<NoticeView | null>(null);
  const del = useMutation(deleteNotice);
  const archive = useMutation(setNoticeArchived);
  const toast = useToast();

  return (
    <div>
      <PageHeader
        title="공지 관리"
        subtitle="공지를 게시하면 대상 학과·학년 채팅에 공식 카드가 자동으로 전달됩니다."
        action={
          <Link to="/staff/notices/new" className="inline-flex min-h-[44px] items-center gap-1 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            <PlusIcon className="h-4 w-4" /> 새 공지
          </Link>
        }
      />
      <InlineError error={del.error ?? archive.error} />
      {loading && !data ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data!.length === 0 ? (
        <EmptyState title="작성한 공지가 없습니다" description="첫 공지를 작성해 학생들에게 바로 전달해 보세요." />
      ) : (
        <div className="space-y-3">
          {data!.map((n) => (
            <Card key={n.id}>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="navy">{n.category}</Badge>
                <Badge tone="gray">{n.audience}</Badge>
                {n.important && <Badge tone="brand">중요</Badge>}
                {n.status === 'archived' ? <Badge tone="gray">게시 종료</Badge> : <Badge tone="green">게시 중</Badge>}
                {n.revision > 1 && <Badge tone="sky">제{n.revision}판</Badge>}
                <span className="ml-auto text-xs text-navy-400">{timeAgo(n.updatedAt)}</span>
              </div>
              <Link to={`/app/notices/${n.id}`} className="mt-2 block font-semibold text-navy-900 hover:text-brand-700">{n.title}</Link>
              <p className="mt-1 text-xs text-navy-500">
                {n.deliveredChannels.length > 0 ? `전달 채널: ${n.deliveredChannels.join(', ')}` : '채팅 자동 전달 없음 (학교 전체 공지)'}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link to={`/staff/notices/${n.id}/edit`} className="inline-flex min-h-[36px] items-center rounded-xl px-3 text-xs font-semibold text-navy-700 ring-1 ring-inset ring-navy-200 hover:bg-navy-50">수정</Link>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={archive.pending}
                  onClick={async () => {
                    if ((await archive.mutate(n.id, n.status !== 'archived')) !== undefined) toast(n.status === 'archived' ? '다시 게시했어요' : '게시를 종료했어요');
                  }}
                >
                  {n.status === 'archived' ? '다시 게시' : '게시 종료'}
                </Button>
                <Button size="sm" variant="danger" onClick={() => setTarget(n)}>삭제</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={!!target}
        danger
        title="공지를 삭제할까요?"
        description="삭제 후에도 채팅에 전달된 카드는 남지만 '삭제된 공지'로 표시되고 원문은 열리지 않습니다."
        confirmLabel="삭제"
        loading={del.pending}
        onCancel={() => setTarget(null)}
        onConfirm={async () => {
          if (!target) return;
          if ((await del.mutate(target.id)) !== undefined) toast('공지를 삭제했어요');
          setTarget(null);
        }}
      />
    </div>
  );
}

const emptyInput: NoticeInput = { audienceType: 'department_year', academicYear: 2, category: '일반', title: '', body: '', important: false };

function NoticeForm({ initial, editingId }: { initial: NoticeInput; editingId?: string }) {
  const { user } = useAuth();
  const [form, setForm] = useState<NoticeInput>(initial);
  const [renotify, setRenotify] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const create = useMutation(createNotice);
  const update = useMutation(updateNotice);
  const m = editingId ? update : create;
  const fe = m.fieldErrors;
  const set = <K extends keyof NoticeInput>(k: K, v: NoticeInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const res = editingId ? await update.mutate(editingId, form, renotify) : await create.mutate(form);
    if (!res) return;
    toast(res.delivered > 0 ? `게시 완료 · 채널 ${res.delivered}곳에 공식 카드 전달` : editingId ? '수정 완료 · 기존 카드는 최신판을 보여줍니다' : '게시 완료');
    navigate('/staff/notices');
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Card className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="게시 대상" htmlFor="aud" error={fe.audienceType} hint={editingId ? '게시 후에는 대상을 바꿀 수 없습니다.' : undefined}>
            <Select id="aud" value={form.audienceType} disabled={!!editingId} onChange={(e) => set('audienceType', e.target.value as AudienceType)}>
              <option value="department">{user?.departmentName} 전체</option>
              <option value="department_year">{user?.departmentName} 특정 학년</option>
              {user?.role === 'admin' && <option value="all">학교 전체</option>}
            </Select>
          </Field>
          {form.audienceType === 'department_year' && (
            <Field label="학년" htmlFor="year" error={fe.academicYear}>
              <Select id="year" value={form.academicYear ?? ''} disabled={!!editingId} onChange={(e) => set('academicYear', Number(e.target.value))}>
                <option value={1}>1학년</option>
                <option value={2}>2학년</option>
              </Select>
            </Field>
          )}
          <Field label="카테고리" htmlFor="cat" error={fe.category}>
            <Select id="cat" value={form.category} onChange={(e) => set('category', e.target.value as NoticeCategory)}>
              {NOTICE_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="제목" htmlFor="title" error={fe.title} counter={{ value: form.title, max: 120 }}>
          <Input id="title" value={form.title} invalid={!!fe.title} onChange={(e) => set('title', e.target.value)} placeholder="예: 2학년 현장실습 신청 안내" />
        </Field>
        <Field label="내용" htmlFor="body" error={fe.body} counter={{ value: form.body, max: 10000 }}>
          <Textarea id="body" rows={8} value={form.body} invalid={!!fe.body} onChange={(e) => set('body', e.target.value)} />
        </Field>
        <label className="flex min-h-[44px] items-center gap-2 text-sm text-navy-800">
          <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={form.important} onChange={(e) => set('important', e.target.checked)} />
          중요 공지로 표시 (학생 홈 브리핑에 노출)
        </label>
        {editingId && (
          <label className="flex min-h-[44px] items-center gap-2 text-sm text-navy-800">
            <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={renotify} onChange={(e) => setRenotify(e.target.checked)} />
            중요한 수정이므로 채팅에 수정 안내 카드를 한 번 더 보내기
          </label>
        )}
      </Card>
      <p className="text-xs text-navy-500">
        학과·학년 공지는 해당 기본 채널에 <b>원문 링크 카드</b>로만 전달되며 본문은 복사되지 않습니다. 같은 공지·판·채널에는 카드가 한 번만 생성됩니다.
      </p>
      <InlineError error={m.error && !m.error.fieldErrors ? m.error : null} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => navigate('/staff/notices')}>취소</Button>
        <Button type="submit" loading={m.pending}>{editingId ? '수정 저장' : '게시하기'}</Button>
      </div>
    </form>
  );
}

export function StaffNoticeNewPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/staff/notices" title="새 공지 작성" />
      <NoticeForm initial={emptyInput} />
    </div>
  );
}

export function StaffNoticeEditPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getNotice(id), [id]);
  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  if (!data.canManage || data.deletedAt) return <EmptyState title="수정할 수 없는 공지입니다" />;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/staff/notices" title="공지 수정" subtitle={`현재 제${data.revision}판 · 저장하면 제${data.revision + 1}판이 됩니다`} />
      <NoticeForm
        key={data.id}
        editingId={data.id}
        initial={{ audienceType: data.audienceType, academicYear: data.academicYear, category: data.category, title: data.title, body: data.body, important: data.important }}
      />
    </div>
  );
}
