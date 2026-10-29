// FR-JOB-001~004 · FR-OPP-005~006 first pass. Not mounted in the global App yet; every state
// comes from the server (no local mock). Until root mounts API-JOB with auth and DB, requests
// fail closed (503) and the not-ready state is shown. This module creates no login or session.
import { useCallback, useState } from 'react';
import { ApiError } from '../../lib/api';
import { EmployerDraftPanel, ProfilePanel, ProgramsPanel } from './PrivatePanels';
import { ContestsPanel, JobsPanel } from './PublicPanels';
import { AREA_LABEL, authCode, type PrivateArea } from './ui';

type Block = { code: 'UNAUTHORIZED' | 'FORBIDDEN'; requestId?: string };

export default function CareersPage() {
  const [blocked, setBlocked] = useState<Partial<Record<PrivateArea, Block>>>({});

  const onAuthError = useCallback((area: PrivateArea, error: unknown) => {
    const code = authCode(error);
    if (!code) return;
    const requestId = error instanceof ApiError ? error.requestId : undefined;
    setBlocked((current) => ({ ...current, [area]: { code, requestId } }));
  }, []);

  // Recovery remounts the panels from scratch; nothing from before the 401/403 is restored.
  const recheck = useCallback((area?: PrivateArea) => {
    setBlocked((current) => {
      if (!area) return {};
      const rest = { ...current };
      delete rest[area];
      return rest;
    });
  }, []);

  const entries = Object.entries(blocked) as Array<[PrivateArea, Block]>;
  const unauthorized = entries.find(([, block]) => block.code === 'UNAUTHORIZED');
  const forbidden = entries.filter(([, block]) => block.code === 'FORBIDDEN');
  // 401 anywhere removes every private panel; 403 removes only the affected panel.
  const allowed = (area: PrivateArea) => !unauthorized && !blocked[area];

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">취업·진로</h1>
        <p className="text-sm text-slate-600">공개 채용 공고 검색, 가상 진로 요약, 프로그램 가상 신청, 기업 채용의뢰 초안(시연)입니다. 실제 기관 제출·채용·고용 확인을 하지 않습니다.</p>
      </header>

      {unauthorized && (
        <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <p>로그인이 필요합니다. 공통 로그인이 연결되기 전에는 개인 기능을 사용할 수 없어 개인 화면을 표시하지 않습니다.</p>
          {unauthorized[1].requestId && <p className="mt-1 text-xs">요청 ID: {unauthorized[1].requestId}</p>}
          <button type="button" onClick={() => recheck()} className="mt-2 rounded border border-amber-400 px-2 py-1 text-xs">로그인 상태 다시 확인</button>
        </div>
      )}
      {!unauthorized && forbidden.length > 0 && (
        <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {forbidden.map(([area, block]) => (
            <p key={area}>
              {AREA_LABEL[area]}: 이 계정에는 권한이 없어 화면을 표시하지 않습니다.
              {block.requestId && <span className="ml-1 text-xs">(요청 ID: {block.requestId})</span>}
              <button type="button" onClick={() => recheck(area)} className="ml-2 rounded border border-amber-400 px-2 py-0.5 text-xs">권한 다시 확인</button>
            </p>
          ))}
        </div>
      )}

      <JobsPanel />
      <ContestsPanel />
      {allowed('profile') && <ProfilePanel onAuthError={onAuthError} />}
      <ProgramsPanel canApply={allowed('applications')} onAuthError={onAuthError} />
      {allowed('employer') && <EmployerDraftPanel onAuthError={onAuthError} />}
    </div>
  );
}
