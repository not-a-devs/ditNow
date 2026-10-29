# DIT NOW 병렬 구현 보드

2026-10-30 KST · TASK-ORCH-92 · 초기 기준 main `a86ec597`; 아래 후속 PR 상태는 2026-10-30 갱신.
fullstack-implementation·nav-doc-maintenance 적용. 관련 전체 FR 92개, NFR-SEC/PRIV/REL/UX/OPS 및 각 TC-V1은 [기능 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv)에서 연결한다.

## 목표와 완료 판단

전체 92개를 1차 구현 대상으로 관리한다. 로그인·실DB 핵심 3 CRUD·보안·배포가 최우선이며 독립 P1/P2를 병렬 진행한다. P0 완료가 개발 종료 조건은 아니다. 전체 가능한 구현 → 전체 자동 검사 → 사용자 직접 검사 → 보완·재기획을 반복한다.

[92행 상태표](06_FEATURE_IMPLEMENTATION_STATUS.csv)는 main의 기능 상태다. 브랜치의 작업 중 코드나 사전 mvp를 main 완료율로 집계하지 않는다. 최초 기준은 모두 운영 통합 미검증이다. 기존 chatbot의 시설 조회 코드는 PARTIAL 2행(상위 CAMP-001과 세부 CAMP-003)이며 두 독립 완성 기능을 뜻하지 않는다. 나머지는 NOT_IMPLEMENTED 또는 운영 정책 BLOCKED이며 각 세부 계층은 NOT_RUN이다.

| 상태 | 필요한 증거 |
|---|---|
| NOT_IMPLEMENTED | 최종 앱에 구현 없음; 계약/문서만 있음 |
| PARTIAL | FE/BE/DB 중 일부 코드만 존재; 실제 연결 미완료 |
| BLOCKED | 운영 정책/외부 접근/환경/필수 승인 미충족; 안전한 시연 별도 가능 |
| IMPLEMENTED | 필요한 FE/BE/MariaDB 연결 코드 존재; 아직 전체 검증 전 |
| VERIFIED (별도 계층) | 해당 환경의 TC·2계정·영속성·오류·회귀 증거와 HEAD/실행 기록 필요 |

문서 DOCUMENTED, 단위 TESTED, 운영 VERIFIED는 다른 사실이다. 조회 전용 공개 원문은 MariaDB N_A 사유를 쓰고 검증된 출처 스냅샷으로 가능하다. 내부 규정 미확인을 실제 학교 정책으로 만들지 않는다.

## 실행 중인 격리 작업

각 worktree는 `C:/DIT CSW/` 아래다. root는 아래와 다른 기존 작업/미커밋 파일을 건드리지 않는다. Claude CLI 2.1.312의 기존 인증을 사용하며 권한 우회·추가 비용 서비스 개설은 하지 않는다.

