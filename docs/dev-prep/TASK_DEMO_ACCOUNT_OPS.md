# TASK-DEMO-ACCOUNT-OPS — 가상 DEMO 학생 2계정 운영자 생성 CLI

> **최신 실행:** 사용자 승인 `DITNOW-P0-DEMO-20261030`으로 실제 생성·로컬 HTTP·390/1280 브라우저와 정리를 수행했다. [실행 SHA·결과](TASK_P0_APPROVED_LIVE_E2E.md)를 따른다. 아래 미실행·승인 대기는 원본 도구 작성 당시 이력이며 운영 배포 승인이 아니다.

- 상태: review (코드·오프라인 테스트만). **실DB 실행·계정 생성은 NOT_RUN**이며 사람 승인 + root 절차 전 실행 금지.
- 기준 브랜치: `7f7eabb` (승인 대기 PR13/19/26/37/54/58/48/49/28 포함, main 미병합).
- 소유 파일: `services/api/app/operations/__init__.py`, `services/api/app/operations/demo_accounts.py`, `services/api/tests/test_demo_accounts.py`, 이 문서.
- 변경하지 않음: 모델·스키마·migration·auth·config·App·라우터·OpenAPI·패키지/잠금·NAV.

## 1. 실행 방식
```
# 기본: 오프라인 DRY_RUN. Settings·비밀번호·네트워크를 읽지 않는다.
uv run --locked python -m app.operations.demo_accounts

# 실제 적용(사람 승인 후 root만):
DIT_DEMO_ACCOUNT_PASSWORD_A=... DIT_DEMO_ACCOUNT_PASSWORD_B=... \
  uv run --locked python -m app.operations.demo_accounts \
  --apply --confirm-synthetic-only --approval-reference <승인참조>
```
- 비밀번호 환경 변수 이름(정확히): **`DIT_DEMO_ACCOUNT_PASSWORD_A`**, **`DIT_DEMO_ACCOUNT_PASSWORD_B`**. 기본값·argv·dotenv 없음. 12~64자, 앞뒤 공백·제어문자 금지, 서로 달라야 하며 학번을 포함하면 거부한다. 거부 시 값은 출력하지 않는다.
- DB 연결은 기존 엄격 팩토리 `app.core.db_connection.create_database_engine(Settings())`만 쓴다(`DIT_API_DB_*`, 사용자 `ditnow_app` 고정, 인증 전 검증된 TLS 강제).
- 승인 참조는 `[A-Za-z0-9][A-Za-z0-9._:-]{2,63}` 형식의 비밀이 아닌 식별자이며 출력에 그대로 기록된다.

## 2. 적용 단계 (`--apply`)
1. 인자 검사 → 주입 비밀번호 검사 → `Settings()` → 엔진 생성. 앞 단계 실패 시 뒤 단계(설정·네트워크)를 건드리지 않는다.
2. 메타데이터 준비 검사: MariaDB 11.4, `ditnow`, `utf8mb4_unicode_ci`, `CURRENT_USER()=ditnow_app`, FK/CHECK 활성, P0 16개 + legacy 9개 = **25개 테이블 InnoDB**, P0 컬럼(`schema_readiness` 재사용)과 `students` 컬럼, 보이는 트리거 0개. 레코드 조회 없음.
3. 단일 트랜잭션: 고정 합성 키만으로 충돌 검사 → 생성 → 자체 UUID 행수 재확인 → **명시적 1회 commit**.
4. commit 후 새 읽기 트랜잭션에서 자체 UUID 행수만 재확인(`post_commit_verification`).

연결 단위 가드가 `SELECT/SHOW/INSERT/SAVEPOINT/RELEASE/ROLLBACK` 외 문장(DDL·UPDATE·DELETE·GRANT 등)과 무장 전 commit을 차단한다. commit 전 실패는 전체 롤백한다. commit 시도 이후 결과 미확정은 `COMMIT_OUTCOME_UNKNOWN_REVIEW_REQUIRED`와 `committed=UNKNOWN`, commit 성공 뒤 연결 context 종료 등 실패는 `POST_COMMIT_FAILURE_REVIEW_REQUIRED`와 `committed=YES`다. 두 경우 신규 UUID·감사 UUID 등 비밀 아닌 metadata를 함께 남겨 사람이 대조할 수 있게 하며 자동 재실행·정리하지 않는다. 연결 반환 실패를 미반영(`NO`)이라고 보고하지 않는다.

## 3. 생성 행 (총 16행, 모두 신규 UUID)
| 테이블 | 행 | 내용 |
| --- | --- | --- |
| `students` (legacy 로그인 권위) | 2 | `DITDEMO_A`/`DITDEMO_B`, 이름 `[가상]학생A/B`, `dept_id` `DEMO-A/B`, `grade` 1, 기존 `chatbot.app.auth.hash_password` PBKDF2 해시 |
| `identities` | 3 | 학생 2: issuer `urn:ditnow:student-login:demo:v1`, subject=학번(정확 일치), `active`/`DEMO`. 감사 전용 운영자 1: issuer `urn:ditnow:demo-audit-operator:v1`, subject `DITDEMO_AUDIT_OPERATOR`, `disabled`/`DEMO` |
| `profiles` | 2 | `[가상]학생A`, `[가상]학생B` (운영자 없음) |
| `departments` | 2 | `DEMO-A`, `DEMO-B` 분리 학과 |
| `academic_memberships` | 2 | 각 학과, 1학년, `active`, `valid_from=적용 시각`, 종료 없음 |
| `role_assignments` | 2 | `student`·`department` 범위만. admin/교수/조교/플랫폼 역할 없음 |
| `audit_logs` | 2 | `identity_binding_approved` / `identity_binding`, actor=비활성 운영자 UUID, entity=해당 학생 canonical UUID, `DEMO` |
| `opportunities` | 1 | `[가상] 통합검증용 기회 DITNOW_DEMO_P0_INTEGRATION`, `contest`, `published`, `info_only`, `DEMO`, 공식 출처·URL·기관명 없음 |

