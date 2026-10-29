# AI 개발 환경 점검과 모노레포 이전 제안

> 2026-10-29 현재 작업 트리 점검. **설계·문구 제안**이며 `docs/11_DECISION_LOG.md`의 확정/미결정 상태를 바꾸지 않는다. 원격 배포·본선 코드 재사용 가능성은 검증하지 않았다.

작업 ID: `TASK-AI-ENV-001` (문서·도구 정합성 점검). 영향 영역: 탐색 문서, 에이전트 스킬, 검사 스크립트. 연결 결정: DEC-001, DEC-014, DFLT-001, OPEN-001~003. 완료 조건: 실제 경로와 스킬 복사본 검사 통과, 기존 앱 검증 명령 통과, 미확정 구조와 README 수정안을 명확히 기록.

## 확인된 현재 상태

- 저장소는 단일 Git 루트이며 `docs/`와 `mvp/`가 있다. `mvp/package.json`은 React/Vite/TypeScript 프런트엔드의 `dev`, `typecheck`, `build`, `preview`만 정의한다.
- `mvp/src/shared/data/store.ts`는 브라우저 `localStorage`와 `BroadcastChannel`을 사용한다. `mvp/src/shared/data/api/`는 브라우저 안의 모의 서비스 계층이다. `mvp/src/app/auth.tsx`의 라우트 보호는 클라이언트 UI 처리다. 서버 인증, DB, RLS의 구현 증거가 아니다.
- `NAV.md`의 현재 경로는 `scripts/check-agent-config.mjs`로 검사한다. 제안 경로는 현재 파일로 표시하지 않는다.
- `.agents/skills/`와 `.claude/skills/`에는 동일한 8개 `SKILL.md`가 있다. Codex 0.165.0의 `codex debug prompt-input`은 8개를 프로젝트 스킬로 노출했다. Claude Code 2.1.312의 `/skills` 검색에서도 각 8개가 `project` 항목으로 표시됐다. 모델을 호출하는 실제 작업 수행까지는 검사하지 않았다.

검증 기록: `node --check scripts/check-agent-config.mjs`와 `node scripts/check-agent-config.mjs` 통과(현재 NAV 경로 검사, 8쌍 동일성·메타데이터 검사), `cd mvp && npm run typecheck` 통과, `cd mvp && npm run build` 통과. 별도 단위 테스트·lint 명령은 `mvp/package.json`에 없다. 브라우저 시연·서버/DB 검증은 이번 문서 작업에서 실행하지 않았다.

## 문서와 규칙 정합성

| 쟁점 | 근거 | 판단·처리 |
| --- | --- | --- |
| 제품 방향 | `docs/01_PRD.md` §1~2, `docs/11_DECISION_LOG.md` DEC-001~014 | 신규 독립형 통합 캠퍼스 플랫폼이 확정 방향이다. `AGENTS.md`와 `CLAUDE.md`는 이를 유지한다. |
| 범위/완료 표현 | `docs/00_START_HERE.md` 상태 구분, `docs/09_RELEASE_SCOPE.md`, `mvp/README.md` | 장기 설계 범위와 사전 프런트 프로토타입을 구분해야 한다. 두 에이전트 규칙은 서버/DB 완료를 주장하지 않도록 명시한다. |
| 기술 스택 | `docs/06_ARCHITECTURE.md` §1, `docs/11_DECISION_LOG.md` DFLT-001/OPEN-002 | Supabase 계열은 설계 기본값이며 확정이 아니다. `NAV.md`의 이전 `services/api/`·`infra/db/` 표기는 확정 아키텍처로 오해될 수 있어 제안 경로를 기본값에 맞춰 고쳤다. |
| 문서 권위 | `docs/00_START_HERE.md`, `docs/10_AI_RUNBOOK.md` | 제안 문서를 확정 결정으로 승격하지 않는 규칙과 일치한다. 배포/병합 권한은 팀에 있다. |
| 기존 문서 내부 | `docs/06_ARCHITECTURE.md` §3, `docs/10_AI_RUNBOOK.md` 예시 | `src/`·`supabase/`는 당시 권장 구조/태스크 예시이고 현재 실제 경로가 아니다. 신규 모노레포 제안이 승인되면 예시 경로를 함께 갱신해야 한다. |

## 목표 구조 제안 (아직 디렉터리를 만들지 않음)

```text
ditNow/
  apps/web/                  # 검증된 단계에서 mvp 프런트 이전
  packages/contracts/       # 공유 요청·응답·도메인 타입과 스키마
  supabase/migrations/       # DB 스키마·RLS·시드 (DFLT-001 선택 시)
  supabase/functions/        # 권한이 필요한 서버 동작 (DFLT-001 선택 시)
  tests/                     # 계약·통합·브라우저 검사
  docs/                      # 기존 명세와 결정 기록
  scripts/                   # 저장소 검사·지원 도구
  mvp/                       # 이전 검증 및 승인 전까지 그대로 보존
```

이 구조는 프런트엔드, 서버 함수, DB 마이그레이션을 **한 Git 저장소에서 버전 관리**한다. `services/api/`의 독립 API 서버와 `infra/db/`는 FastAPI 등 별도 스택을 팀이 결정할 경우의 대안이다. 현재 README의 FastAPI 표기만으로 그 선택을 확정하지 않는다. `docs/05_DATA_MODEL.md`와 `docs/04_POLICY_RBAC.md`를 DB/RLS 설계 입력으로 쓰되, 실제 구현과 검증은 별도 태스크다.

## 보존형 단계별 이전 계획

