import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { listAnonPosts, listRecruitments } from '../../shared/data/api';
import { dday, timeAgo } from '../../shared/format';
import { useApi } from '../../shared/hooks';
import { Badge, Card, cx, EmptyState, ErrorState, Input, LoadingBlock, PageHeader } from '../../shared/ui';
import { ChatIcon, PlusIcon, SearchIcon } from '../../shared/ui/icons';

const PAGE = 10;

function AnonymousBoard() {
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const { data, error, loading, reload } = useApi(() => listAnonPosts({ query: applied, limit }), [applied, limit]);

  return (
    <div>
      <div className="mb-4 rounded-2xl bg-navy-50 px-4 py-3 text-xs text-navy-600">
        🔒 이 게시판의 글과 댓글은 <b>익명</b>으로 표시됩니다. 다른 학생에게 이름·학과·계정 정보가 공개되지 않으며, 게시 후 실명으로 바꿀 수 없습니다.
      </div>
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setLimit(PAGE);
          setApplied(query);
        }}
      >
        <label htmlFor="q" className="sr-only">검색</label>
        <Input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="제목·내용 검색" />
        <button className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white text-navy-600 ring-1 ring-navy-200" aria-label="검색">
          <SearchIcon />
        </button>
      </form>
      {loading && !data ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data!.items.length === 0 ? (
        <EmptyState title={applied ? '검색 결과가 없습니다' : '아직 글이 없어요'} description={applied ? '다른 검색어로 찾아보세요.' : '첫 익명 글을 남겨 보세요.'} />
      ) : (
        <>
          <Card className="divide-y divide-navy-100 p-0 sm:p-0">
            {data!.items.map((p) => (
              <Link key={p.id} to={`/app/community/anonymous/${p.id}`} className="block px-4 py-3.5 hover:bg-navy-50/60">
                <div className="flex items-center gap-2">
                  <p className="min-w-0 flex-1 truncate font-semibold text-navy-900">{p.title}</p>
                  {p.isMine && <Badge tone="sky">내 글</Badge>}
                </div>
                <p className="mt-0.5 line-clamp-2 text-sm text-navy-600">{p.body}</p>
                <p className="mt-1.5 flex items-center gap-3 text-xs text-navy-400">
                  <span>익명</span>
                  <span>{timeAgo(p.createdAt)}</span>
                  <span className="inline-flex items-center gap-1"><ChatIcon className="h-3.5 w-3.5" />{p.commentCount}</span>
                </p>
              </Link>
            ))}
          </Card>
          {data!.total > data!.items.length && (
            <button onClick={() => setLimit((l) => l + PAGE)} className="mt-3 min-h-[44px] w-full rounded-xl bg-white text-sm font-semibold text-navy-600 ring-1 ring-navy-200 hover:bg-navy-50">
              더 보기 ({data!.items.length}/{data!.total})
            </button>
          )}
        </>
      )}
    </div>
  );
}

function RecruitmentBoard() {
  const [onlyOpen, setOnlyOpen] = useState(false);
  const { data, error, loading, reload } = useApi(() => listRecruitments({ onlyOpen }), [onlyOpen]);
  return (
    <div>
      <div className="mb-4 rounded-2xl bg-accent-100 px-4 py-3 text-xs text-[#8a4410]">
        👤 팀원 모집은 <b>실명 활동 프로필</b>(이름·학과)로 표시됩니다. 익명 게시판 활동과는 연결되지 않습니다.
      </div>
      <label className="mb-3 flex min-h-[40px] items-center gap-2 text-sm text-navy-700">
        <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} />
        모집 중인 글만 보기
      </label>
      {loading && !data ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data!.length === 0 ? (
        <EmptyState title="모집글이 없습니다" description="공모전·프로젝트 팀원을 직접 모집해 보세요." />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data!.map((r) => {
            const open = r.status === 'open' && !r.isExpired;
            return (
              <Link key={r.id} to={`/app/community/recruitments/${r.id}`}>
                <Card className="h-full hover:ring-brand-200">
                  <div className="flex items-center gap-1.5">
                    <Badge tone="accent">{r.field}</Badge>
                    <Badge tone={open ? 'green' : 'gray'}>{open ? '모집 중' : '마감'}</Badge>
                    {r.isOwner && <Badge tone="sky">내 모집</Badge>}
                    <span className="ml-auto text-sm font-bold text-brand-600">{dday(r.deadline)}</span>
                  </div>
                  <p className="mt-2 font-semibold text-navy-900">{r.title}</p>
                  <p className="mt-1 line-clamp-2 text-sm text-navy-600">{r.roles}</p>
                  <p className="mt-3 text-xs text-navy-500">
                    {r.ownerName} · {r.ownerDepartment} · 팀 {r.acceptedCount + 1}/{r.capacity}명
                  </p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function CommunityPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'recruit' ? 'recruit' : 'anon';
  const newLink = tab === 'anon' ? '/app/community/anonymous/new' : '/app/community/recruitments/new';

  return (
    <div>
      <PageHeader
        title="커뮤니티"
        subtitle="익명으로 자유롭게, 실명으로 함께 만들기"
        action={
          <Link to={newLink} className="inline-flex min-h-[44px] items-center gap-1 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            <PlusIcon className="h-4 w-4" /> {tab === 'anon' ? '익명 글쓰기' : '모집하기'}
          </Link>
        }
      />
      <div role="tablist" className="mb-4 grid grid-cols-2 rounded-xl bg-navy-100/70 p-1">
        {[
          { key: 'anon', label: '익명 자유게시판' },
          { key: 'recruit', label: '실명 팀원 모집' },
        ].map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setParams(t.key === 'anon' ? {} : { tab: 'recruit' }, { replace: true })}
            className={cx('min-h-[40px] rounded-lg text-sm font-semibold', tab === t.key ? 'bg-white text-brand-700 shadow-sm' : 'text-navy-500')}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'anon' ? <AnonymousBoard /> : <RecruitmentBoard />}
    </div>
  );
}
