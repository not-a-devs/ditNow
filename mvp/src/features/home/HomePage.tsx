import { Link } from 'react-router-dom';
import { useAuth } from '../../app/auth';
import { getBriefing, getMySavedSummary, getTimetable, listNoticesForMe } from '../../shared/data/api';
import { dday, timeAgo, WEEKDAYS } from '../../shared/format';
import { useApi } from '../../shared/hooks';
import { Badge, Card, EmptyState, ErrorState, LoadingBlock, SectionTitle } from '../../shared/ui';
import { ChevronRight, MegaphoneIcon, SparkIcon } from '../../shared/ui/icons';

const sourceLink: Record<string, (id: string) => string> = {
  course: () => '/app/timetable',
  opportunity: (id) => `/app/opportunities/${id}`,
  notice: (id) => `/app/notices/${id}`,
  recruitment: (id) => `/app/community/recruitments/${id}`,
};

const savedStatusLabel = { interested: '관심', preparing: '준비 중', self_reported_submitted: '제출했다고 기록', closed: '종료' } as const;

export function HomePage() {
  const { user } = useAuth();
  const briefing = useApi(getBriefing, []);
  const timetable = useApi(getTimetable, []);
  const notices = useApi(() => listNoticesForMe(5), []);
  const saved = useApi(getMySavedSummary, []);
  const today = new Date().getDay();
  const todays = timetable.data?.filter((s) => s.weekday === today) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-navy-500">
          {new Date().getMonth() + 1}월 {new Date().getDate()}일 {WEEKDAYS[today]}요일
        </p>
        <h1 className="mt-0.5 text-2xl font-bold text-navy-900">
          {user?.name}님, 오늘도 반가워요 <span aria-hidden>👋</span>
        </h1>
      </div>

      {/* 오늘의 브리핑 */}
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-navy-800 to-navy-900 p-5 text-white sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <SparkIcon className="h-5 w-5 text-sky-500" />
          <h2 className="font-bold">오늘의 브리핑</h2>
          <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-navy-100">규칙 기반 · AI 미연결</span>
        </div>
        {briefing.loading && !briefing.data ? (
          <div className="mt-4 h-24 animate-pulse rounded-2xl bg-white/10" />
        ) : briefing.error ? (
          <p className="mt-3 text-sm text-navy-100">브리핑을 불러오지 못했습니다. 아래 카드에서 원본을 직접 확인하세요.</p>
        ) : (
          briefing.data && (
            <>
              <p className="mt-3 text-[15px] text-navy-50">{briefing.data.summary}</p>
              {briefing.data.actions.length > 0 && (
                <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {briefing.data.actions.map((a, i) => (
                    <li key={i}>
                      <Link
                        to={sourceLink[a.source_type]?.(a.source_id) ?? '/app'}
                        className="flex min-h-[56px] items-center justify-between gap-2 rounded-2xl bg-white/10 px-4 py-3 hover:bg-white/15"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold">{a.title}</span>
                          <span className="block truncate text-xs text-navy-200">{a.reason}</span>
                        </span>
                        <ChevronRight className="h-4 w-4 shrink-0 text-navy-200" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {briefing.data.cautions.map((c) => (
                <p key={c} className="mt-3 text-[11px] text-navy-300">※ {c}</p>
              ))}
            </>
          )
        )}
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 오늘 수업 */}
        <section>
          <SectionTitle action={<Link to="/app/timetable" className="text-sm font-semibold text-brand-600">전체 시간표</Link>}>오늘 수업</SectionTitle>
          {timetable.loading && !timetable.data ? (
            <LoadingBlock rows={2} />
          ) : timetable.error ? (
            <ErrorState error={timetable.error} onRetry={timetable.reload} />
          ) : todays.length === 0 ? (
            <EmptyState title="오늘은 수업이 없어요" description="시간표에서 이번 주 수업을 확인할 수 있습니다." />
          ) : (
            <div className="space-y-2">
              {todays.map((s) => (
                <Card key={`${s.courseId}-${s.start}`} className="flex items-center gap-4">
                  <div className="w-14 shrink-0 text-center">
                    <p className="text-sm font-bold text-brand-600">{s.start}</p>
                    <p className="text-[11px] text-navy-400">~{s.end}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-navy-900">{s.name}</p>
                    <p className="text-xs text-navy-500">{s.room} · {s.professor} 교수</p>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* 공식 공지 */}
        <section>
          <SectionTitle action={<Link to="/app/department" className="text-sm font-semibold text-brand-600">학과 채널</Link>}>나에게 온 공식 공지</SectionTitle>
          {notices.loading && !notices.data ? (
            <LoadingBlock rows={2} />
          ) : notices.error ? (
            <ErrorState error={notices.error} onRetry={notices.reload} />
          ) : notices.data!.length === 0 ? (
            <EmptyState title="새 공식 공지가 없습니다" />
          ) : (
            <Card className="divide-y divide-navy-100 p-0 sm:p-0">
              {notices.data!.map((n) => (
                <Link key={n.id} to={`/app/notices/${n.id}`} className="flex min-h-[56px] items-center gap-3 px-4 py-3 hover:bg-navy-50/60">
                  <MegaphoneIcon className="h-5 w-5 shrink-0 text-brand-600" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-navy-900">{n.title}</p>
                    <p className="text-xs text-navy-500">{n.audience} · {timeAgo(n.updatedAt)}</p>
                  </div>
                  {n.important && <Badge tone="brand">중요</Badge>}
                </Link>
              ))}
            </Card>
          )}
        </section>
      </div>

      {/* 내 지원 준비 */}
      <section>
        <SectionTitle action={<Link to="/app/opportunities" className="text-sm font-semibold text-brand-600">기회 센터</Link>}>내 지원 준비</SectionTitle>
        {saved.loading && !saved.data ? (
          <LoadingBlock rows={1} />
        ) : saved.error ? (
          <ErrorState error={saved.error} onRetry={saved.reload} />
        ) : saved.data!.length === 0 ? (
          <EmptyState
            title="저장한 장학금·공모전이 없어요"
            description="기회 센터에서 공고를 저장하면 마감일과 준비 체크리스트를 여기서 관리할 수 있어요."
            action={<Link to="/app/opportunities" className="inline-flex min-h-[44px] items-center rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white">기회 둘러보기</Link>}
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {saved.data!.map(({ saved: s, opportunity: o, done, total }) => (
              <Link key={s.id} to={`/app/opportunities/${o.id}`}>
                <Card className="h-full hover:ring-brand-200">
                  <div className="flex items-center gap-2">
                    <Badge tone="accent">{o.kind}</Badge>
                    <Badge tone={s.status === 'self_reported_submitted' ? 'green' : 'gray'}>{savedStatusLabel[s.status]}</Badge>
                    <span className="ml-auto text-sm font-bold text-brand-600">{dday(o.deadline)}</span>
                  </div>
                  <p className="mt-2 font-semibold text-navy-900">{o.title}</p>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-navy-100" role="progressbar" aria-valuenow={done} aria-valuemax={total} aria-label="체크리스트 진행률">
                    <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-navy-500">체크리스트 {done}/{total}</p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
