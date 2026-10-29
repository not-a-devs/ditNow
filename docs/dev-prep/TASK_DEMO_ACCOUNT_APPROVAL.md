# TASK-DEMO-APPROVAL-PREFLIGHT — 가상 계정 생성·로컬 통합 검증 승인 체크리스트

> 작성·코드 대조: 2026-10-30. 기준 `main`: `f8705eac26dc12960b2689e894497e9893371ca5`.
> **상태: DOCUMENTED / 실제 계정 생성 승인 대기.** 이 문서·PR의 병합이나 과거 코드 병합 승인을 실행 승인으로 사용하지 않는다.
> 작성자는 실제 비밀 파일·DB·계정·서버 활성화에 접근하지 않는다. 실행은 별도 명시적 승인을 받은 root 운영자만 수행한다.

## 1. 이번 승인에서 검토할 범위

아래 A~D는 사람에게 제시할 **승인 요청 항목**이다. 체크하지 않은 항목을 승인된 것으로 간주하지 않는다. 승인 날짜·승인자·대화/티켓 참조·실행 HEAD·운영자를 저장소 밖 보호 기록에 남긴다. 비밀값과 실제 접속 주소를 PR에 적지 않는다.

- [ ] **A — 가상 데이터 생성:** `ditnow`에 아래 신규 16행만 INSERT하고 한 번 명시적으로 commit하는 것을 승인한다. 기존 행 충돌 시 중단하며 덮어쓰기·채택·비밀번호 재설정은 하지 않는다.
- [ ] **B — 로컬 런타임 활성화:** 성공 결과를 검토한 뒤 두 학생의 승인 감사 UUID만 로컬 allowlist에 pin하고, strict TLS를 유지하는 loopback API·신규 `apps/web`를 단일 프로세스로 실행하는 것을 승인한다.
- [ ] **C — 실제 통합 검증:** 이 두 가상 계정으로 localhost HTTP 보안 검사와 390/1280 브라우저의 익명 글·실명 모집·개인 기회 준비 CRUD, 타 소유자 접근 거부, 토큰 폐기를 검사하는 것을 승인한다. 현재 요청 제한에 맞는 격리 검증 서버의 quota/페이싱도 실행 전에 명시한다.
- [ ] **D — 제한된 정리:** 검사기가 이번 실행에서 생성·확인한 본인 소유 marker 자료만 API로 정리하고 발급 세션을 폐기하는 것을 승인한다. 아래 잔여물·실패 경계를 이해한다.

**이번 목록에 포함하지 않는 것:** MariaDB 사용자/GRANT 생성·변경, 관리자/교수/조교 권한, 실제 학생 정보, 추가 시드, DDL·migration 재실행, 기존 데이터 수정, 원격 웹/API 공개·배포, 유료 서비스/외부 LLM 호출, 계정 제거·비밀번호 초기화·전역 reset. 가상 계정은 MariaDB의 로그인 사용자가 아니라 기존 테이블의 플랫폼 레코드다. DB 접속 자체는 승인된 사설망을 사용하되 웹/API 검사 대상은 loopback으로 제한한다.

기존 [DEC-016~020](../11_DECISION_LOG.md), [운영 절차](../10_AI_RUNBOOK.md), [P0 계약](../v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md)을 바꾸지 않는다. `OPEN-003` 전체 역할 생성 책임·권한 정책이 해결됐다는 뜻도 아니다.

## 2. 생성 대상: 정확히 16행

근거는 [시더 소스](../../services/api/app/operations/demo_accounts.py)의 `STUDENTS`, `PLANNED_ROWS`, `insert_rows`, `metadata`다. UUID는 실행 시 새로 생성하며 사전 고정된 값으로 꾸미지 않는다.