| 태스크/세션 | worktree · 브랜치 | 소유 파일 | 현재 상태/차단 |
|---|---|---|---|
| A · Codex pr11_independent_review | ditNow-p0-domain-contracts · feat/p0-provider-neutral-contracts-20261030 | services/api/app/db/**, schemas/p0.py·operations.py, api/dependencies.py, 공통 DB repositories, pyproject/uv.lock, auth/DB tests | PR #19 모델/인증 기반 61 테스트·CI PASS, 사람 승인 대기. 후속 DIT_API_ 설정/aiomysql·권한 분리 작업; 실제 DB 네트워크 차단 |
| B · Codex api_foundation_review | ditNow-web-shell · feat/new-platform-web-shell-20261030 | apps/web 공통 셸·라우터·디자인·lib·테스트·패키지, 아래 feature 디렉터리 제외 | PR #21 병합·27 단위 및 390/1280 실제 브라우저 검사 PASS. 후속 G 강의실 작업으로 이동 |
| C · Claude CLI | ditNow-community · feat/community-recruitment-firstpass-20261030 | app/features/community/**, test_community*.py, apps/web/src/features/community/**, TASK_COMMUNITY_IMPLEMENTATION.md | PR #23 부분 구현. 114 테스트 PASS, 독립 리뷰의 재시도/캐시·API 경로 결함 보완 중. 인증/DB 대기 |
| D · Claude CLI | ditNow-opportunities · feat/opportunity-firstpass-20261030 | app/features/opportunities/**, test_opportunities*.py, apps/web/src/features/opportunities/**, TASK_OPPORTUNITIES_IMPLEMENTATION.md | PR #20 부분 구현. 90 테스트 PASS, 독립 리뷰의 멱등 tombstone/ETag/URL 보완 중. 인증/DB 대기 |
| E · Claude CLI | ditNow-campus · feat/campus-communication-firstpass-20261030 | app/features/campus/**, test_campus*.py, apps/web/src/features/campus/**, TASK_CAMPUS_IMPLEMENTATION.md | PR #24 부분 구현. 95 테스트 PASS, 출처·공지 revision·채팅 nonce 보완 중. 실제 실시간/학적 대기 |
| F · Codex rag_integration | ditNow-rag-integration · feat/integrated-rag-adapter-20261030 | chatbot 패키징/상대 import, integrations/chatbot/**, schemas/ai.py, api/v1/ai.py, test_chatbot_integration*.py | PR #22 병합(API37·기존 챗봇130·신규 웹27). 후속 UI PR #25 및 DB 자동 DDL 안전화 분리 작업 |
| ORCH · root | ditNow-orchestration · docs/integrated-mariadb-roadmap-20261030 | 결정/NAV/README/아키텍처/로드맵/진행표/검사 스크립트, 후속 공통 router·CI 통합 | 전체 92개·공통 계약·PR/CI 조정 |

`app/` 약칭은 services/api/app/이다. 모든 PR 제목/본문/커밋은 한국어. 각 작업은 테스트 후 PR로 전달하고 root가 독립 검토·HEAD CI를 확인한다. 동일 파일 수정 금지. 마이그레이션/인증/공통 의존성은 A 단일 소유이며 F 로컬 패키지 의존성은 A 작업 후 root가 통합한다.

## 최소 공통 계약

- FastAPI 실제 `schemas/common.py`가 성공/오류 권위다. data/resource_version/server_time, 오류 code/message/field_errors/retryable/request_id. 아직 구현하지 않은 경로를 OpenAPI 실행 경로로 표시하지 않는다.
- 인증 공급자 미설정은 fail closed. 검증된 외부 issuer/subject→내부 UUID, 현재 소속·역할/소유권은 서버 원장에서 재검사한다. 테스트 fake는 tests 안에만 두고 운영 로그인으로 표시하지 않는다.
- MariaDB 최소 GRANT/제약/트랜잭션+FastAPI 범위 질의. PostgreSQL 네이티브 RLS와 SET LOCAL을 MariaDB 기능처럼 적용하지 않는다. 브라우저 DB 직접 접근 금지.
- B의 신규 frontend `src/lib/api.ts`: requestData<T>(path, init?)는 data 반환, ApiError에 code/status/requestId. feature `src/features/{community,opportunities,campus,ai}/index.tsx`는 default React component. 모듈이 아직 병합되지 않았으면 미구현 안내만 표시한다.
- C/D/E는 자기 서비스·입출력·repository Protocol·주입형 router를 작성한다. 공유 인증을 우회하여 임시 공개 CRUD를 열지 않는다. 실제 DB adapter와 통합 테스트 전 VERIFIED 금지.
- 공지 원본 한 건→대상 카드 참조, 외부 장학 제출은 자체 신고. 익명 공개 모델에 개인 식별자/소속/감사 상관값을 넣지 않는다.

## 후속 배정과 통합 순서

1. A 모델/인증 제안·B 신규 셸·F 공개 RAG를 독립 검증한다. A는 보안 승인 PR로 보류하고 B/F의 비보호 경로는 회귀·CI 성공 시 병합 가능하다.
2. C/D/E 단위 결과를 공통 계약과 대조한 뒤 별도 PR로 검토한다. DB 스키마 요청은 A에게 모으고 실제 권한 경계 병합은 승인 후 진행한다.
3. 공통 계약 승인·MariaDB 접속 준비 후 가상 로그인→핵심 3 CRUD FE/BE/DB 영속성→2계정 권한→통합/배포를 우선 검증한다.
4. 비어 있는 세션은 같은 파일을 피하여 강의실·과제·질문·출결 시연, 도서/예약, 입학 공개 안내·가상 흐름 등 진행표의 P1/P2 항목을 순서대로 배정한다. 정책 필요한 처리 대신 허용된 공개 안내부터 구현한다.
5. 가능한 전체를 자동 검사하고 사용자 직접 검수용 시나리오·환경·가상 계정을 준비한다. 사용자 승인 없이 유료 개통/배포/운영 관리자 생성 금지.

## 진행과 차단 증거

- PR #11 사용자 병합 확인: 5d08cb4d4cd92ea06dbe5404b69e894eb0a0822a.
- [PR #13](https://github.com/not-a-devs/ditNow/pull/13): Claude CLI 독립 설계 리뷰 및 MariaDB/통합 원장 정정. HEAD ea3ff0b8c2b9b413080690bb9f2b27a6a4d01632의 CI 성공. 사람 보안 승인 대기, 자동 병합 금지.
- PR #15 FastAPI 기반, #16 Python CI, #17 공개 OpenAPI·타입 검사는 main 병합 완료. 업무 로그인/CRUD/MariaDB 완료를 뜻하지 않는다.
- DEC-019의 기존 팀원 VM MariaDB11.4/Tailscale/계정 역할 확정. 프로젝트 내부 DB 컨테이너 생성 금지. 실제 TCP는 timeout, 로컬 Tailscale offline/NoState. [DB 운영 검사](07_DB_CONNECTIVITY_AND_ROLES.md)의 네트워크 복구·자격/TLS·GRANT·migration·공통 인증 게이트를 유지한다.
- Claude 세션 결과는 세션 종료 후 변경 범위/커밋/PR/검사 로그로 갱신한다. 실행 시작 사실을 성공/완료로 표시하지 않는다. AI 리뷰는 사람 공식 승인이 아니다.

수용 기준: 진행표 ID=명세 92개 집합, 중복 없음, 모든 행 계층/우선순위/차단/후속 태스크·TC 추적, mvp 완료율 제외, 공통 파일 충돌 없음. 자동 검사: `node scripts/check-feature-progress.mjs`, `node scripts/check-agent-config.mjs`, `git diff --check`.


## 후속 세션과 전체 자동 검사

- G · Codex api_foundation_review: ditNow-classrooms / feat/classrooms-firstpass-20261030. 소유 `apps/web/src/features/classrooms/**`, `services/api/app/features/classrooms/**`, 전용 테스트/태스크 문서. 분반·자료·과제·질문 시연 서비스/UI를 공통 의존성과 분리해 구현 중. 인증/DB/파일·시험·실시간 활성화는 미완료다.
- F-DB-SAFETY · ditNow-chatbot-db-safety / fix/chatbot-explicit-db-init-20261030. chatbot/ 런타임 auto DDL 제거·기존 seed/reset 안전 경계를 검토한다. 공통 원장과 충돌하는 standalone schema를 운영 DB에 생성하지 않는다. 사람 승인 PR로 보류한다.
- A-DB-CONFIG · 새 main 기준 독립 브랜치. core/config·DB 접속 설정/비동기 드라이버·services/api 의존성 잠금 단일 소유. 실제 연결·DDL·계정 생성은 미실행이다.
- ORCH · ditNow-db-operations / docs/db-network-and-integration-progress-20261030. DEC-019·DB 네트워크/역할 보고·보드·진행표·검증 상태 소유.
- root 격리 통합 검사 ditNow-firstpass-integration / test/parallel-firstpass-integration-20261030: C/D/E 합성 소스 **pytest 251 PASS, 신규 웹 타입/27 테스트/build PASS**. 아직 미병합 PR 합성의 단위/계약 검사이며 auth/DB/E2E 완료 증거가 아니다. 이 검사에서 C/D/E의 `/api/v1` 중복 prefix를 발견해 세 CLI 수정 세션을 재시작했다. 각 실제 HEAD의 CI를 다시 확인한다.
- 별도 Codex의 C/D/E 독립 리뷰에서 생성 재시도 중복, 개인 익명 응답 캐시 헤더 누락, 삭제 후 멱등 재시도 부활, 약한 ETag, 출처 URL·확인일 및 동시 공지 게시/채팅 재시도 문제가 재현됐다. 기존 성공 테스트만으로 실제 통합 완료로 올리지 않고 수정·회귀 검사한다.
