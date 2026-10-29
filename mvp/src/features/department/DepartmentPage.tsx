import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../app/auth';
import { createFreeChannel, listMyChannels, listNoticesForMe, type ChannelSummary } from '../../shared/data/api';
import { timeAgo } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import { Badge, Button, Card, EmptyState, ErrorState, Field, InlineError, Input, LoadingBlock, PageHeader, SectionTitle } from '../../shared/ui';
import { ChevronRight, HashIcon, MegaphoneIcon, PlusIcon, ShieldIcon } from '../../shared/ui/icons';
import { useToast } from '../../shared/ui/toast';

function ChannelRow({ c }: { c: ChannelSummary }) {
  return (
    <Link to={`/app/department/channels/${c.id}`} className="flex min-h-[64px] items-center gap-3 px-4 py-3 hover:bg-navy-50/60">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${c.official ? 'bg-brand-50 text-brand-600' : 'bg-navy-50 text-navy-500'}`}>
        {c.official ? <ShieldIcon /> : <HashIcon />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate font-semibold text-navy-900">{c.name}</span>
          {c.official && <Badge tone="brand">기본</Badge>}
        </span>
        <span className="block truncate text-xs text-navy-500">{c.lastMessagePreview ?? c.description}</span>
      </span>
      {c.lastMessageAt && <span className="shrink-0 text-[11px] text-navy-400">{timeAgo(c.lastMessageAt)}</span>}
      <ChevronRight className="h-4 w-4 shrink-0 text-navy-300" />
    </Link>
  );
}

function NewChannelForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const { mutate, pending, error, fieldErrors } = useMutation(createFreeChannel);
  const toast = useToast();
  const navigate = useNavigate();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ch = await mutate({ name, description });
    if (ch) {
      toast('자유 채널을 만들었어요');
      onDone();
      navigate(`/app/department/channels/${ch.id}`);
    }
  };
  return (
    <Card className="mt-3">
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field label="채널 이름" htmlFor="ch-name" error={fieldErrors.name} counter={{ value: name, max: 60 }}>
          <Input id="ch-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 정보처리기사 스터디" />
        </Field>
        <Field label="설명 (선택)" htmlFor="ch-desc" error={fieldErrors.description}>
          <Input id="ch-desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="어떤 이야기를 나누는 채널인가요?" />
        </Field>
        <p className="text-xs text-navy-500">학생이 만든 채널은 일반 채널이며 공식 배지가 붙지 않습니다. 학과 구성원 누구나 참여할 수 있어요.</p>
        <InlineError error={error && !error.fieldErrors ? error : null} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onDone}>취소</Button>
          <Button type="submit" loading={pending}>만들기</Button>
        </div>
      </form>
    </Card>
  );
}

export function DepartmentPage() {
  const { user } = useAuth();
  const channels = useApi(listMyChannels, []);
  const notices = useApi(() => listNoticesForMe(3), []);
  const [creating, setCreating] = useState(false);

  const basics = channels.data?.filter((c) => c.kind !== 'free') ?? [];
  const frees = channels.data?.filter((c) => c.kind === 'free') ?? [];
  const deptNotices = notices.data?.filter((n) => n.audienceType !== 'all') ?? [];

  return (
    <div>
      <PageHeader title={user?.departmentName ?? '우리 학과'} subtitle="학과 전체·학년 채널과 공식 공지를 한 곳에서" />

      {deptNotices.length > 0 && (
        <section className="mb-6">
          <SectionTitle>최근 학과 공식 공지</SectionTitle>
          <div className="space-y-2">
            {deptNotices.map((n) => (
              <Link key={n.id} to={`/app/notices/${n.id}`} className="flex min-h-[56px] items-center gap-3 rounded-2xl bg-brand-50 px-4 py-3 ring-1 ring-brand-100 hover:bg-brand-100/60">
                <MegaphoneIcon className="h-5 w-5 shrink-0 text-brand-600" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-navy-900">{n.title}</span>
                  <span className="text-xs text-navy-500">{n.audience} · {n.authorName} {n.authorRole}</span>
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {channels.loading && !channels.data ? (
        <LoadingBlock />
      ) : channels.error ? (
        <ErrorState error={channels.error} onRetry={channels.reload} />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section>
            <SectionTitle>기본 채널</SectionTitle>
            <Card className="divide-y divide-navy-100 p-0 sm:p-0">
              {basics.map((c) => <ChannelRow key={c.id} c={c} />)}
            </Card>
          </section>
          <section>
            <SectionTitle
              action={
                user?.role !== 'admin' && !creating && (
                  <Button size="sm" variant="secondary" onClick={() => setCreating(true)}>
                    <PlusIcon className="h-4 w-4" /> 새 채널
                  </Button>
                )
              }
            >
              자유 채널
            </SectionTitle>
            {creating && <NewChannelForm onDone={() => setCreating(false)} />}
            {frees.length === 0 ? (
              !creating && <EmptyState title="아직 자유 채널이 없어요" description="스터디·동아리·취미 등 목적별 채널을 만들어 보세요." />
            ) : (
              <Card className="mt-3 divide-y divide-navy-100 p-0 first:mt-0 sm:p-0">
                {frees.map((c) => <ChannelRow key={c.id} c={c} />)}
              </Card>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