| 테이블 | 신규 행 | 승인할 값·범위 |
| --- | ---: | --- |
| `students` | 2 | `DITDEMO_A`, `DITDEMO_B`; `[가상]학생A/B`; 초기 호환 필드 `DEMO-A/B`, grade 1; 기존 PBKDF2 헬퍼의 해시만 저장 |
| `identities` | 3 | 학생 2행은 `active`·`DEMO`. 감사 actor 1행은 `disabled`·`DEMO`이며 로그인 불가 |
| `profiles` | 2 | 학생 가상 표시 이름만. 감사 actor 프로필 없음 |
| `departments` | 2 | 코드 `DEMO-A`, `DEMO-B`; 이름 `[가상] 통합검증 학과A/B`; `DEMO` |
| `academic_memberships` | 2 | 각 학생의 해당 학과·1학년·`active`; 적용 시각부터 유효, 종료일 없음; `DEMO` |
| `role_assignments` | 2 | 각 해당 학과 범위의 `student`만; `active`·`DEMO`; 플랫폼/관리자 역할 없음 |
| `audit_logs` | 2 | 학생 identity별 승인 연결 기록. 아래 정확한 issuer·subject·actor·event 계약 사용 |
| `opportunities` | 1 | `[가상] 통합검증용 기회 DITNOW_DEMO_P0_INTEGRATION`; `contest`·`published`·`info_only`·`DEMO`; 공식 기관/출처 URL 없음 |
| **합계** | **16** | 기존 학생·세션·학적·자료의 복제/UPDATE/DELETE 없음 |

### 신원 연결과 승인 pin

- 학생 issuer는 정확히 `urn:ditnow:student-login:demo:v1`, subject는 정확히 `DITDEMO_A` 또는 `DITDEMO_B`다. 이메일·학과 코드·이름으로 자동 연결하지 않는다.
- 감사 actor issuer는 `urn:ditnow:demo-audit-operator:v1`, subject는 `DITDEMO_AUDIT_OPERATOR`다. 별도 `students` 로그인 행·프로필·학적·역할은 **0개**다.
- 감사 행은 `event=identity_binding_approved`, `resource_kind=identity_binding`, `actor_id=위 disabled actor UUID`, `entity_id=각 학생 identity UUID`, `source_kind=DEMO`다.
- 이 actor나 감사 행을 만드는 행위만으로 사람 승인 권위가 생기지 않는다. **사람 승인 기록 + root가 검토한 두 audit UUID pin**이 필요하다.
- legacy `students`는 학번·비밀번호·세션 권위다. 초기 학과/학년 호환 값은 맞추지만 이후 현재 소속·학년·역할 권위는 canonical membership/role이다. 오래된 legacy 필드로 권한을 부여하지 않는다.

## 3. 생성 전 중단 조건과 메타데이터 확인

root가 실행 직전에 확인하고 증거의 날짜·HEAD·고정 결과 코드만 공개 보고한다. 이 문서는 원격 검증의 새로운 성공 증거가 아니다.

- [ ] 승인 A의 명시 기록과 실행 HEAD를 확인했다. 현재 HEAD가 기준에서 바뀌었다면 시더·DB 모델·권한/런타임 변경을 다시 검토했다.
- [ ] root가 합성 키 충돌의 실제 읽기 전용 조회에서 발견한 aiomysql/PyMySQL bytes 매개변수 `TypeError` 호환 보완이 병합되고 새 HEAD CI를 통과했다. 보완 브랜치의 조회 성공은 root의 별도 보고이며 문서 작성자의 원격 검증이나 계정 생성 증거가 아니다. 보완 전 기준 main으로 생성하지 않는다.
- [ ] 접속 계정은 기존 DML 전용 `ditnow_app`이다. migrator 자격 증명을 앱/시더 환경에 넣지 않았다. 실제 GRANT 검토는 별도 운영 증거로 확인했다.
- [ ] `DIT_API_DB_*` strict factory, 승인 CA/호스트명 검증, 인증서 검증 필수 설정을 유지했다. 연결 문제를 `verify=false`·평문 fallback·관리자 계정으로 해결하지 않는다.
- [ ] `VERSION()`은 MariaDB 11.4, `DATABASE()`는 `ditnow`, connection collation은 `utf8mb4_unicode_ci`, `@@foreign_key_checks=1`, `@@check_constraint_checks=1`이다.
- [ ] 아래 25개 요구 테이블이 모두 있고 InnoDB이며 P0 컬럼과 legacy `students` 필수 컬럼이 준비됐다. 예상 밖 스키마/변경이 있으면 자동 승인하지 않고 운영자가 검토한다.
- [ ] 시더에서 보이는 해당 테이블 trigger가 0개다. DML 계정의 metadata 가시성만으로 전체 trigger 부재를 단정하지 않고 root가 권한 있는 별도 읽기 검토로 확인했다.
- [ ] 기존 9개 정의와 기존 레코드 보존 조건을 확인했다. 실제 개인 자료를 덤프하지 않고 필요한 이름·정의·집계만 별도 보호 기록으로 비교한다.
- [ ] 고정 충돌 키가 없다. 충돌 시 비밀번호 reset·upsert·기존 행 채택·임의 suffix 생성으로 우회하지 않는다.

