# TASK-Q — 온라인 학습 1차 모듈

확인일: 2026-10-30. 범위는 FR-LMS-001/002/003, RBAC-LMS, TC-V1-LMS-001/002/003이다. 기존 92개 기능 ID와 사용자 결정을 보존한다. 관련 NFR-SEC-002/003/007, NFR-DATA-003, NFR-REL-001, NFR-UX-001, NFR-PRIV-003에 대한 제한된 도메인·계약 시험이다. 기존 v1 초안의 학교 기능 존재 VERIFIED와 내부 처리 규칙 PARTIAL을 변경하지 않는다.

## 상태와 범위

| 기능 | 이번 코드 | 미구현·차단 |
| --- | --- | --- |
| FR-LMS-001 | 현재 수강 분반의 가상 텍스트 단계 목록·본인 확인 진도, 개정과 기간·정책 검증 | 보호 미디어·파일/동영상 업로드·실제 시청시간 검증·교수 콘텐츠 저작 화면·외부 LMS |
| FR-LMS-002 | `SELF_REPORTED_DEMO` 단계 확인에 따른 가상 진행/완료 조회 | 공식 출석 판정·출결 원장 합산·교수 정정·기관 출석 보증은 BLOCKED |
| FR-LMS-003 | 가상 객관식 문항 열람, 본인 시도 시작·제출·접수 기록 재조회 | 실제 시험 운영·정답/채점 기준 공개·자동/수동 채점·점수/공식 성적·부정행위 판정·감독 |

도메인·모듈 테스트 범위는 TESTED이며 전체 FR 완료는 **PARTIAL**이다. 실서버 인증·공통 수강 원장·DB 어댑터·전역 API/화면 연결은 BLOCKED/NOT_RUN이다. 운영에 테스트 fake를 장착하지 않는다. `get_learning_actor`와 `get_learning_service`는 기본503이며 전역 router/App를 수정하지 않았다.

## 파일과 기존 기능 연결

- 백엔드: `services/api/app/features/online_learning/{models,ports,service,router}.py`.
- 검증: `services/api/tests/test_online_learning_firstpass.py`.
- 프런트: `apps/web/src/features/online-learning/api.ts`, `index.tsx`, `index.test.tsx`. 기본 export 화면이며 App 등록은 후속 공유 소유자 작업이다.
- G 강의실의 자료·과제·질문·교수 공유와 중복 구현하지 않는다. 기존 `course_offerings`·`academic_terms`의 UUID를 참조하는 `offering_id`·`term_id`만 받으며 분반/학기/수강 명단 생성 기능은 없다. 이 참조 DTO가 실제 공통 원장과 연결되었다는 뜻은 아니다.
- 기존 [FRD](../v1-draft/02_FRD.md), [권한](../v1-draft/04_RBAC.md), [추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv), [데이터/API](../v1-draft/05_DB_API.md)에 연결한다. 단일 공통 인증·학적 원장, MariaDB 및 mvp 격리 결정을 따른다. 사전 mvp 코드는 읽거나 복사하지 않았다.

## 제안 API 계약

`/api/v1/online-learning` 이하이며 이 모듈만 별도 테스트 앱에 등록해 검사한다. 모든 성공·검증·권한·예외 응답은 `Cache-Control: private, no-store`다. 공개 응답 모델에 `owner_id`, 답안 원문, 정답 키, 채점 기준, 점수를 넣지 않는다.

