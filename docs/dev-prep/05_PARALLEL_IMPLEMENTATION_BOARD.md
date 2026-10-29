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

## 현재 실행·리뷰·승인 대기 — PR #32 병합 기준

main은 `3535e0179f306ab027334010ae2ca4592cd3558d`이다. 아래 PR은 실제 작업 결과이며 열린 브랜치의 코드를 main 구현 상태에 합산하지 않는다. 단위 테스트는 메모리 fake 또는 SQLite를 사용한 범위와 실제 서버 검증을 구분한다.

| 작업 | 담당·격리 worktree | 변경 가능 영역·현재 상태 |
|---|---|---|
| TASK-I 공개 대학 안내 | Codex F + root · ditNow-public-campus | PR #32 병합. 실제 API·신규 앱 연결, 390/1280 화면·검색/필터/상세/오류 검사, 같은 HEAD CI 5개 성공. 전체 6개 FR은 PARTIAL |
| TASK-N 실제 SQLAlchemy 저장소 | Codex B · ditNow-mariadb-integration | [PR #37](https://github.com/not-a-devs/ditNow/pull/37), HEAD bf4adc1262e8a84307d43f5c1d529cfab37c0072. 공통 DB 모델·migration 제안·저장소·접속 코드 단일 소유. 전체 API537·CI5 성공, Codex F 독립 리뷰 수정 완료. 사람 보안 승인 전 OPEN, 원격 적용 0 |
| TASK-K 커뮤니티 협업 | Claude CLI 작성·별도 리뷰·수정 세션 · ditNow-collaboration | [PR #35](https://github.com/not-a-devs/ditNow/pull/35). collaboration FE/BE/tests만 소유. 독립 리뷰 BE76·Ruff PASS, 동시성 오류 계약/古い応答/ID 경계/자기 댓글 삭제 등 보완 중. 실제 DB/인증·전역 화면 연결 전 |
| TASK-L 취업·프로그램 | Claude CLI 작성·별도 리뷰·수정 세션 · ditNow-careers | [PR #36](https://github.com/not-a-devs/ditNow/pull/36). careers FE/BE/tests만 소유. 독립 리뷰 BE100 PASS, 한도 aggregate 잠금/손상 시각/개인 상태 폐기 등 보완 중. 실상담·심사·기업 권한 활성화 차단 |
| TASK-M 학사·출결 | Claude CLI 수정 + Codex F 독립 리뷰 · ditNow-academics | [PR #34](https://github.com/not-a-devs/ditNow/pull/34). academics FE/BE/tests만 소유. root와 F가 BE40·FE31 직접 PASS했으나 학점/시간 충돌·중복 요청/세션·StrictMode 결함을 별도 재현해 병합 보류·보완 중 |
| TASK-O 생활·학생지원 | Codex A 작성 + root 독립 리뷰 · ditNow-student-life | [PR #38](https://github.com/not-a-devs/ditNow/pull/38) 병합. root BE27·FE12 직접 PASS, 같은 HEAD CI5 성공. 미마운트 가상 신청/상태·배지 조회만, 고충 본문·민감 지원·직원 처리 권한 제외 |
| TASK-P 공개 통합 검색 | Codex B 후속 · ditNow-public-discovery | discovery BE/FE/tests·전용 태스크 문서. 기존 공개 안내/시설 검색을 재사용한다. 공유 router/App/OpenAPI는 root 소유, 개인정보 검색 없음 |
| TASK-Q 온라인 학습 | Codex A · ditNow-online-learning | online_learning BE·online-learning FE·전용 tests/태스크 문서. 기존 분반을 참조하는 가상 진도·온라인 학습/시험, 공식 성적·외부 LMS·감독 판정 차단 |
| TASK-R 공지 상세·학과 질문 | Codex F · ditNow-notice-discussion | notice_discussion BE·notice-discussion FE·전용 tests/태스크 문서. 기존 공지 원장 재사용, 학과 질문/댓글·안전 메타 조회, 공식 답변/파일 저장 차단 |
| TASK-ORCH | root · ditNow-progress-update | NAV/README·보드·92행 진행표·연결 검사, 공통 router/App/OpenAPI 통합·PR/CI/리뷰 조정. DB 비밀 주입과 실제 접속은 root만 수행 |

DB의 현재 환경 차단은 **BLOCKED_TLS** 하나다. 네트워크·양 계정 직접 인증/SELECT·GRANT·빈 스키마는 확인했다. 사용자가 CA/SAN을 요청했으며 인증서 검증을 해제하지 않는다. 원격 DDL·seed·CRUD 쓰기는 0이다. 별개의 사람 보안 승인·실제 로그인 정책 게이트는 그대로 유지한다. PR #13/19/26/28/37은 자동 병합하지 않는다.

모든 작업은 별도 worktree/브랜치이며 공통 인증·DB 모델·migration은 현재 TASK-N의 B만 변경한다. K/L/M/O/P는 공통 파일을 변경하지 않고 PR로 전달한다. AI 독립 리뷰는 사람의 공식 승인이 아니다.

## 최초 병렬 배정 이력

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

`app/` 약칭은 services/api/app/이다. 모든 PR 제목/본문/커밋은 한국어. 각 작업은 테스트 후 PR로 전달하고 root가 독립 검토·HEAD CI를 확인한다. 위 최초 배정의 A 공통 DB 소유권은 TASK-N을 시작하며 B에게 명시적으로 이전했다.

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
- DEC-019의 기존 팀원 VM MariaDB11.4/Tailscale/계정 역할 확정. 프로젝트 내부 DB 컨테이너 생성 금지. 초기 TCP timeout/offline 기록은 이후 재검사 성공으로 대체됐다. [DB 운영 검사](07_DB_CONNECTIVITY_AND_ROLES.md)의 최신 TLS·migration·공통 인증 게이트를 유지한다.
- Claude 세션 결과는 세션 종료 후 변경 범위/커밋/PR/검사 로그로 갱신한다. 실행 시작 사실을 성공/완료로 표시하지 않는다. AI 리뷰는 사람 공식 승인이 아니다.

수용 기준: 진행표 ID=명세 92개 집합, 중복 없음, 모든 행 계층/우선순위/차단/후속 태스크·TC 추적, mvp 완료율 제외, 공통 파일 충돌 없음. 자동 검사: `node scripts/check-feature-progress.mjs`, `node scripts/check-agent-config.mjs`, `git diff --check`.


## 후속 세션과 전체 자동 검사

- G · Codex api_foundation_review: ditNow-classrooms / feat/classrooms-firstpass-20261030. PR #27을 bb5e2380feb0a6c05cc1bf054d54e1535c7aff9d로 병합했다. 분반·자료·과제·질문의 미마운트 서비스/UI/단위 검사만 포함한다. 인증/DB/파일·시험·실시간 활성화는 미완료다.
- F-DB-SAFETY · ditNow-chatbot-db-safety / fix/chatbot-explicit-db-init-20261030. chatbot/ 런타임 auto DDL 제거·기존 seed/reset 안전 경계를 검토한다. 공통 원장과 충돌하는 standalone schema를 운영 DB에 생성하지 않는다. 사람 승인 PR로 보류한다.
- A-DB-CONFIG · ditNow-db-configuration / feat/mariadb-connection-contract-20261030 · PR #26. core/config·DB 접속 설정/비동기 드라이버·services/api 의존성 잠금 단일 소유. 61 단위 검사 및 같은 HEAD CI 성공; 사람 승인 대기. 실제 연결·DDL·계정 생성은 미실행이다.
- ORCH · ditNow-db-operations / docs/db-network-and-integration-progress-20261030. DEC-019·DB 네트워크/역할 보고·보드·진행표·검증 상태 소유.
- root 격리 통합 검사 ditNow-firstpass-integration / test/parallel-firstpass-integration-20261030: C/D/E 합성 소스 **pytest 251 PASS, 신규 웹 타입/27 테스트/build PASS**. 아직 미병합 PR 합성의 단위/계약 검사이며 auth/DB/E2E 완료 증거가 아니다. 이 검사에서 C/D/E의 `/api/v1` 중복 prefix를 발견해 세 CLI 수정 세션을 재시작했다. 각 실제 HEAD의 CI를 다시 확인한다.
- 별도 Codex의 C/D/E 독립 리뷰에서 생성 재시도 중복, 개인 익명 응답 캐시 헤더 누락, 삭제 후 멱등 재시도 부활, 약한 ETag, 출처 URL·확인일 및 동시 공지 게시/채팅 재시도 문제가 재현됐다. 기존 성공 테스트만으로 실제 통합 완료로 올리지 않고 수정·회귀 검사한다.
- C/D/E의 후속 Claude CLI 수정은 실제 완료·Push됐다(C 5d41809 / D 5cd3858 / E bf82870). root가 재리뷰·각 HEAD CI·합성 테스트 후 처리한다. 이 작업의 단위 저장소는 테스트 fake이며 DB 권한/영속성을 검증하지 않았다.
- PR #19의 추가 Claude 읽기 전용 코드 리뷰 시도는 900초 timeout으로 결과가 없었다(NOT_RUN). 이전 PR #11의 완료된 Claude 설계 리뷰와 구분한다. 자동 반복하지 않았고 PR #19는 사람 보안 승인 전 열린 상태로 유지한다.
- H · Codex B: ditNow-library / feat/library-firstpass-20261030. FR-LIB-001~004의 가상 카탈로그·본인 대출/연장·희망도서·공간 예약, 기능 전용 FE/BE/tests만 소유. 실제 DB·운영 규정 활성화는 차단한다.
- I · Codex F: ditNow-public-campus / feat/public-campus-information-20261030. FR-WEB-001~004/DEPT-007~008의 공개 원문 출처를 갖춘 소규모 스냅샷·검색·상세 API/UI. 담당자 쓰기·교수 실명/최신성 추정·비공개 API는 사용하지 않는다.

PR #32 기준은 부분 구현 34·미구현 53·차단 5였다. PR #38까지 반영한 최신 진행표는 **부분 구현 40·미구현 47·운영 정책 차단 5·완전 구현 0**이다. 진행 중/검토/승인 차단/일부 병합은 work_status·work_branch·work_pr·work_scope 열로 분리한다. 개별 기능 전체의 실DB·사용자 시나리오 검증은 아직 아니다.


## 최신 실행 갱신 — 공개 안내·DB 실제 진단
- C/D/E PR23·20·24는 독립 재검토·같은 HEAD CI·합성 API397/웹140 통과 후 미활성 모듈로 병합했다. H 도서 PR31와 J 가상 입학 PR33도 미마운트/운영 미연결 부분이다. 운영 신원·DB 활성화 승인이 아니다.
- I 공개 안내 PR32는 기존 조회 스냅샷을 GET API·신규 `/app/information`에 연결하고 실제 브라우저 검색/필터/목록·상세/출처·오류/390·1280 검사를 수행했다. 모바일 상세 초점이 sticky 헤더 아래 숨는 결함을 수정했다.
- Claude CLI 후속 세션을 실제 시작했다: K ditNow-collaboration/feat/collaboration-firstpass-20261030, L ditNow-careers/feat/careers-programs-firstpass-20261030, M ditNow-academics/feat/academics-attendance-firstpass-20261030. 각 features 모듈·전용 FE/BE/tests·TASK 문서만 소유하며 공유 인증/DB/migration/lock은 수정하지 않는다.
- N · Codex B, ditNow-mariadb-integration/feat/mariadb-p0-persistence-20261030. 검토된 PR19/26을 격리 브랜치에서 조합해 실제 SQLAlchemy P0 저장소·비파괴 초기 migration 코드/테스트를 작성한다. 공통 모델·DB 의존성·migration은 B가 단일 소유한다. 다른 미병합 변경을 임의 채택하지 않는다.
- DB의 네트워크·양 계정 인증·SELECT·직접 GRANT·빈 schema는 Codex에서도 성공했다. 실제 async API 연결은 **BLOCKED_TLS**이며 사용자에게 CA·SAN을 요청했고 검증 해제 금지를 확인했다. [현재 DB 검사](07_DB_CONNECTIVITY_AND_ROLES.md)를 따른다. 원격 DDL/seed/CRUD 쓰기는 아직 0이다.
- PR13/19/26/28은 사람 보안 승인 대기로 유지한다. PR30은 별도 인프라 작업자가 병합한 팀원 VM 운영 정의이며 로컬 DB 컨테이너를 실행하지 않는다.
