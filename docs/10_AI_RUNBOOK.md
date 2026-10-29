# AI 개발 오케스트레이션 실행 규정

## 1. AI 역할
- **Product Owner(사람)**: 목표·범위·정책·우선순위 확정, `main` 병합·배포 승인.
- **Planner(AI)**: FR/NFR를 의존성 DAG·태스크·테스트로 분해; 미결정 사항 명시.
- **Architect(AI)**: 공통 타입·DB 스키마·권한 정책·API 계약을 먼저 설계하고 충돌 방지.
- **Builder(AI)**: 제한된 파일 범위에서 단위 기능과 테스트 구현.
- **Reviewer(AI)**: 요구사항/보안/성능/문서 계약 일치 여부와 교차 영향 리뷰.
- **QA(AI+사람)**: 실제 브라우저/DB/2계정 테스트 증거 검증; 재현 불가면 미검증.

## 2. AI 작업 시 우선순위
1. `00_START_HERE.md`의 우선순위를 따른다.
2. 필요한 도메인의 FR와 NFR, RBAC, 스키마, 테스트 TC를 읽는다. 무관한 전체 문서를 매 태스크마다 모두 읽지 않는다.
3. `[확정]`은 변경 금지, `[설계 기본값]`은 문서에 있는 안전한 기준대로 진행, `[미결정]`은 범위 외 기능이면 보류.
4. 보안/신원/권한/민감자료/공식 대외 표시에 영향이 있는 결정을 임의 확정하지 않는다. 해당 태스크만 `BLOCKED` 처리하고 독립 태스크를 진행한다.
5. 구체화되지 않은 **장기 BASELINE** 기능에 대해 임의 스키마·API·운영 규칙을 만들어 개발하지 않는다. 상세 FRD 승인 단계로 되돌린다.

## 3. 질문 최소화 결정 규칙
- 질문하지 않고 진행: UI 토큰 내부 구현, 공통 폼 처리, 이미 정의된 필드 이름·제약, 명시된 기본값, 파일 구조 내 세부 구현.
- 가정 기록 후 진행: 서버/프런트 라이브러리 선택처럼 외부 계약을 바꾸지 않는 단기 옵션. `assumptions.md`에 근거 기록.
- 질문/차단: 학생 신분 인증 방식, 성적·출결 판정 규칙, 익명 작성자 신원 연결, 학교 공식 명칭/교직원 권한·배포 대상, 실제 서류·비밀정보 처리, 지출 발생 유료 서비스 활성화.
- 같은 질문 반복 금지: `11_DECISION_LOG.md`에 결정되면 이후 기준으로 사용.

## 4. 태스크 생성 형식 (예시; 실제 코딩 전 Planner가 생성)
```yaml
id: TASK-0042
title: 조교 공지 발행 시 학과 학년 채팅 카드 자동 전달
status: proposed # proposed / ready / in_progress / review / blocked / done
priority: P0
owner_area: notices
source_ids: [FR-NOT-001, FR-NOT-002, NFR-SEC-002, NFR-REL-002, TC-005, TC-006]
inputs: [notice_id, actor_token, audience_type, audience_id]
outputs: [notice_revision, delivery_ids]
dependencies: [TASK-AUTH-RBAC, TASK-DEPT-CHANNELS, TASK-NOTICE-MODEL]
files_allowed: [mvp/src/features/notices/**, services/api/**] # services/api는 FastAPI 제안 경로이며 아직 없음
files_forbidden: [src/features/community/**]
acceptance:
  - approved assistant can publish department-year notice
  - students in matching department-year see exactly one official reference card
  - other students cannot read the target notice or channel
  - editing the original displays the latest revision from the existing card
checks:
  - npm run typecheck
  - npm run test -- --run
  - Playwright TC-005/TC-006
proof_required: [commit_hash, tests_log, screenshot, cross_account_access_test]
retry_limit: 2
human_gate: shared_schema_or_policy_or_main_merge
```

## 5. 태스크 실행 상태기계
`proposed → ready → in_progress → review → done`; 실패/선행 미충족 `blocked`; 범위 변경은 `cancelled`로 종료 후 새 태스크.
- `ready`: 입력·권한·선행 작업·AC·관련 테스트가 명시되어 있음.
- `in_progress`: 담당 AI는 허용된 파일만 수정, 필요시 구현 범위를 분리.
- `review`: 타입/린트/테스트 결과와 변경 경로 제출.
- `done`: Reviewer 통과 + 해당 TC/실사용 시나리오 검증 + 문서-코드 상태 일치.
- 중단: 테스트 실패 2회 동일 원인 시 로그와 해결 선택지 남기고 `blocked`.

## 6. 병렬 개발 규칙
- 하나의 DB migration/auth/공통 디자인 토큰은 하나의 소유자만 변경.
- 공통 스키마/타입/API 계약을 먼저 완료한 뒤 프런트·백엔드 병렬화.
- 영역별 독립 브랜치/PR 권장; `main` merge는 담당자 승인.
- 두 브랜치가 같은 파일을 수정할 예상이 있으면 순차화.
- 검증하지 않은 문구나 외부 연동 성공을 README에 쓰지 않는다.

## 7. 실행 루프용 프롬프트
### Planner 시작 프롬프트
> `docs/00_START_HERE.md`, `01_PRD.md`, `02_FRD.md`, `03_NFR.md`, `04_POLICY_RBAC.md`, `05_DATA_MODEL.md`, `09_RELEASE_SCOPE.md`, `10_AI_RUNBOOK.md`, `11_DECISION_LOG.md`를 먼저 확인하라. 사용자의 확정 결정을 바꾸지 말고 P0를 의존성 순서대로 작은 태스크로 분해하라. 각 태스크에 source IDs, 허용 파일, 입력/출력, 완료 조건, 검사 명령, 리스크/차단 조건을 포함하라. 구현은 하지 말고 계획만 출력하라. 미결정이 없는 단순 태스크를 먼저 ready로 배치하라.

### Builder 실행 프롬프트
> 할당된 TASK ID와 연결 FR/NFR/TC, 승인된 파일 범위만 읽고 변경하라. 서버 인증·권한·유효성 검증과 테스트를 포함하라. 관련 문서의 확정 정책을 바꾸거나 모의 화면으로 성공을 가장하지 마라. 실패 시 증거와 로그를 남기며, 완료는 검증 결과로만 보고하라.

### Reviewer 실행 프롬프트
> 이 PR을 태스크의 acceptance 및 TC와 대조하라. 타 계정 접근, 익명 신원 노출, 공식 권한 승격, 중복 저장, 잘못된 데이터 흐름, 민감 키/개인정보 노출을 최우선 검사하라. 직접 실행된 테스트가 없으면 PASS 대신 NOT_RUN으로 기록하라. 문제 목록을 심각도/파일/재현 절차로 제출하라.

### Release 검증 프롬프트
> 배포된 URL과 제출 브랜치를 대상으로 심사용 계정, README 1~3 CRUD, 2계정 권한 격리, 공지 자동 배포, AI 실패 안전성, 390/1280 반응형, Lighthouse 3회를 검사하라. 실패·미실행은 증거와 함께 보고하고, 비밀값을 노출하지 마라. 배포·최종 제출은 사람의 확인 전 실행하지 마라.

## 8. 매 실행에서 남길 결과
- 작업 ID/상태, 구현 파일, commit, 테스트 명령 및 실제 로그, 미완료 위험, 관련 문서 업데이트, 다음 실행 가능한 ID.
- 반드시 `done` / `failed` / `blocked` / `not_run` 명시. '대체로 성공' 금지.