| 메서드·상대 경로 | 입력 | 출력 |
| --- | --- | --- |
| GET `/` | 현재 공통 actor, limit 1~50 | 본인 수강 분반 참조 목록 |
| GET `/{offering_id}` | 현재 수강·학기·가상 정책 | 가상 콘텐츠·진도·시험 요약·본인 시도 |
| PUT `/{offering_id}/units/{unit_id}/progress` | step_id, expected_revision, expected_unit_revision, expected_policy_revision, Idempotency-Key | 본인 가상 진도·공식 출석 BLOCKED |
| GET `/{offering_id}/exams/{exam_id}` | 공개/응시 기간 내 현재 수강 권한 | 문항·선택지 allowlist, 정답·rubric 제외 |
| POST `/{offering_id}/exams/{exam_id}/attempts` | expected_exam_revision, expected_policy_revision, Idempotency-Key | 본인 가상 시도 접수 |
| GET `/{offering_id}/exams/{exam_id}/attempts/{attempt_id}` | 현재 권한·부모·소유권 | 본인 상태·개정·시각, 답안/점수 제외 |
| POST `/{offering_id}/exams/{exam_id}/attempts/{attempt_id}/submit` | answers(question_id, option_id), expected_revision/시험·정책 개정, Idempotency-Key | submitted, NOT_GRADED, 공식 성적 BLOCKED |

미등록/회수된 권한403, 다른 소유자·부모·draft 자원404, 개정·기간·중복 활동·시도수 충돌409, 유효하지 않은 선택400, 미주입 정책/저장소503이다. 삭제·재개·자동 재응시·권한 부여 API를 제공하지 않는다.

## 시연 정책과 상태

`DemoLearningPolicy`는 분반·학기·revision·completion_steps·max_attempts·require_all_answers를 서버 코드가 명시 주입한다. 학교 규정이나 운영 기본값을 발명하지 않았다. 숫자 범위는 유효성/자원 제한이며, 실제 적용 값은 승인된 시연 정책이 필요하다. 런타임 기본 정책·시드는 없다.

- 진도: IN_PROGRESS → DEMO_COMPLETED. 학생의 단계 확인만 근거다. Unit/정책 개정 후 기존 진도는 STALE_DEMO이며 완료로 재해석하지 않고 후속 검토가 필요하다. 완료 원장을 초기화·자동 환산하지 않는다.
- 시도: in_progress → submitted. 같은 학생·같은 시험에 하나의 진행 시도만 허용하며, 가상 정책의 누적 시도 한도를 원자적으로 검사한다. 채점·score 상태가 없다. submitted의 본인 접수 기록은 시험 종료 후에도 현재 권한·공개 부모를 재검증해 조회한다. draft로 회수된 시험은 재시도에서도 숨긴다.
- UTC aware 시각으로 `[opens_at, closes_at)` 기간을 검사한다. 기간·상태·개정은 서버 판단이다. 브라우저의 버튼 상태는 보안 근거가 아니다.
- 텍스트 단계·문항·선택지는 가상 자료다. 실제 학교 학습 자료·교수 답안·개인 성적을 수집하지 않는다. 공식 존재 근거 URL은 기존 추적표를 보존하며 콘텐츠의 공식 원문/신뢰도라고 사용하지 않는다.

## DB/UOW 필수 계약 — 실제 어댑터 미구현

`LearningStore.transaction(user_id, offering_id)`가 현재 계정·학생 자격·학기·수강 grant·정책을 잠금 안에서 다시 읽어야 한다. `learning_units`, `learning_events`, `assessment_attempts`의 물리 설계와 migration은 공통 DB 소유자 승인 대상이며 이 PR은 DDL을 작성하지 않았다. 진도 레코드는 이벤트 기반 집계 후보이지 새 공통 학적 원장이 아니다.

