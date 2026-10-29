import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  applyRecruitment,
  createRecruitment,
  decideApplication,
  deleteRecruitment,
  getRecruitment,
  setRecruitmentStatus,
  updateRecruitment,
  withdrawApplication,
  type RecruitmentInput,
} from '../../shared/data/api';
import { dday, formatDateTime, toLocalInput } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, InlineError, Input, LoadingBlock, PageHeader, SectionTitle, Textarea } from '../../shared/ui';
import { useToast } from '../../shared/ui/toast';

const appStatus = {
  pending: { label: '검토 대기', tone: 'gray' },
  accepted: { label: '승인', tone: 'green' },
  rejected: { label: '거절', tone: 'brand' },
  withdrawn: { label: '철회', tone: 'gray' },
} as const;

export function RecruitmentDetailPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getRecruitment(id), [id]);
  const [message, setMessage] = useState('');
  const [confirm, setConfirm] = useState(false);
  const apply = useMutation(applyRecruitment);
  const withdraw = useMutation(withdrawApplication);
  const decide = useMutation(decideApplication);
  const status = useMutation(setRecruitmentStatus);
  const del = useMutation(deleteRecruitment);
  const navigate = useNavigate();
  const toast = useToast();

  if (loading && !data) return <LoadingBlock rows={3} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const { recruitment: r, applications } = data;
  const open = r.status === 'open' && !r.isExpired;
  const full = r.acceptedCount >= r.capacity - 1;
  const mine = r.myApplication && r.myApplication.status !== 'withdrawn' ? r.myApplication : null;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/app/community?tab=recruit" title={r.title} />
      <Card>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="accent">{r.field}</Badge>
          <Badge tone={open ? 'green' : 'gray'}>{open ? '모집 중' : '마감'}</Badge>
          <span className="ml-auto text-sm font-bold text-brand-600">{dday(r.deadline)}</span>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-brand-50 font-bold text-brand-700" aria-hidden>{r.ownerName.slice(0, 1)}</span>
          <div>
            <p className="text-sm font-semibold text-navy-900">{r.ownerName}</p>
            <p className="text-xs text-navy-500">{r.ownerDepartment} · 실명 활동 프로필</p>
          </div>
        </div>
        <dl className="mt-4 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 rounded-xl bg-navy-50 p-3 text-sm">
          <dt className="text-navy-500">모집 역할</dt>
          <dd className="text-navy-900">{r.roles}</dd>
          <dt className="text-navy-500">팀 인원</dt>
          <dd className="text-navy-900">{r.acceptedCount + 1} / {r.capacity}명 (모집자 포함)</dd>
          <dt className="text-navy-500">마감</dt>
          <dd className="text-navy-900">{formatDateTime(r.deadline)}</dd>
        </dl>
        <p className="mt-4 whitespace-pre-wrap break-words text-[15px] leading-7 text-navy-900">{r.body}</p>
      </Card>

      {r.isOwner ? (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to={`/app/community/recruitments/${r.id}/edit`} className="inline-flex min-h-[44px] items-center rounded-xl px-4 text-sm font-semibold text-navy-700 ring-1 ring-inset ring-navy-200 hover:bg-navy-50">수정</Link>
            <Button variant="secondary" loading={status.pending} onClick={() => status.mutate(r.id, r.status === 'open' ? 'closed' : 'open')}>
              {r.status === 'open' ? '모집 마감하기' : '모집 다시 열기'}
            </Button>
            <Button variant="danger" onClick={() => setConfirm(true)}>삭제</Button>
          </div>
          <div className="mt-2"><InlineError error={status.error ?? del.error} /></div>

          <section className="mt-6">
            <SectionTitle>지원자 {applications.length}명</SectionTitle>
            <InlineError error={decide.error} />
            {applications.length === 0 ? (
              <EmptyState title="아직 지원자가 없어요" />
            ) : (
              <div className="space-y-2">
                {applications.map((a) => (
                  <Card key={a.id}>
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-navy-900">{a.applicantName}</p>
                      <span className="text-xs text-navy-500">{a.applicantDepartment}</span>
                      <Badge tone={appStatus[a.status].tone} className="ml-auto">{appStatus[a.status].label}</Badge>
                    </div>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-navy-700">{a.message}</p>
                    {a.status === 'pending' && (
                      <div className="mt-3 flex gap-2">
                        <Button size="sm" disabled={full || decide.pending} onClick={() => decide.mutate(a.id, 'accepted')}>승인</Button>
                        <Button size="sm" variant="secondary" disabled={decide.pending} onClick={() => decide.mutate(a.id, 'rejected')}>거절</Button>
                        {full && <span className="self-center text-xs text-navy-500">정원이 찼습니다</span>}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <section className="mt-6">
          <SectionTitle>지원하기</SectionTitle>
          {mine ? (
            <Card>
              <div className="flex items-center gap-2">
                <p className="font-semibold text-navy-900">내 지원</p>
                <Badge tone={appStatus[mine.status].tone}>{appStatus[mine.status].label}</Badge>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-navy-700">{mine.message}</p>
              {mine.status === 'pending' && (
                <Button size="sm" variant="secondary" className="mt-3" loading={withdraw.pending} onClick={() => withdraw.mutate(mine.id)}>지원 철회</Button>
              )}
              <div className="mt-2"><InlineError error={withdraw.error} /></div>
            </Card>
          ) : !open ? (
            <EmptyState title="모집이 마감되었습니다" />
          ) : (
            <Card>
              <form
                className="space-y-3"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await apply.mutate(r.id, message)) {
                    setMessage('');
                    toast('지원했어요. 모집자가 확인하면 상태가 바뀝니다.');
                  }
                }}
                noValidate
              >
                <Field label="지원 메시지" htmlFor="msg" error={apply.fieldErrors.message} counter={{ value: message, max: 500 }}>
                  <Textarea id="msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="할 수 있는 역할, 경험, 연락 가능한 시간 등을 적어 주세요." />
                </Field>
                <p className="text-xs text-navy-500">지원 시 모집자에게 내 이름과 학과가 공개됩니다.</p>
                <InlineError error={apply.error && !apply.error.fieldErrors ? apply.error : null} />
                <Button type="submit" className="w-full" loading={apply.pending}>실명으로 지원하기</Button>
              </form>
            </Card>
          )}
        </section>
      )}

      <ConfirmDialog
        open={confirm}
        danger
        title="모집글을 삭제할까요?"
        description="삭제하면 목록에서 사라지고 지원자도 더 이상 볼 수 없습니다."
        confirmLabel="삭제"
        loading={del.pending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          if (await del.mutate(r.id)) {
            toast('모집글을 삭제했어요');
            navigate('/app/community?tab=recruit', { replace: true });
          } else setConfirm(false);
        }}
      />
    </div>
  );
}

function RecruitmentForm({ initial, recruitmentId }: { initial: RecruitmentInput; recruitmentId?: string }) {
  const [form, setForm] = useState(initial);
  const create = useMutation(createRecruitment);
  const update = useMutation(updateRecruitment);
  const m = recruitmentId ? update : create;
  const fe = m.fieldErrors;
  const navigate = useNavigate();
  const toast = useToast();
  const set = <K extends keyof RecruitmentInput>(k: K, v: RecruitmentInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const res = recruitmentId ? await update.mutate(recruitmentId, form) : await create.mutate(form);
    if (!res) return;
    toast(recruitmentId ? '수정했어요' : '모집글을 올렸어요');
    navigate(`/app/community/recruitments/${res.id}`, { replace: true });
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Card className="space-y-4">
        <Field label="제목" htmlFor="title" error={fe.title} counter={{ value: form.title, max: 120 }}>
          <Input id="title" value={form.title} invalid={!!fe.title} onChange={(e) => set('title', e.target.value)} placeholder="예: 공모전 같이 나갈 백엔드 개발자 구해요" />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="분야" htmlFor="field" error={fe.field}>
            <Input id="field" value={form.field} invalid={!!fe.field} onChange={(e) => set('field', e.target.value)} placeholder="공모전 / 해커톤 / 스터디" />
          </Field>
          <Field label="팀 인원 (본인 포함)" htmlFor="cap" error={fe.capacity}>
            <Input id="cap" type="number" min={2} max={20} value={form.capacity} invalid={!!fe.capacity} onChange={(e) => set('capacity', Number(e.target.value))} />
          </Field>
        </div>
        <Field label="모집 역할" htmlFor="roles" error={fe.roles}>
          <Input id="roles" value={form.roles} invalid={!!fe.roles} onChange={(e) => set('roles', e.target.value)} placeholder="예: 디자이너 1명, 백엔드 1명" />
        </Field>
        <Field label="모집 마감" htmlFor="deadline" error={fe.deadline}>
          <Input id="deadline" type="datetime-local" value={form.deadline} invalid={!!fe.deadline} onChange={(e) => set('deadline', e.target.value)} />
        </Field>
        <Field label="설명" htmlFor="body" error={fe.body} counter={{ value: form.body, max: 5000 }}>
          <Textarea id="body" rows={8} value={form.body} invalid={!!fe.body} onChange={(e) => set('body', e.target.value)} />
        </Field>
      </Card>
      <p className="text-xs text-navy-500">모집글에는 실명 활동 프로필(이름·학과)이 표시됩니다. 학교 공식 실명 인증과는 다릅니다.</p>
      <InlineError error={m.error && !m.error.fieldErrors ? m.error : null} />
      {m.error?.code === 'CONFLICT' && m.error.fieldErrors && <InlineError error={m.error} />}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => navigate(-1)}>취소</Button>
        <Button type="submit" loading={m.pending}>{recruitmentId ? '수정 저장' : '모집글 올리기'}</Button>
      </div>
    </form>
  );
}

export function RecruitmentNewPage() {
  const weekLater = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  weekLater.setHours(23, 0, 0, 0);
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back="/app/community?tab=recruit" title="팀원 모집하기" />
      <RecruitmentForm initial={{ title: '', body: '', field: '', roles: '', capacity: 4, deadline: toLocalInput(weekLater.toISOString()) }} />
    </div>
  );
}

export function RecruitmentEditPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getRecruitment(id), [id]);
  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const r = data.recruitment;
  if (!r.isOwner) return <EmptyState title="작성자만 수정할 수 있습니다" />;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back={`/app/community/recruitments/${id}`} title="모집글 수정" />
      <RecruitmentForm
        key={id}
        recruitmentId={id}
        initial={{ title: r.title, body: r.body, field: r.field, roles: r.roles, capacity: r.capacity, deadline: toLocalInput(r.deadline) }}
      />
    </div>
  );
}