| 확인 묶음 | 테이블 이름 |
| --- | --- |
| 기존 9개 | `auth_sessions`, `courses`, `course_sessions`, `enrollments`, `exams`, `graduation_rules`, `graduation_rule_categories`, `question_logs`, `students` |
| P0 16개 | `identities`, `profiles`, `departments`, `academic_memberships`, `role_assignments`, `anonymous_posts_private`, `opportunities`, `recruitments`, `saved_opportunities`, `opportunity_check_items`, `audit_logs`, `anonymous_posts_public`, `community_idempotency_claims`, `opportunity_check_idempotency`, `saved_opportunity_status_events`, `recruitment_applications` |

충돌 검사는 `DITDEMO_A/B`(DB collation상 동등한 값 포함), 학생 2개·감사 actor 1개의 issuer/subject 원문 또는 digest, `DEMO-A/B` 코드다. 하나라도 있으면 `SYNTHETIC_STUDENT_ID_EXISTS` / `SYNTHETIC_ISSUER_SUBJECT_EXISTS` / `SYNTHETIC_DEPARTMENT_CODE_EXISTS`로 중단한다. PK·digest·코드 UNIQUE 충돌도 rollback하며 동시 실행을 성공으로 간주하지 않는다.

## 4. 승인 전 가능한 오프라인 단계

아래는 `services/api/`에서 실행한다. 첫 명령은 인자 없이 기본 DRY_RUN이며 Settings·비밀번호·네트워크를 읽지 않는다. 두 번째는 격리 SQLite/대역 기반 회귀다. 어느 것도 실계정 생성 증거가 아니다.

```powershell
uv run --locked python -m app.operations.demo_accounts
uv run --locked pytest -q tests/test_demo_accounts.py
```

기대 DRY_RUN: `mode=DRY_RUN`, `connection=NOT_RUN`, `settings=NOT_READ`, `passwords=NOT_READ`, `persistent_writes=0`, `required_tables=25`, 위 16행 계획. 테스트의 실제 파일/결과는 아래 작성 작업 검증란에서 확인한다.

## 5. 승인 A 이후: root의 명시적 한 번 실행

1. 승인 참조는 비밀이 아닌 3~64자 `[A-Za-z0-9][A-Za-z0-9._:-]{2,63}`로 정하고 별도 실제 승인 기록과 연결한다. 문자열을 넣는 것 자체는 승인이 아니다.
2. root가 OS 환경으로 `DIT_API_ENVIRONMENT=development`와 완전한 `DIT_API_DB_HOST/PORT/NAME/USER/PASSWORD/TLS_CA_FILE/CONNECT_TIMEOUT`을 주입한다. 이름은 `ditnow`, 사용자는 `ditnow_app`, 포트 기본 3307, 접속 timeout은 최대 5초다. 실제 주소·CA 경로·비밀번호는 문서/argv/저장소에 넣지 않는다.
3. `DIT_DEMO_ACCOUNT_PASSWORD_A`, `DIT_DEMO_ACCOUNT_PASSWORD_B`를 별도 안전한 방식으로 주입한다. 서로 다르고 12~64자, 앞뒤 공백·제어문자·두 학생 학번 포함이 없어야 한다. 기본값·명령행 인자·dotenv는 사용하지 않는다. 값·해시를 출력하지 않는다.
4. 다음은 **승인 후 root만 실행할 명령 예시이며 이 문서 작성 중에는 실행하지 않는다.**

```powershell
# services/api/; 환경 비밀값은 사전 승인된 방식으로 별도 주입
uv run --locked python -m app.operations.demo_accounts `
  --apply --confirm-synthetic-only --approval-reference APPROVAL_REFERENCE