| 단계 | 작업 | 완료 근거/게이트 |
| --- | --- | --- |
| 0. 기준선 | `mvp/`의 `typecheck`·`build` 결과와 현재 시연 흐름을 기록하고 파일/라우트 목록을 고정 | 현행 UI 회귀 기준 확보. 앱 코드는 이동하지 않음 |
| 1. 결정 | OPEN-001 첫 3 CRUD와 OPEN-002 스택/호스팅, OPEN-003 시연 권한 책임자를 팀이 결정 | `docs/11_DECISION_LOG.md`에 승인자·날짜·영향 기록 |
| 2. 계약 | `packages/contracts/`의 API/도메인 계약, 오류 형태, 역할 범위와 테스트를 먼저 정의 | `docs/02_FRD.md`, `03_NFR.md`, `04_POLICY_RBAC.md`, `08_TEST_QA.md`의 ID와 추적 가능 |
| 3. 데이터·서버 | 선택한 스택의 마이그레이션, RLS/서버 권한, 인증, 시드, 공식 공지 참조 이벤트 구현 | 타 계정/타 학과 접근 차단, DB 영속, TC-001~008 중 해당 항목 실검증 |
| 4. 프런트 연동 | 기존 `mvp/src/shared/data/api/` 함수 계약을 기준으로 서버 클라이언트를 단계별 연결. 화면별 플래그/별도 브랜치로 전환 | 각 흐름의 로딩·오류·권한·새 세션 회귀 확인. 모의 계층은 비교 기준으로 보존 |
| 5. 위치 이전 | 앱이 서버를 통해 동일 동작하고 팀이 승인하면 `mvp/`를 `apps/web/`로 한 번에 이동하고 import·배포 설정·문서 경로 갱신 | 이전 전후 빌드/브라우저 시연 동등성, Git diff 리뷰. 그 전에는 이동 금지 |
| 6. 릴리스 | CI와 QA 증거, README 실제 기능 표, 배포 설정을 정리 | 사람의 병합·배포 승인과 공식 대회 규정 확인 |

## 루트 README 수정 제안 (미적용)

| 현재 문구/영역 | 실제·명세와의 차이 | 권장 수정 |
| --- | --- | --- |
| AI 길찾기 중심 한 줄 소개와 기능 1~3 | PRD §1~2, DEC-001~013의 통합 플랫폼 방향과 README 첫 3 CRUD 후보(DFLT-007)가 다름 | 첫 문장을 **“학사·수업·공지·학과 소통·기회·협업을 연결하는 독립형 통합 캠퍼스 플랫폼의 사전 프로토타입”**으로 제안. 해커톤 첫 3기능은 OPEN-001 승인 후 확정 |
| 자연어 비서, 실시간 위치 경로, RAG/파인튜닝, Kakao Map API | 현재 `mvp/` 코드와 의존성에서 구현·연동 증거가 없고 FRD의 AI는 개인 데이터 기반 브리핑 | 현재 기능 목록에서 빼고 “장기 검토/미구현”으로 구분. 해당 기술을 확정 스택으로 표시하지 않음 |
| FastAPI 백엔드, 시설 DB 검색 흐름 | 현재 서버 코드/`requirements.txt`/DB 마이그레이션이 없음; DFLT-001은 Supabase 제안 | 기술 스택 표를 “현재: React/Vite/TS/Tailwind 브라우저 프로토타입; 서버·DB: 미구현, 기술 선택 미확정”으로 교체 |
| 루트 `npm install`, `pip install -r requirements.txt`, 루트 `.env`, 루트 `npm run dev` | 루트 `package.json`/`requirements.txt`가 없으며 실제 실행은 `mvp/` | 실행 예시를 `cd mvp`, `npm ci`, `npm run dev`로 교체. 환경 변수는 `mvp/.env.example`과 실제 사용 코드 확인 후 작성 |
| 실제 수강신청 기반 시간표·현재 학점/졸업학점 | `mvp/`는 시드 계정·브라우저 데이터이며 실제 학교 학사 시스템과 미연동 | “시연 데이터로 보는 시간표”로 표시하고 학점/졸업요건은 구현 증거 확인 전 삭제 또는 계획으로 이동 |
| 개발 과정 AI 활용 내역 | README의 RAG 파이프라인 구현 서술을 뒷받침할 코드가 없음 | 실제 사용한 도구·산출물만 기록하고 미검증 항목은 제거 |

수정 순서: 팀이 README 제품 포지셔닝과 OPEN-001/002를 결정 → 확정된 문구를 루트 README에 반영 → `mvp/README.md`의 “Supabase로 교체해야”와 “서버 계층” 표현도 **설계 기본값/브라우저 모의 계층**으로 명확히 수정 → 문서·코드·시연 증거 재검토. 기존 README와 명세는 이 점검에서 덮어쓰지 않았다.

## 잔여 결정과 위험

- OPEN-001~003, OPEN-008은 팀 승인 전이다. 제품명/CI, 스택, 첫 3기능을 이 문서에서 확정하지 않는다.
- 현재 `mvp/`의 탭 간 동기화는 동일 브라우저 저장소 범위다. 다른 장치·계정 간 서버 실시간 채팅, 실제 학교 신원, DB 격리의 증거로 사용하면 안 된다.
- Codex와 Claude Code의 스킬 **발견**은 새 로컬 세션에서 확인했다. 스킬을 모델이 실제 작업에 선택·적용하는 동작은 비용이 드는 모델 호출 없이 검증할 수 없어 별도 실제 태스크에서 확인해야 한다.
- 본선 사전 코드 재사용/제출 규정은 `docs/00_START_HERE.md`와 공식 최신 안내를 별도 확인해야 한다.
