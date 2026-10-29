# DIT NOW AI 개발 준비 점검

작업 ID: TASK-AI-PREP-C. 확인일: 2026-10-29. 이 문서는 병합된 [v1.0 초안](../v1-draft/01_PRD.md)을 실제 저장소 구조와 대조한 준비 기록이다. 애플리케이션 코드·DB 마이그레이션·배포 설정은 변경하지 않았다.

## 현행 구조와 탐색
현재 저장소는 루트 문서/스크립트와 mvp/ 프런트 시연 앱이다. mvp/src/shared/data/store.ts는 localStorage 기반이며 mvp/src/shared/data/api/는 브라우저 모의 API 계층이다. 서버 Auth, 공유 DB, RLS, 실시간 원격 채팅, 학교 운영 원장 연동이 구현됐다는 증거는 없다. [NAV](../../NAV.md)를 v1-draft와 이 준비 기록의 새 위치에 맞춰 갱신했다.

## 프로젝트 스킬
.agents/skills/와 .claude/skills/에 각각 8개가 있다: campus-ux-audit, fullstack-implementation, implementation-planner, nav-doc-maintenance, official-service-audit, quality-release-gate, rbac-privacy-review, spec-gap-review. node scripts/check-agent-config.mjs는 두 복사본의 동일성과 메타데이터·NAV 현재 경로를 검사했고 통과했다. 스킬이 실제 코딩 태스크에서 모델에 의해 선택·적용됐는지는 이번 점검 범위 밖이다. 새 스킬이나 설정 변경은 필요하지 않았다.

## 공통 계약 선행
[DB·API 계약](../v1-draft/05_DB_API.md)은 API-ID/NOT/CHAT/COM/OPP/COURSE 등 도메인별 경로와 성공/오류 형태를 정의한다. [RBAC](../v1-draft/04_RBAC.md)은 역할+범위+자원 상태를 검증한다. [92행 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv)는 FR→API→RBAC→DB→NFR→TC를 연결한다. 실제 공유 타입/스키마와 DB migration은 아직 없다. 구현 승인 시 공통 계약의 소유자와 버전을 먼저 정하고, 그 후 프런트/서버 작업을 분리해야 한다.

## 태스크 의존성
1. OPEN-001~003의 첫 세 CRUD/스택/시연 권한 책임을 승인하고 가상 시드와 공통 오류·출처 계약을 고정한다.
2. 범위 기반 인증·역할·소속/분반 FK와 두 계정 거부 테스트를 준비한다.
3. 학생 익명 글·실명 모집·개인 기회 준비의 P0 후보 CRUD를 각각 검증한다.
4. 공지 원본/outbox→학과·학년 채널 카드→알림을 연결하고 중복·타 학과 접근을 검사한다.
5. AI 개인 브리핑은 권한 필터·출처·실패 안전성을 검증한다.
6. 강의실/화면 공유 P1은 미디어 PoC와 수강생 권한 검증 후 진행한다. 학사·입학·증명·결제·고충 실운영은 [미확정 정책](../v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md)의 차단 조건을 해소한 뒤 별도 승인한다.

이 순서는 [AI 태스크 기준](../v1-draft/10_AI_TASK_RULES.md)의 설계 제안이다. 문서 준비가 개발 착수 승인이나 기능 구현을 뜻하지 않는다.

## 실제 검증 명령과 결과
| 명령/위치 | 결과 | 범위 |
|---|---|---|
| node --check scripts/check-agent-config.mjs, 저장소 루트 | PASS | 검사 스크립트 구문 |
| node scripts/check-agent-config.mjs, 저장소 루트 | PASS, 현재 NAV 경로 49개·8쌍 스킬 | 경로/스킬 구조 |
| npm ci, mvp/ | PASS, 139개 패키지 설치 | lockfile 기반 설치 |
| npm run typecheck, mvp/ | PASS | 현재 시연 앱 타입 |
| npm run build, mvp/ | PASS, Vite 5.4.11 | 현재 시연 앱 번들 |
| npm audit --json, mvp/ | FAIL, 6건(높음 5·보통 1) | 기존 lockfile의 전체 의존성 |
| npm audit --omit=dev --json, mvp/ | FAIL, 높음 3건 | 운영 의존성 |

보안 검사에서 @remix-run/router, react-router, react-router-dom의 높음 등급이 운영 의존성에 포함된다. 전체 검사에는 postcss, vite의 높음과 esbuild의 보통도 포함된다. npm audit 출력은 수정 가능성을 표시하지만 패키지 변경·회귀 테스트는 이 문서 작업에서 하지 않았다. 릴리스 전 별도 의존성 업데이트 태스크와 재검증이 필요하다. 이 검사는 현재 패키지 상태이며 새 명세의 안전성을 증명하지 않는다.

## 모노레포 구조 판단
[기존 AI 환경 점검](../research/09_AI_DEVELOPMENT_ENVIRONMENT.md)의 apps/web, packages/contracts, supabase/migrations·functions, tests 제안은 여전히 유효한 후보이나 DFLT-001/OPEN-002의 기술 선택 전 실제 경로로 만들지 않는다. mvp/는 현행 시연 기준으로 보존하고, 계약→서버/DB→화면 연동·회귀→승인된 위치 이전 순서로 진행한다. 독립 services/api는 별도 스택 결정이 있을 때만 후보로 검토한다.

## 미해결·다음 태스크
OPEN-001~003, 실제 학교 원장/권한 정책, README의 AI 길찾기 중심 설명과 통합 캠퍼스 비전 충돌은 미해결이다. 첫 개발 태스크를 만들기 전 소유자 승인 기록과 P0 범위 결정이 필요하다. 보안 의존성 업데이트는 기능 구현과 분리한 별도 PR에서 다루고, npm audit 및 현재 타입/빌드 회귀를 게이트로 둔다. 실제 배포·브라우저·DB/두 계정 검증은 NOT_RUN이다.