legacy 학과·학년은 초기 필수값만 일치시키며 이후 권위는 canonical membership/role뿐이다. 운영자 identity는 사람·관리자 신원이 아니며 로그인 행·역할·프로필·학적이 없다. 감사 행만으로는 아무 권한도 생기지 않는다: 런타임은 **운영자가 검토한 audit UUID allowlist**(기본 빈 목록 → 503)를 요구한다(별도 root 소유).

## 4. 충돌 시 fail-closed
아래 중 하나라도 있으면 아무것도 쓰지 않고 `COLLISION:<종류>`로 중단한다. 자동 채택·재설정·덮어쓰기·비밀번호 재설정 없음.
- `SYNTHETIC_STUDENT_ID_EXISTS` (`DITDEMO_A/B`; MariaDB 콜레이션 별칭 포함)
- `SYNTHETIC_ISSUER_SUBJECT_EXISTS` (학생 2 + 운영자 바인딩의 digest 또는 원값)
- `SYNTHETIC_DEPARTMENT_CODE_EXISTS` (`DEMO-A/B`)
동시 실행 경합은 `students` PK·`uq_identity_binding_digest`·학과 코드 UNIQUE가 최종 차단하며 실패 시 전체 롤백된다.

## 5. root 보호 메타데이터 계약 (stdout JSON, 성공 시)
`status=APPLIED`, `commits=1`, `rows_created`, `post_commit_verification`, `approval_reference`, `issuer`, `accounts[]`(`student_id`, `identity_id`, `display_name`, `department_id`, `department_code`, `membership_id`, `academic_year`, `role_assignment_id`, `role`, `role_scope`, `audit_log_id`), `operator_identity_id`, `operator_identity`, `audit_log_ids`, `opportunity_id`, `opportunity_marker=DITNOW_DEMO_P0_INTEGRATION`, `runtime_audit_allowlist=OPERATOR_REVIEW_REQUIRED`, `secret_material=NOT_OUTPUT`.
비밀번호·해시·DSN·호스트는 출력하지 않는다. 실패 시 `{"status":"BLOCKED","code":...,"committed":"NO"|"UNKNOWN"|"YES"}` 또는 사전 차단 `{"status":"BLOCKED","code":...,"persistent_writes":0}`. `UNKNOWN`/`YES`는 위 자체 식별 metadata도 포함한다. root가 저장소 밖 보호 위치로 캡처한다.

## 6. 검증 (2026-10-30, 로컬 Windows, Python 3.13, uv 잠금)
- `uv run --locked pytest tests/test_demo_accounts.py`: 36 passed (격리 SQLite+aiosqlite, SQLAlchemy ORM)
  - 성공 원장 전체 값·단일 commit·SELECT/INSERT만·비밀번호 해시 검증·출력/로그 비밀 미노출
  - 학번·학과 코드·학생/운영자 issuer-subject 충돌, 재실행 거부(비밀번호 미변경), 중간 실패·제약 위반 전체 롤백
  - DDL·UPDATE·무장 전 commit 가드, commit 실패 UNKNOWN 보고, 기본 준비 검사의 비 MariaDB 거부
  - CLI 기본 DRY_RUN·옵션 게이트·argv 비밀번호 거부·약한/중복 비밀번호 거부가 Settings/네트워크 전에 일어남, 엔진 dispose·예외 정화, 앱 미배선
  - 독립 리뷰 P2 보완: 실제 commit 뒤 `AsyncConnection.__aexit__` 실패도 YES+자체 UUID 보존, commit event 실패는 UNKNOWN+자체 UUID 보존, 오류 원문·비밀번호 비출력. 고정 기회 marker가 제목·출력에 동일하게 포함됨.
- `uv run --locked pytest` 전체: 수정 후 **1149 passed**, 기존 Starlette 테스트 클라이언트 deprecation 경고 1개. `ruff check .`, `ruff format --check .`: 통과(187개 파일).
- **NOT_RUN**: 실제 MariaDB 연결·TLS·GRANT·25테이블 준비 검사, 실제 계정 생성, 로그인→identity bridge→개인 CRUD 종단 흐름, 런타임 audit allowlist 연결. SQLite 결과는 MariaDB 증거가 아니다.

## 7. 잔여 게이트
- 사람 승인 + root의 실제 `--apply` 실행과 메타데이터 보호 캡처.
- 런타임 identity ledger 어댑터와 audit UUID allowlist 배선(root/auth 소유). 이 CLI는 라우터·의존성을 활성화하지 않는다.
- DML 계정에서 보이지 않는 트리거는 별도 권한 검토가 필요하다.

## 8. 독립 리뷰와 수정 구분
- Codex B가 원본 HEAD `3c9959627d9831ab56eb9e98cae27ca40f6469f4`를 읽기 전용으로 검토하고 전용 34개/Ruff를 직접 통과했다. commit 이후 예외의 NO 오분류 P2와 기회 marker 계약 불일치를 보고했다.
- root의 소유권 이전 후 위 두 사항을 B가 수정하고 전용 36개를 통과했다. 수정자 자기 검토를 독립 재리뷰 완료라고 주장하지 않는다. 실제 MariaDB·계정 생성·HTTP 연결은 이 수정에서도 NOT_RUN이다.