1. 수강 grant/정책/부모 콘텐츠·시험 및 학생×시험 집계를 잠그고 시도수·진행 시도·CAS를 검사한다. 세션의 오래된 수강 claim을 신뢰하지 않는다.
2. 진도/시도 원장·이벤트·멱등 장부가 같은 트랜잭션에서 커밋/롤백되어야 한다. 이벤트는 가상 단계 확인/시도 시작/제출의 대상·개정·서버시각과 최소 주체만 보관하며 답안·정답·채점기준을 일반 로그·검색·AI로 복제하지 않는다.
3. `(actor, offering, operation/resource, key)` 유일성, canonical body hash, tombstone을 유지한다. 동일 키·동일 본문은 현재 권한/부모/소유권 재검증 후 접수 결과를 반환하고 다른 본문은409다. 없어진 시도를 재생성하지 않는다.
4. 정답 키/rubric은 서버 내부 레코드에만 있으며 학생 응답/OpenAPI 모델은 명시 allowlist projection이다. 단순 UI 숨김이 아니다. 실제 DB 최소 GRANT·별도 보호 저장/뷰·교수 채점 경계 검증은 아직 없다.

테스트의 RLock·롤백 snapshot·가상 이벤트 장부는 UOW 계약의 실행 가능한 예시다. MariaDB 격리수준·행 잠금·UNIQUE·교착·다중 프로세스·영속성을 검증하지 않았다.

## UX·재시도

수강 목록 로딩/빈 목록/401/403/503/일반 오류/재확인 상태를 구분한다. 본인 확인 진도와 공식 출석의 차이를 항상 표시한다. 원장 응답의 DEMO 출처·UUID·기간·부모와 공개 필드를 런타임 검사하고 정답/소유자/답안/점수 extra 필드는 거부한다. 실패한 제출의 선택·본문·멱등 키를 유지하고, 선택을 변경하면 새 키로 회전하며 불확실한 결과 재확인을 안내한다. 현재 권한 실패 시 개인 화면 상태를 지운다. 기본 공통 transport의 `/api/v1` prefix는 한 번만 적용한다.

## 검증과 출시 차단

태스크 테스트는 현재 수강·교차 계정/분반/학기·권한 회수·정책 미주입·정답 유출·부모 회수·개정·기간·중복 선택·시도 제한·롤백·동시 시작/제출·동일 요청 동시 재시도·보호 캐시·FE 의도 키/응답 검사/오류 순환을 확인한다. 명령과 실제 테스트 수·CI HEAD는 PR 본문에 기록한다.

출시 차단: 공통 UUID/session·현 수강 bridge, 승인된 시연 정책/자료, 공통 DB 어댑터와 migration·실제 두 계정 영속성·트랜잭션 시험, 교수 저작/평가 정책, 전역 router/UI 등록과 브라우저 통합 시험. 미검증 운영 기능을 IMPLEMENTED/VERIFIED로 표시하지 않는다. 인증·DB·채점·공식 출결 활성화는 별도 사람 승인이다.

## 독립 검토 보완 — Unicode 문자열 계약

PR #46의 `45d3e2c`를 읽기 전용으로 검토하면서 Pydantic이 허용하는 1500개 이모지 학습 단계가 프런트엔드의 UTF-16 길이 검사에서 거부되는 P2를 재현했다. 응답의 제목·분반·학습 단계·문항·선택지에 적용하는 공통 검사만 Unicode code point 기준으로 맞췄다. 최대 문자 수의 2배를 넘는 UTF-16 입력은 배열 변환 전에 거부하고 기존 빈 문자열/공백 거부를 유지한다. API 스키마·정책·인증·공개 필드는 바꾸지 않는다.

회귀 두 개는 이모지를 포함한 각 필드의 상한 허용과 상한 초과·ASCII/한글·공백 거부를 확인한다. 검토자가 직접 실행한 수정 전 전용 BE25/FE12 결과와 수정 후 결과를 구분한다. 보완 후 `npm test -- --run src/features/online-learning/index.test.tsx`는 14개 PASS, `npm run typecheck`, `npm run build`, `git diff --check`도 PASS다. Python 소스는 바꾸거나 전체 테스트를 반복하지 않았다. 새 CI HEAD 결과는 PR 본문에서 별도 확인한다. 실제 MariaDB·수강 원장·인증 연결과 전역 마운트 상태는 이 보완으로 변경되지 않는다.