```

5. 결과 JSON은 root의 저장소 밖 보호 위치에 보관한다. 정상 조건은 `status=APPLIED`, `commits=1`, `rows_created`가 표와 일치, `post_commit_verification=MATCHED`다. 새 transaction에서 이번 UUID만 다시 조회하며 그 읽기 transaction은 rollback한다.
6. stdout의 `accounts[].audit_log_id` / `audit_log_ids`, 각 student·identity·department UUID, `operator_identity_id`, `opportunity_id`를 root가 서로 대조한다. 비밀/원문 응답이나 pin 목록을 PR에 붙이지 않는다. `runtime_audit_allowlist=OPERATOR_REVIEW_REQUIRED`는 자동 승인 완료가 아니다.

### Commit 결과에 따른 분기

| 결과 | 운영자 조치 |
| --- | --- |
| commit 전 실패, `committed=NO` | 무변경/rollback 결과 확인. 원인·충돌을 해결하기 위한 별도 검토 후에만 재시도 판단 |
| `COMMIT_OUTCOME_UNKNOWN_REVIEW_REQUIRED`, `committed=UNKNOWN` | **재실행 금지.** 출력된 이번 계획 UUID를 사용한 별도 승인된 읽기 확인으로 성공/부분 상태를 판정 |
| `POST_COMMIT_FAILURE_REVIEW_REQUIRED`, `committed=YES` | 이미 생성됐을 수 있으므로 reset/재실행 금지. 이번 UUID·후속 읽기/정리 결과 검토 |
| `status=APPLIED`이지만 후속 검증 `MISMATCH_REVIEW_REQUIRED` 또는 `NOT_VERIFIED_REVIEW_REQUIRED` | exit 0만으로 완료 처리하지 않는다. 런타임 pin/HTTP 단계를 중단하고 검토 |

시더는 INSERT만 허용하고 한 번 명시적으로 commit한다. 이는 DML 생성 절차이며 MariaDB DDL의 원자 rollback을 주장하는 문서가 아니다. 자동 DROP/DELETE/UPDATE/GRANT/reset·실패 시 무한 재실행은 없다.

## 6. 승인 B 이후: 로컬 API·웹 설정 순서

1. 생성 결과와 사람 승인 기록이 일치하고 현재 canonical 학적·student 역할과 disabled/role0 감사 actor를 확인한다.
2. `DIT_API_P0_IDENTITY_APPROVAL_IDS`에 **학생의 audit_log_id 정확히 2개**를 JSON 배열로 로컬 주입한다. identity UUID·operator UUID·opportunity UUID를 넣지 않는다. 기본 `[]`는 유지하며 결과를 검토하기 전 pin하지 않는다.
3. 승인된 로컬 프로세스에서만 `DIT_API_P0_RUNTIME_ENABLED=true`, `DIT_API_P0_SCHEMA_APPROVED=true`를 설정한다. 스키마 attestation은 실제 readiness/GRANT 검토를 대체하지 않는다. 누락/불일치 시 503을 정상 차단으로 취급한다.
4. `DIT_API_CORS_ORIGINS`에는 실행 web origin 하나를 정확한 JSON 배열로 지정한다(예: `["http://localhost:5173"]`). host alias를 섞지 않고 wildcards·쿠키 인증은 쓰지 않는다. Authorization/If-Match/Idempotency-Key와 PUT/PATCH/DELETE가 실제 CORS에서 허용되는지 확인한다.
5. root가 로컬 검증 서버의 `DIT_API_ASK_RATE_LIMIT_PER_MIN` 또는 실행 페이싱을 검토·기록한다. 기본 20/분은 전체 검사·토큰 정리에 부족할 수 있다. 하네스가 제한을 자동 변경하지 않으며 429를 성공 처리하지 않는다. 이 선택은 운영 quota 변경 승인이 아니다.
6. API는 strict DB 설정을 유지하고 loopback에 단일 worker로 실행한다. Windows에서는 기존 승인된 Selector helper를 사용하며 reload·전역 event-loop policy 변경을 추가하지 않는다.

```powershell
# services/api/; 승인된 로컬 설정을 주입한 후 root만 실행
uv run --locked uvicorn app.main:app --loop app.core.event_loop:new_event_loop `
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
# 별도 터미널 apps/web/; 승인된 API base와 origin을 일치시킨다
npm run dev -- --port 5173
```

