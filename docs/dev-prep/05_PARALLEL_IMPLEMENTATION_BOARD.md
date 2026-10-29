# DIT NOW 병렬 구현 보드

2026-10-30 KST · TASK-ORCH-92 · 초기 기준 main `a86ec597`; 아래 후속 PR 상태는 2026-10-30 갱신.
fullstack-implementation·nav-doc-maintenance 적용. 관련 전체 FR 92개, NFR-SEC/PRIV/REL/UX/OPS 및 각 TC-V1은 [기능 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv)에서 연결한다.

## 최신 우선순위 — 실제 두 계정 통합 검증

사용자 지시로 신규 기능 추가보다 신규 앱 → FastAPI → 원격 MariaDB의 실제 E2E를 우선한다. 기준 main은 `f8705eac26dc12960b2689e894497e9893371ca5`이며 다음 독립 작업을 완료했다. 아래 과거 기능/병렬 세션 기록과 현재 실검증 상태를 혼동하지 않는다.

| 작업 | 실제 결과·병합 |
|---|---|
| root DB 재검증·호환 보완 | [PR #69](https://github.com/not-a-devs/ditNow/pull/69), `e97157e6ef37a6fa40fae37da013c7e9311082df`. 엄격 TLSv1.3·두 DB 계정·25개 InnoDB·기존 집계·트리거0 확인. 신원 해시 조회의 드라이버 bytes 오류를 재현·보완 후 실제 읽기 왕복/충돌 검사 성공, 전체 API1442·독립15·최종HEAD CI5 성공. 데이터 쓰기0 |
| A 계정 승인 절차 | [PR #66](https://github.com/not-a-devs/ditNow/pull/66), `82b76e52a0583f6c6036416c7aa3ca9fd618192a`. 신규16행·충돌·auditUUID2개 pin·commit불명확 처리·정리 한계 문서와 독립리뷰·CI5. 실제생성 승인과 구분 |
| B 배포 준비 | [PR #67](https://github.com/not-a-devs/ditNow/pull/67), `d42fdca73fcdee047e3a22ccdbc1c6d1ef44f231`. HTTPS·도메인·CORS·단일worker·Tailscale·비밀주입·운영rollback 절차, 독립리뷰·CI5. 실제호스팅/운영배포0 |
| F 로컬 사전 점검 | [PR #68](https://github.com/not-a-devs/ditNow/pull/68), `c5ce5182419e136bd77a1efb3dba6da81b3d2c0b`. 실제 미인증 HTTP11·Chromium390/1280·preview 화면 검사와 하네스37 성공, 독립리뷰·CI5. 자기서버 종료, 실계정/DB업무0 |

**현재 필수 승인 대기:** 신규 가상 학생 A/B와 지원 원장 총16행 생성, 성공 결과의 auditUUID2개를 검토한 로컬 업무 활성화, 격리된 로컬 검사 quota 및 HTTP/브라우저 CRUD·제한 정리 범위. 사용자에게 구체 실행 승인을 별도 요청했다. 승인 전에는 실제 계정 생성·승인 pin 주입·업무 쓰기를 실행하지 않는다.

**실제 두 계정 로그인·익명·실명 모집·개인 기회 CRUD·재로그인·소유권 격리:** 모두 NOT_RUN이다. 공개/미인증 사전 점검과 단위·SQLite·모의 HTTP·하네스 성공을 대체 증거로 사용하지 않는다. 운영 배포·외부 공개는 별도 승인 대기다. 자세한 현재 상태는 [DB 재검증](TASK_MARIADB_LIVE_REVALIDATION.md), [계정 승인](TASK_DEMO_ACCOUNT_APPROVAL.md), [로컬 사전 점검](TASK_LOCAL_E2E_PREFLIGHT.md), [배포 준비](TASK_DEPLOYMENT_PREPARATION.md)를 따른다.

## 최신 병합 상태 — 사용자 승인 반영

2026-10-30 사용자의 “다 머지해” 지시를 현재 PR의 사람 병합 승인으로 기록했다. [병합 실행 증거](TASK_PR_BATCH_MERGE_20261030.md)를 최신 기준으로 사용한다. 아래 2차 작업자 표와 승인 대기 서술은 해당 시점의 실행 이력이며 현재 실행 중 세션 수가 아니다.

- 공통 계약·DB·챗봇 안전화·신원 연결·신규 로그인·채널 보안 수정 등 기존 열린 PR 14개와 후속 #59/60/61/63을 최신 HEAD CI 및 독립 검토 후 병합했다. #19/26/37은 #54의 선행 커밋으로 main에 포함되어 병합 상태가 됐다.
- #61은 FastAPI 공통 로그인/현재 권한/핵심 CRUD 연결, #60은 신규 앱의 단일 메모리 세션과 실제 API 클라이언트 연결이다. #59는 명시적 가상 계정 생성 도구, #63은 실제 HTTP 검사 도구이며 기본 실행에서 원격 계정이나 데이터를 만들지 않는다.
- 후속 #65의 비동기 테스트 경합 수정과 #62의 브라우저 검사 하네스도 보완·독립 회귀·최신 HEAD CI를 통과해 병합했다. 이 기록까지 코드/테스트 PR 20개가 병합 상태다. 실제 시연 계정이나 브라우저 E2E를 실행했다는 뜻은 아니다.
- TLS 차단은 해제됐고, root가 명시적 migrator로 신규 테이블 16개를 적용했다. 기존 9개 테이블 정의·행 수를 보존했다. 이는 실제 웹 로그인·핵심 CRUD E2E의 증거가 아니다.
- 신규 앱 → FastAPI → 실제 MariaDB → 재조회 및 두 계정 격리의 전체 실행은 아직 NOT_RUN이다. 기능별 VERIFIED/전체 통합 완료 수를 올리지 않았다. 기존 CSV는 계층별 재감사 전의 보수적 집계다.
- 코드 병합 승인을 실제 시연 계정 생성·운영 설정 활성화·유료 서비스·배포 승인으로 확대하지 않는다.

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

## 과거 실행·리뷰·승인 대기 — 2026-10-30 2차 기록

main에는 별도 작업자의 PR #39도 `fe6e7e28d22768a256ee1723ea450d49af2a5efa`로 병합됐다. 아래 PR은 실제 작업 결과이며 열린 브랜치의 코드를 main 구현 상태에 합산하지 않는다. 단위 테스트는 메모리 fake 또는 SQLite를 사용한 범위와 실제 서버 검증을 구분한다.

| 작업 | 담당·격리 worktree | 변경 가능 영역·현재 상태 |
|---|---|---|
| TASK-I 공개 대학 안내 | Codex F + root · ditNow-public-campus | PR #32 병합. 실제 API·신규 앱 연결, 390/1280 화면·검색/필터/상세/오류 검사, 같은 HEAD CI 5개 성공. 전체 6개 FR은 PARTIAL |
| TASK-N 실제 SQLAlchemy 저장소 | Codex B 초안 → A 호환 보완 · ditNow-mariadb-integration | PR #37 HEAD27ff51759f7d105b054fc4c993370dd7ed790687. API728·FE278·CI5·독립 호환36개 PASS, root 엄격 TLS/연결 정렬 실검증 PASS. 새 migration 실행기는 아래 TASK-N2 A 단일 소유. 보안 승인 전 OPEN |
| TASK-K 커뮤니티 협업 | Claude CLI + Codex 검증 · ditNow-collaboration | PR #35 병합. 동시성·늦은 응답·자기 댓글 삭제 보완·BE93/FE57·CI 성공. 실DB/인증·전역 연결 전 |
| TASK-L 취업·프로그램 | Claude CLI + Codex 보완 · ditNow-careers | PR #36 병합. aggregate·시각·개인 상태·늦은401/403 보완 후 독립 회귀·CI 성공. 실상담·심사·기업 권한 미활성 |
| TASK-M 학사·출결 | Claude CLI 수정 + Codex F 독립 리뷰 · ditNow-academics | [PR #34](https://github.com/not-a-devs/ditNow/pull/34) 병합 `6c0cd22c32584379e65271a86a3548c8d9ef193c`. 학점/시간 충돌·요청/세션/정정 중복·StrictMode 수정 후 새 경쟁9·FE20·외부 harness를 F가 각1회 직접 재검증했다. 새 HEAD CI5 성공, 실DB/전역 업무 미연결 |
| TASK-O 생활·학생지원 | Codex A 작성 + root 독립 리뷰 · ditNow-student-life | [PR #38](https://github.com/not-a-devs/ditNow/pull/38) 병합. root BE27·FE12 직접 PASS, 같은 HEAD CI5 성공. 미마운트 가상 신청/상태·배지 조회만, 고충 본문·민감 지원·직원 처리 권한 제외 |
| TASK-P 공개 통합 검색 | Codex B + root · ditNow-public-discovery | PR #40 병합. 기존 공개 안내/시설 검색·신규 App·상세 연결, 개인정보 검색 없음 |
| TASK-Q 온라인 학습 | Codex A + F 리뷰 · ditNow-online-learning | PR #46 병합. 미활성 가상 학습/시험 모듈, 공식 성적·외부 LMS·감독 판정 차단 |
| TASK-R 공지 상세·학과 질문 | Codex F + B 리뷰 · ditNow-notice-discussion | PR #45 병합. 원본 공지 재사용·질문/댓글·메타 조회, 실제 파일/공식 답변·전역 연결 전 |
| PR #39 호환·보안 보완 | Codex A 독립 리뷰 → 기존 PR #28 통합 · ditNow-chatbot-db-safety | 타인 변경 보존. 원격 legacy DSN/TLS·seed 경계, 공통 UUID/현재 권한 미연결, auth/개인 AI 캐시 및 rate-limit 순서 보완. Q는 checkpoint 보존 후 이어감 |
| TASK-ORCH | root · ditNow-progress-update | NAV/README·보드·92행 진행표·연결 검사, 공통 router/App/OpenAPI 통합·PR/CI/리뷰 조정. DB 비밀 주입과 실제 접속은 root만 수행 |

**TLS 차단 해제**: root의 CA 지문 일치·엄격 SQLAlchemy/aiomysql 인증·SELECT1·TLSv1.3·연결 utf8mb4_unicode_ci 검사가 PASS다. 앱과 migrator 인증/GRANT를 구분 확인했다. 기존 9개 테이블·외래키·행 수만 조회했고 개인 행 값·DDL·영구 쓰기는 0이다. 비파괴 마이그레이션 실행기와 공통 신원 매핑을 준비하며 PR #13/19/26/28/37 보안 승인 대기는 유지한다.

### 당시 실행한 2차 작업자 8개

root는 통합·공통 App/라우터/OpenAPI/NAV·비밀 주입·실DB 검사만 맡는다. Codex 하위 동시 한도는 root 포함4이며, 별도의 인증된 Claude CLI 5개를 추가 실행했다. 타인의 CLI 프로세스는 이 집계에 넣지 않았다. 각 작업은 별도 worktree/브랜치이고 같은 파일을 동시에 수정하지 않는다.

| 작업자 | worktree · 브랜치 | 단일 소유 파일 범위 | 상태 |
|---|---|---|---|
| Codex A · TASK-N2 | ditNow-mariadb-migration · feat/mariadb-explicit-migration-20261030 | app/db/migration_runner.py·전용 tests·migration 문서 | 실행 중. 기존16 DDL 불변, 기본dryrun·strictTLS·별도migrator·checksum/preflight/부분실패 장부. 실제 실행 root만 |
| Codex B · TASK-IDENTITY-BRIDGE | ditNow-identity-bridge · feat/legacy-identity-bridge-20261030 | app/integrations/identity_bridge/**·전용 tests/doc | 실행 중. 기존 토큰 권위 재사용·명시 UUID 매핑, 기존 계정/역할 자동 생성 금지 |
| Codex F · TASK-FE-AUTH | ditNow-platform-login · feat/platform-login-20261030 | apps/web/src/features/auth/**·전용 doc | 실행 중. 신규 로그인/로그아웃 화면, 기본 비활성·단일 메모리 세션 콜백·공통 auth 수정 없음 |
| Claude CLI · TASK-T | ditNow-home-notifications · feat/home-notifications-firstpass-20261030 | features/action_center BE·action-center FE·전용 tests/doc | 실제 세션 실행. 원본 참조 홈·개인 알림/읽음, 외부 push/LLM 없음 |
| Claude CLI · TASK-U | ditNow-channels · feat/channels-firstpass-20261030 | features/channels FE/BE·전용 tests/doc | 실제 세션 실행. 자유 채널·공식 채널 신청, 관리자 승인/공식 배지 부여 없음 |
| Claude CLI · TASK-V | ditNow-opportunity-matching · feat/opportunity-matching-firstpass-20261030 | features/opportunity_matching BE·opportunity-matching FE·전용 tests/doc | 실제 세션 실행. 원본 기회·현재 소속 매칭/근거, 실제 AI 추천 완료 아님 |
| Claude CLI · READ-ONLY-28 | ditNow-security-readonly · detached299ec17 | 소스 쓰기0·보고 결과만 저장소 밖 수집 | 실제 독립 리뷰 세션 실행. 인증·seed·원격DB·캐시 경계, 사람 승인 아님 |
| Claude CLI · TASK-W | ditNow-classroom-races · fix/classroom-request-races-20261030 | 기존 classrooms FE·전용 doc만 | 실제 세션 실행. 전체 FE에서 반복된 요청/입력 경합의 원인 확인·회귀 보완, 테스트 재시도/생략으로 숨기지 않음 |

Codex B/F는 신원 bridge와 FE 로그인 소스를 교차 읽기 전용 리뷰한다. 공통 DB 모델/마이그레이션 수정은 A만 맡고 root가 실제 DB 실행을 맡는다. Claude 구현자는 공통 파일·DB·비밀에 접근하지 않는다. 작업 완료 후 상태는 PR/동일 HEAD CI/실제 통합 증거로 갱신하며 작업 중 결과는 main 완료로 세지 않는다.

### 최근 병합과 검증

| PR | 실제 merge SHA | 범위·검증 |
|---|---|---|
| #35 | 28cc93591985b25f3b17e94bf3fb19b26cadd7e4 | 협업 모듈, 독립 리뷰·BE93/FE57·동일 HEAD CI |
| #36 | 2dc81879173caa431303e94dea2c31ccad4b7dd1 | 취업/프로그램, 늦은401/403 보완 독립 회귀4·FE40·동일 HEAD CI |
| #40 | 36749bbd943c4086d3461b0617eab228789ab7bf | 공개 검색 실제 App/API 연결·390/1280·동일 HEAD CI |
| #45 | 6af83f2c21de42ec711544a9995878cb6bec40cc | 공지/학과 질문, 독립 BE16/FE8·동일 HEAD CI |
| #46 | 18a7846594e4d13f1e1e415eff7dc31536fc938e | 온라인 학습/가상 시험, 독립 BE25/FE12·추가 Unicode FE2·동일 HEAD CI |

현재92행: PARTIAL66 / NOT_IMPLEMENTED21 / BLOCKED5 / IMPLEMENTED0. 모듈 단위 테스트나 공개 화면 검증은 실제 인증·DB 영속성까지 완료한 기능을 뜻하지 않는다. #47 화면 공유는 BE17/FE17·독립 재리뷰·CI 통과했으나 실미디어/DB·활성화 승인 전 OPEN이다.

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

PR #32 기준은 부분 구현 34·미구현 53·차단 5였다. PR #34/38/39 당시의 과거 진행표는 **부분 구현 50·미구현 37·운영 정책 차단 5·완전 구현 0**이다. PR #39의 학번 로그인은 코드·메모리 테스트의 부분 구현이며 공통 UUID·현재 권한·엄격 TLS 통합 완료를 뜻하지 않는다. 진행 중/검토/승인 차단/일부 병합은 work_status·work_branch·work_pr·work_scope 열로 분리한다. 개별 기능 전체의 실DB·사용자 시나리오 검증은 아직 아니다.

## PR #39 독립 보안 검토와 보완 경계

Codex A가 별도 detached worktree에서 main `fe6e7e2`를 읽기 전용 검토하고 기존 AI/auth 테스트14개를 직접 통과했다. 실제 원격 연결 없이 엔진 구성과 메모리 DB를 조사한 결과는 다음과 같다. 다른 작업자의 PR을 되돌리거나 승인 기록을 삭제하지 않았다. DEC-020의 학번·초기 비밀번호 로그인과 AI 답변 통합 선택은 보존한다.

| 발견 | 근거·재현 범위 | 처리 |
|---|---|---|
| 임의 DSN이 legacy engine으로 전달 | assistant.py → chatbot db.make_engine; 무연결 생성에서 ssl/timeout 없음·hide_parameters=false | 기존 PR #28의 승인 factory 경계로 차단·호환 수정 중 |
| 공통 신원·현재 권한 미연결 | legacy students 학번 PK/auth_sessions 사용. 메모리에서 비밀번호 변경 후 기존 token 개인 응답200 재현 | 실서버 개인 원장은 승인된 공통 UUID/current grant bridge 전503; 시연 메모리 테스트와 구분 |
| seed의 원격 DDL 가능 | app.seed_demo → init_db(create_all), 학생 수만으로 기존 데이터 판별 | canonical memory 외 차단; 원격 migration은 별도 검토 절차 |
| token/개인 AI 캐시 및 rate-limit 순서 | 메모리 login/개인 AI 응답 cache-control 없음. invalid token 조회가 quota보다 먼저 실행 | private/no-store 및 DB 조회 전 제한 회귀 보완 |

위 결과는 실제 MariaDB·TLS·운영 사용자·외부 LLM 검증이 아니다. PR #28은 수정 후 독립 재리뷰·새 HEAD CI와 사람 보안 승인을 기다린다. 인증서 검증 해제·원격 DDL·운영 권한 생성은 하지 않는다.


## 과거 실행 이력 — 공개 안내·초기 DB 진단

이 절은 PR #32 전후 당시 기록이다. 현재 TLS 해제·기존9테이블·가상DML/롤백 및 A 단일 migration 소유 상태는 위 최신 표와 DB 검사 문서를 따른다.
- C/D/E PR23·20·24는 독립 재검토·같은 HEAD CI·합성 API397/웹140 통과 후 미활성 모듈로 병합했다. H 도서 PR31와 J 가상 입학 PR33도 미마운트/운영 미연결 부분이다. 운영 신원·DB 활성화 승인이 아니다.
- I 공개 안내 PR32는 기존 조회 스냅샷을 GET API·신규 `/app/information`에 연결하고 실제 브라우저 검색/필터/목록·상세/출처·오류/390·1280 검사를 수행했다. 모바일 상세 초점이 sticky 헤더 아래 숨는 결함을 수정했다.
- Claude CLI 후속 세션을 실제 시작했다: K ditNow-collaboration/feat/collaboration-firstpass-20261030, L ditNow-careers/feat/careers-programs-firstpass-20261030, M ditNow-academics/feat/academics-attendance-firstpass-20261030. 각 features 모듈·전용 FE/BE/tests·TASK 문서만 소유하며 공유 인증/DB/migration/lock은 수정하지 않는다.
- N · Codex B, ditNow-mariadb-integration/feat/mariadb-p0-persistence-20261030. 검토된 PR19/26을 격리 브랜치에서 조합해 실제 SQLAlchemy P0 저장소·비파괴 초기 migration 코드/테스트를 작성한다. 공통 모델·DB 의존성·migration은 B가 단일 소유한다. 다른 미병합 변경을 임의 채택하지 않는다.
- DB의 네트워크·양 계정 인증·SELECT·직접 GRANT·빈 schema는 Codex에서도 성공했다. 실제 async API 연결은 **BLOCKED_TLS**이며 사용자에게 CA·SAN을 요청했고 검증 해제 금지를 확인했다. [현재 DB 검사](07_DB_CONNECTIVITY_AND_ROLES.md)를 따른다. 원격 DDL/seed/CRUD 쓰기는 아직 0이다.
- PR13/19/26/28은 사람 보안 승인 대기로 유지한다. PR30은 별도 인프라 작업자가 병합한 팀원 VM 운영 정의이며 로컬 DB 컨테이너를 실행하지 않는다.
