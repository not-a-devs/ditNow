import { getTimetable } from '../../shared/data/api';
import { WEEKDAYS } from '../../shared/format';
import { useApi } from '../../shared/hooks';
import { Card, cx, EmptyState, ErrorState, LoadingBlock, PageHeader } from '../../shared/ui';

const DAYS = [1, 2, 3, 4, 5];

export function TimetablePage() {
  const { data, error, loading, reload } = useApi(getTimetable, []);
  const today = new Date().getDay();

  return (
    <div>
      <PageHeader title="내 시간표" subtitle="수강 중인 과목의 주간 수업 시간 (시연용 가상 수강 정보)" />
      {loading && !data ? (
        <LoadingBlock rows={4} />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data!.length === 0 ? (
        <EmptyState title="등록된 수강 과목이 없습니다" />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          {DAYS.map((d) => {
            const slots = data!.filter((s) => s.weekday === d);
            return (
              <section key={d} aria-label={`${WEEKDAYS[d]}요일`}>
                <h2 className={cx('mb-2 rounded-xl px-3 py-2 text-sm font-bold', d === today ? 'bg-brand-600 text-white' : 'bg-white text-navy-700 ring-1 ring-navy-100')}>
                  {WEEKDAYS[d]}요일 {d === today && <span className="text-xs font-medium">· 오늘</span>}
                </h2>
                {slots.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-navy-400">수업 없음</p>
                ) : (
                  <div className="space-y-2">
                    {slots.map((s) => (
                      <Card key={`${s.courseId}-${s.start}`} className="border-l-4 border-l-brand-600 p-3 sm:p-3">
                        <p className="text-xs font-semibold text-brand-600">{s.start} ~ {s.end}</p>
                        <p className="mt-0.5 font-semibold text-navy-900">{s.name}</p>
                        <p className="text-xs text-navy-500">{s.room}</p>
                        <p className="text-xs text-navy-400">{s.professor} 교수</p>
                      </Card>
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