프런트 API base는 [웹 실행 안내](../../apps/web/README.md)의 `VITE_API_BASE_URL`에 승인된 API의 `/api/v1` 포함 URL을 설정한다(예: `http://127.0.0.1:8000/api/v1`). `VITE_*`는 공개 값이므로 비밀을 넣지 않는다. README의 과거 기반 단계 상태 설명보다 이번 통합 계약의 현재 코드와 [런타임 기록](TASK_P0_LIVE_API_IMPLEMENTATION.md)을 대조한다. legacy `DIT_API_DATABASE_URL`로 strict factory를 우회하지 않는다. 외부 LLM 설정/호출이나 개인 학적 RAG 연결을 이번 CRUD 검증의 선행 조건으로 만들지 않는다. 공개 조회 동작과 실제 개인 RAG 권한 승인 상태는 별개다.

## 7. 승인 C·D 이후: HTTP → 실제 브라우저 → 정리

환경의 실제 비밀번호는 시드 비밀번호와 같아야 하며 값은 OS 환경으로만 주입한다. 각 도구의 상세 규칙은 [HTTP 검사](TASK_P0_SECURITY_E2E.md)와 [브라우저 하네스](TASK_P0_BROWSER_E2E.md)를 따른다.

| 단계 | root가 준비할 설정·판정 |
| --- | --- |
| HTTP opt-in | `DIT_API_RUN_P0_SECURITY_CHECK=1`, `DIT_API_P0_SECURITY_CHECK_APPROVED=1`; `DIT_API_P0_CHECK_BASE_URL`은 port를 명시한 loopback **origin**(예: `http://127.0.0.1:8000`) |
| HTTP 대상 | `DIT_API_P0_CHECK_A_STUDENT_ID=DITDEMO_A`, `_B_STUDENT_ID=DITDEMO_B`, 각 `_A_PASSWORD`/`_B_PASSWORD`; `_OPPORTUNITY_ID`는 승인된 생성 결과, `_OPPORTUNITY_MARKER=DITNOW_DEMO_P0_INTEGRATION` (모두 `DIT_API_P0_CHECK_` 접두사) |
| HTTP 실행 | `services/api/`에서 `uv run --locked python scripts/verify_p0_security.py`; 기본 close sample은 끔 |
| HTTP 판정 | `PASS_HTTP_SCOPE`만 해당 실행 범위 성공. 무인증 401, B의 A 수정/삭제 거부, 익명 신원 미노출, revision/멱등 충돌, 새 토큰 재조회, 정리/토큰 401 확인. `overall_project=NOT_VERIFIED` 유지 |
| 브라우저 opt-in | `P0_E2E_RUN=1`, `P0_E2E_WEB_URL`은 정확한 loopback origin, `P0_E2E_API_URL`은 같은 API의 `/api/v1` 포함 base |
| 브라우저 대상 | `P0_E2E_STUDENT_A_ID/PASSWORD`, `P0_E2E_STUDENT_B_ID/PASSWORD`, `P0_E2E_OPPORTUNITY_ID`; 위 두 계정·승인 공고만 주입. close·스크린샷 기본 끔 |
| 브라우저 실행 | `tests/e2e/`에서 `npm ci`, `npm test`, 필요한 경우 root가 Chromium 설치 후 `node run.cjs`; 390/1280 각각 실제 UI와 API 재조회 검사 |
| 보고 | PASS/FAIL/INCOMPLETE/NOT_RUN을 분리. 비밀·토큰·원문 응답·실제 접속 주소를 저장소에 올리지 않는다. 보호된/마스킹된 증거만 root가 검토 |

- 하네스 실행 전 공고가 `DEMO`·정보 제공 전용·정확한 marker인지 확인한다. A가 이미 저장한 기존 행은 건드리지 않으며 사전조건 실패 시 중단한다. 검증 간 정리가 완료되지 않으면 다음 검사로 덮지 않는다.
- 새로고침은 메모리 로그인 세션을 폐기한다. 로그인 필요 안내에서 다시 로그인한 뒤 서버의 같은 자료를 재조회하는 흐름이다. reload 자동 로그인이나 localStorage 인증을 기대하지 않는다.
- HTTP·UI로 발급된 토큰은 finally에서 모두 logout하고 `/auth/me` 401을 확인한다. 리디렉션·외부 origin·개인 응답 no-store 누락·알 수 없는 생성 응답·정리 실패를 숨기지 않는다.
- 본인 ID뿐 아니라 **현재 marker와 소유권**까지 재확인한 이번 자료만 API로 삭제한다. 익명 글은 논리 삭제, 모집은 `open→cancelled` 논리 취소다. 물리 원장·멱등 claim·tombstone·상태 이력 등은 남을 수 있다.
- **초기 16개 가상 시드 행과 DEMO 공고는 정리 대상이 아니다.** 세션 폐기는 계정 제거가 아니다. 전체 DB rollback/초기화/원상복구를 약속하지 않는다.
- `closed→cancelled`는 기존 409이므로 close 표본은 기본 미실행한다. 별도 승인해 켜면 closed 잔여 행을 숨기지 않고 HTTP NOT_VERIFIED / 브라우저 INCOMPLETE로 남긴다.
- 정리 상한·marker 불일치·응답 손실이 생기면 자동 재실행/대량 삭제 대신 중단·보고한다. 별도 확인이나 시드 계정 제거에는 다시 구체 범위 승인이 필요하다.

