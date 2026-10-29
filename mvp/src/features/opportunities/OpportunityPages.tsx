import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  addCheckItem,
  deleteCheckItem,
  getOpportunity,
  listOpportunities,
  OPPORTUNITY_KINDS,
  saveOpportunity,
  unsaveOpportunity,
  updateCheckItem,
  updateSaved,
} from '../../shared/data/api';
import { dday, formatDate, formatDateTime } from '../../shared/format';
import { useApi, useMutation } from '../../shared/hooks';
import type { CheckItem, OpportunityKind, SavedStatus } from '../../shared/types';
import { Badge, Button, Card, ConfirmDialog, cx, EmptyState, ErrorState, InlineError, Input, LoadingBlock, PageHeader, SectionTitle, Textarea } from '../../shared/ui';
import { CheckIcon, FileIcon, StarIcon, TrashIcon } from '../../shared/ui/icons';
import { useToast } from '../../shared/ui/toast';

const statusLabel: Record<SavedStatus, string> = {
  interested: '관심',
  preparing: '준비 중',
  self_reported_submitted: '제출했다고 기록',
  closed: '지원 안 함/종료',
};

const modeLabel = {
  external_document_submission: '외부 기관 직접 제출 (지정 양식)',
  external_link: '외부 사이트 접수',
  info_only: '안내 (별도 접수 방법 참고)',
} as const;

