// FR-JOB-001 public job search and FR-OPP-005 contest → team-recruitment ID candidates.
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import * as api from './api';
import type { ContestCandidate, JobFilter, JobSummary } from './types';
import { ErrorBox, Loading, ProvenanceBadge, SourceLink, describeError, formatDate, type Load } from './ui';

type Paged<T> = { items: T[]; nextCursor: string | null };

export function JobsPanel() {
  const [draft, setDraft] = useState<JobFilter>({ q: '', department: '', openOnly: false });
  const [filter, setFilter] = useState<JobFilter>({});
  const [jobs, setJobs] = useState<Load<Paged<JobSummary>>>({ state: 'loading' });
  const [moreError, setMoreError] = useState<string | null>(null);

  const load = useCallback(() => {
    setJobs({ state: 'loading' });
    api.listJobs(filter).then(
      (page) => setJobs({ state: 'ready', data: { items: page.items, nextCursor: page.next_cursor } }),
      (error) => setJobs({ state: 'error', ...describeError(error) }),
    );
  }, [filter]);
  useEffect(load, [load]);

  const more = () => {
    if (jobs.state !== 'ready' || !jobs.data.nextCursor) return;
    setMoreError(null);
    const current = jobs.data;
    api.listJobs({ ...filter, cursor: current.nextCursor }).then(
      (page) => setJobs({ state: 'ready', data: { items: [...current.items, ...page.items], nextCursor: page.next_cursor } }),
      (error) => setMoreError(describeError(error).message),
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFilter({ ...draft });
  };

  return (
    <section aria-labelledby="careers-jobs" className="space-y-3">
      <h2 id="careers-jobs" className="text-lg font-semibold">채용·아르바이트 공고</h2>
      <p className="text-xs text-slate-500">승인된 기회 공고 원본(취업 분류)을 그대로 보여 줍니다. 이 플랫폼은 지원서를 받거나 채용·고용을 확인하지 않습니다.</p>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 text-sm">
        <label className="flex flex-col">검색어
          <input value={draft.q} maxLength={50} onChange={(e) => setDraft({ ...draft, q: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <label className="flex flex-col">학과 코드
          <input value={draft.department} maxLength={20} onChange={(e) => setDraft({ ...draft, department: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={!!draft.openOnly} onChange={(e) => setDraft({ ...draft, openOnly: e.target.checked })} />마감 전만
        </label>
        <button type="submit" className="rounded bg-slate-900 px-3 py-1 text-white">검색</button>
      </form>
      {jobs.state === 'loading' && <Loading label="공고를 불러오는 중…" />}
      {jobs.state === 'error' && <ErrorBox message={jobs.message} requestId={jobs.requestId} onRetry={load} />}
      {jobs.state === 'ready' && jobs.data.items.length === 0 && <p className="text-sm text-slate-500">조건에 맞는 공고가 없습니다.</p>}
      {jobs.state === 'ready' && jobs.data.items.length > 0 && (
        <ul className="space-y-2">
          {jobs.data.items.map((job) => (
            <li key={job.id} className="rounded border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-1">
                <ProvenanceBadge kind={job.provenance} checkedAt={job.checked_at} />
                {job.deadline_passed && <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs">마감</span>}
              </div>
              <p className="mt-1 font-medium">{job.title}</p>
              <p className="text-slate-600">{job.organization} · 마감 {formatDate(job.deadline_at)}</p>
              <SourceLink url={job.original_url} />
            </li>
          ))}
        </ul>
      )}
      {jobs.state === 'ready' && jobs.data.nextCursor && (
        <button type="button" onClick={more} className="rounded border px-3 py-1 text-sm">더 보기</button>
      )}
      {moreError && <ErrorBox message={moreError} onRetry={more} />}
    </section>
  );
}

export function ContestsPanel() {
  const [contests, setContests] = useState<Load<ContestCandidate[]>>({ state: 'loading' });
  const load = useCallback(() => {
    setContests({ state: 'loading' });
    api.listContests().then(
      (page) => setContests({ state: 'ready', data: page.items }),
      (error) => setContests({ state: 'error', ...describeError(error) }),
    );
  }, []);
  useEffect(load, [load]);

  return (
    <section aria-labelledby="careers-contests" className="space-y-3">
      <h2 id="careers-contests" className="text-lg font-semibold">공모전 팀원 모집 연결 후보</h2>
      <p className="text-xs text-slate-500">모집 글은 커뮤니티 실명 모집에서 작성하며, 여기서는 연결할 공모전 ID만 확인합니다. 팀 구성·참가 신청을 대신하지 않습니다.</p>
      {contests.state === 'loading' && <Loading label="공모전을 불러오는 중…" />}
      {contests.state === 'error' && <ErrorBox message={contests.message} requestId={contests.requestId} onRetry={load} />}
      {contests.state === 'ready' && contests.data.length === 0 && <p className="text-sm text-slate-500">연결할 수 있는 공모전이 없습니다.</p>}
      {contests.state === 'ready' && contests.data.length > 0 && (
        <ul className="space-y-2">
          {contests.data.map((contest) => (
            <li key={contest.opportunity_id} className="rounded border border-slate-200 p-3 text-sm">
              <ProvenanceBadge kind={contest.provenance} checkedAt={contest.checked_at} />
              <p className="mt-1 font-medium">{contest.title}</p>
              <p className="text-slate-600">{contest.organization} · 마감 {formatDate(contest.deadline_at)}</p>
              {contest.team_link_candidate ? (
                <p className="text-xs text-emerald-700">모집 글 연결 가능 · 공모전 ID <code>{contest.opportunity_id}</code></p>
              ) : (
                <p className="text-xs text-slate-500">현재 모집 글에 연결할 수 없습니다(마감 등).</p>
              )}
              <SourceLink url={contest.original_url} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