## 8. 실행 후 완료 기록과 중단/종료

- [ ] 생성 결과의 한 번 commit 및 자기 UUID 후속 count MATCHED, 기존 자료 보존 증거를 확인했다.
- [ ] root가 검토한 두 audit UUID만 pin했고 A/B 현재 자기 DTO·서로 다른 학과·DEMO를 확인했다.
- [ ] HTTP 결과와 실제 MariaDB 증거, 브라우저 390/1280 결과를 구분해 기록했다. 단위/SQLite/모의 HTTP 성공을 실DB 성공으로 대체하지 않았다.
- [ ] 생성한 본인 marker 자료 정리·잔여 기록·토큰 폐기 결과를 기록했다. 종료/정리 실패는 FAIL/INCOMPLETE/미검증 그대로다.
- [ ] 검증이 끝나면 로컬 서버를 종료하고 해당 프로세스의 비밀번호·pin·opt-in 환경을 제거했다. 재활성화·계정 제거를 자동 수행하지 않는다.
- [ ] 서버 재시작 후 영속성·실운영 세션/요청 제한·배포·성능·전체 92개 운영 기능 등 미수행 범위를 NOT_RUN으로 남겼다.

관련 요구사항: FR-AUTH-001, FR-COM-001/004, FR-OPP-001/004; NFR-SEC-001~004, NFR-PRIV-001, NFR-DATA-002, NFR-REL-001, NFR-PERF-002; TC-001/002/003(모집 CRUD 부분)/004/014/018. 기존 [QA 기본 계정 목록](../08_TEST_QA.md)의 교수/조교/세 학생 전체 시나리오를 이 두 계정 생성으로 충족했다고 표시하지 않는다.

## 9. 이 문서 작성 작업의 검증

현재 작업은 승인 자료의 코드 대조와 문서 검증이다. 2026-10-30, 위 기준 HEAD의 Windows/Python 3.13.3에서 다음을 직접 실행했다. 설치는 `uv --locked --offline` 캐시만 사용했다.

| 검사 | 실제 결과 |
| --- | --- |
| `uv run --locked --offline python -m app.operations.demo_accounts` | PASS: DRY_RUN, Settings/비밀번호 NOT_READ, connection NOT_RUN, persistent_writes 0, 계획 16행/25테이블 |
| `uv run --locked --offline pytest -q tests/test_demo_accounts.py` | **36 passed**; 격리 SQLite·대역 회귀이며 원격 DB 검증 아님 |
| `node scripts/check-agent-config.mjs` | PASS: 실제 경로 100개·미러 skill 8개 |
| `node scripts/check-feature-progress.mjs` | PASS: 92개 기준선·92행 보존, 오류 0 |

실제 비밀 조회·DB 연결·계정 생성·런타임 활성화·실제 HTTP/브라우저·외부 LLM·배포는 **NOT_RUN**이다. 상대 링크·diff와 PR HEAD의 CI 결과는 PR에서 기록한다. NAV·공통 운영 보드와 다른 태스크 문서는 이 단일 파일 작업의 소유 범위 밖이므로 수정하지 않는다.

추가 근거: [계정 운영 코드·이전 검증](TASK_DEMO_ACCOUNT_OPS.md), [런타임 계약](TASK_P0_LIVE_API_IMPLEMENTATION.md), [DB 운영 증거](07_DB_CONNECTIVITY_AND_ROLES.md), [API 실행 안내](../../services/api/README.md), [시더 테스트](../../services/api/tests/test_demo_accounts.py).