export function OpportunitiesPage() {
  const [kind, setKind] = useState<OpportunityKind | undefined>();
  const { data, error, loading, reload } = useApi(() => listOpportunities(kind), [kind]);

  return (
    <div>
      <PageHeader title="기회 센터" subtitle="장학금·근로·공모전·취업 공고를 저장하고 준비 상태를 관리하세요" />
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {[undefined, ...OPPORTUNITY_KINDS].map((k) => (
          <button
            key={k ?? 'all'}
            onClick={() => setKind(k)}
            aria-pressed={kind === k}
            className={cx(
              'min-h-[40px] shrink-0 rounded-full px-4 text-sm font-semibold ring-1 ring-inset',
              kind === k ? 'bg-navy-800 text-white ring-navy-800' : 'bg-white text-navy-600 ring-navy-200 hover:bg-navy-50',
            )}
          >
            {k ?? '전체'}
          </button>
        ))}
      </div>
      {loading && !data ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data!.length === 0 ? (
        <EmptyState title="해당 분류의 공고가 없습니다" />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data!.map((o) => (
            <Link key={o.id} to={`/app/opportunities/${o.id}`}>
              <Card className="h-full hover:ring-brand-200">
                <div className="flex items-center gap-1.5">
                  <Badge tone="accent">{o.kind}</Badge>
                  {o.saved && <Badge tone="sky"><StarIcon className="h-3 w-3" /> {statusLabel[o.saved.status]}</Badge>}
                  <span className={cx('ml-auto text-sm font-bold', o.isClosed ? 'text-navy-400' : 'text-brand-600')}>{dday(o.deadline)}</span>
                </div>
                <p className="mt-2 font-semibold text-navy-900">{o.title}</p>
                <p className="mt-0.5 text-xs text-navy-500">{o.organization}</p>
                <p className="mt-2 line-clamp-2 text-sm text-navy-600">{o.summary}</p>
                <p className="mt-3 text-xs text-navy-500">마감 {formatDate(o.deadline)} · {o.target}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <p className="mt-6 text-center text-[11px] text-navy-400">※ 모든 공고는 시연용 가상 데이터입니다. 실제 지원 전 반드시 원문 공고를 확인하세요.</p>
    </div>
  );
}

function ChecklistItem({ item }: { item: CheckItem }) {
  const upd = useMutation(updateCheckItem);
  const del = useMutation(deleteCheckItem);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(item.text);
  const done = !!item.completedAt;
  return (
    <li className="flex min-h-[52px] items-center gap-2 px-3 py-1.5">
      <button
        onClick={() => upd.mutate(item.id, { completed: !done })}
        role="checkbox"
        aria-checked={done}
        aria-label={`${item.text} 완료 표시`}
        className={cx('grid h-7 w-7 shrink-0 place-items-center rounded-lg ring-1 ring-inset', done ? 'bg-brand-600 text-white ring-brand-600' : 'bg-white ring-navy-300')}
      >
        {done && <CheckIcon className="h-4 w-4" />}
      </button>
      {editing ? (
        <form
          className="flex flex-1 gap-1.5"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await upd.mutate(item.id, { text: value })) setEditing(false);
          }}
        >
          <label htmlFor={`ci-${item.id}`} className="sr-only">항목 수정</label>
          <Input id={`ci-${item.id}`} autoFocus value={value} maxLength={100} onChange={(e) => setValue(e.target.value)} className="py-1.5" />
          <Button size="sm" type="submit">저장</Button>
        </form>
      ) : (
        <button onClick={() => setEditing(true)} className={cx('flex-1 text-left text-sm', done ? 'text-navy-400 line-through' : 'text-navy-900')} title="눌러서 수정">
          {item.text}
        </button>
      )}
      <button onClick={() => del.mutate(item.id)} className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-navy-300 hover:bg-navy-50 hover:text-brand-600" aria-label={`${item.text} 삭제`}>
        <TrashIcon className="h-4 w-4" />
      </button>
      {(upd.error || del.error) && <span className="sr-only" role="alert">{(upd.error ?? del.error)!.message}</span>}
    </li>
  );
}

export function OpportunityDetailPage() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useApi(() => getOpportunity(id), [id]);
  const save = useMutation(saveOpportunity);
  const unsave = useMutation(unsaveOpportunity);
  const upd = useMutation(updateSaved);
  const add = useMutation(addCheckItem);
  const [newItem, setNewItem] = useState('');
  const [memo, setMemo] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();

  if (loading && !data) return <LoadingBlock rows={4} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const { opportunity: o, items } = data;
  const s = o.saved;
  const done = items.filter((i) => i.completedAt).length;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader back="/app/opportunities" title={o.title} subtitle={o.organization} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr),380px]">
        {/* 원본 정보 */}
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="accent">{o.kind}</Badge>
              <Badge tone="navy">{o.target}</Badge>
              <span className={cx('ml-auto text-lg font-extrabold', o.isClosed ? 'text-navy-400' : 'text-brand-600')}>{dday(o.deadline)}</span>
            </div>
            <p className="mt-3 text-[15px] leading-7 text-navy-900">{o.summary}</p>
            <dl className="mt-4 grid grid-cols-[88px,1fr] gap-x-3 gap-y-2 text-sm">
              <dt className="text-navy-500">지원 자격</dt>
              <dd className="text-navy-900">{o.eligibility}</dd>
              <dt className="text-navy-500">접수 기간</dt>
              <dd className="text-navy-900">{formatDate(o.startsAt)} ~ {formatDateTime(o.deadline)}</dd>
              <dt className="text-navy-500">접수 방법</dt>
              <dd className="text-navy-900">{modeLabel[o.submissionMode]}</dd>
              <dt className="text-navy-500">제출처</dt>
              <dd className="text-navy-900">{o.destination ?? '정보 없음 · 원본 확인 필요'}</dd>
              <dt className="text-navy-500">원문</dt>
              <dd className="text-navy-900">{o.originalUrl ? <a className="text-brand-600 underline" href={o.originalUrl} target="_blank" rel="noreferrer">원문 공고 열기</a> : '원문 링크 없음 (시연 데이터)'}</dd>
            </dl>
          </Card>

          <Card>
            <SectionTitle>지정 양식</SectionTitle>
            {o.files.length === 0 ? (
              <p className="text-sm text-navy-500">지정 양식이 없습니다. 제출처 안내를 확인하세요.</p>
            ) : (
              <ul className="space-y-2">
                {o.files.map((f) => (
                  <li key={f.name} className="flex min-h-[48px] items-center gap-3 rounded-xl bg-navy-50 px-3">
                    <FileIcon className="h-5 w-5 text-navy-500" />
                    <span className="flex-1 text-sm text-navy-900">{f.name}</span>
                    {f.url ? (
                      <a href={f.url} className="text-sm font-semibold text-brand-600" download>다운로드</a>
                    ) : (
                      <span className="text-xs text-navy-400">시연용 · 파일 없음</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {o.submissionMode === 'external_document_submission' && (
              <p className="mt-3 rounded-xl bg-accent-100 px-3 py-2 text-xs text-[#8a4410]">
                이 장학금은 양식을 내려받아 작성한 뒤 <b>외부 기관에 직접 제출</b>해야 합니다. DIT NOW에서는 접수되지 않습니다.
              </p>
            )}
          </Card>
        </div>

        {/* 내 준비 관리 */}
        <div className="space-y-4">
          {!s ? (
            <Card className="text-center">
              <StarIcon className="mx-auto h-8 w-8 text-brand-600" />
              <p className="mt-2 font-semibold text-navy-900">준비 목록에 저장하기</p>
              <p className="mt-1 text-sm text-navy-500">마감일과 서류 준비 체크리스트를 나만 볼 수 있게 관리합니다.</p>
              <Button
                className="mt-4 w-full"
                loading={save.pending}
                onClick={async () => {
                  if (await save.mutate(o.id)) toast('준비 목록에 저장했어요');
                }}
              >
                저장하고 준비 시작
              </Button>
              <div className="mt-2"><InlineError error={save.error} /></div>
            </Card>
          ) : (
            <>
              <Card>
                <SectionTitle>내 준비 상태</SectionTitle>
                <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="준비 상태">
                  {(Object.keys(statusLabel) as SavedStatus[]).map((k) => (
                    <button
                      key={k}
                      role="radio"
                      aria-checked={s.status === k}
                      disabled={upd.pending}
                      onClick={() => upd.mutate(s.id, { status: k })}
                      className={cx(
                        'min-h-[44px] rounded-xl px-2 text-xs font-semibold ring-1 ring-inset',
                        s.status === k ? 'bg-navy-800 text-white ring-navy-800' : 'bg-white text-navy-600 ring-navy-200 hover:bg-navy-50',
                      )}
                    >
                      {statusLabel[k]}
                    </button>
                  ))}
                </div>
                {s.status === 'self_reported_submitted' && s.selfReportedSubmittedAt && (
                  <p className="mt-2 text-xs text-navy-500">{formatDateTime(s.selfReportedSubmittedAt)}에 제출했다고 직접 기록함 · 기관 접수 확인 아님</p>
                )}
                <label htmlFor="memo" className="mt-4 block text-sm font-semibold text-navy-800">메모</label>
                <Textarea
                  id="memo"
                  className="mt-1.5 min-h-[80px]"
                  maxLength={1000}
                  value={memo ?? s.memo}
                  onChange={(e) => setMemo(e.target.value)}
                  placeholder="추천서 부탁드릴 교수님, 준비 일정 등"
                />
                {memo !== null && memo !== s.memo && (
                  <Button
                    size="sm"
                    className="mt-2"
                    loading={upd.pending}
                    onClick={async () => {
                      if (await upd.mutate(s.id, { memo })) {
                        setMemo(null);
                        toast('메모를 저장했어요');
                      }
                    }}
                  >
                    메모 저장
                  </Button>
                )}
                <div className="mt-2"><InlineError error={upd.error} /></div>
              </Card>

              <Card className="p-0 sm:p-0">
                <div className="flex items-center justify-between px-4 pt-4">
                  <h2 className="font-bold text-navy-900">준비 체크리스트</h2>
                  <span className="text-sm font-semibold text-brand-600">{done}/{items.length}</span>
                </div>
                {items.length === 0 ? (
                  <p className="px-4 py-4 text-sm text-navy-500">항목을 추가해 준비 과정을 관리하세요.</p>
                ) : (
                  <ul className="mt-2 divide-y divide-navy-100">
                    {items.map((i) => <ChecklistItem key={i.id} item={i} />)}
                  </ul>
                )}
                <form
                  className="flex gap-2 border-t border-navy-100 p-3"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    if (await add.mutate(s.id, newItem)) setNewItem('');
                  }}
                >
                  <label htmlFor="new-item" className="sr-only">새 항목</label>
                  <Input id="new-item" value={newItem} maxLength={100} onChange={(e) => setNewItem(e.target.value)} placeholder="예: 성적증명서 발급" />
                  <Button type="submit" loading={add.pending} disabled={!newItem.trim()}>추가</Button>
                </form>
                {add.error && <div className="px-3 pb-3"><InlineError error={add.error} /></div>}
              </Card>

              <Button variant="ghost" className="w-full" onClick={() => setConfirm(true)}>준비 목록에서 삭제</Button>
            </>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirm}
        danger
        title="준비 목록에서 삭제할까요?"
        description="상태, 메모, 체크리스트가 모두 삭제됩니다. 공고 자체는 사라지지 않습니다."
        confirmLabel="삭제"
        loading={unsave.pending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          if (s && (await unsave.mutate(s.id))) toast('준비 목록에서 삭제했어요');
          setConfirm(false);
        }}
      />
    </div>
  );
}
