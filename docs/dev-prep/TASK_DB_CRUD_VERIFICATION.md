# TASK-DB-CRUD-VERIFY — 합성 fixture 롤백 전용 DB 검사

상태: **검증 코드 IMPLEMENTED / TESTED(오프라인)**, 작업자의 실제 MariaDB 접속·비밀값 조회·원격 실행은 **NOT_RUN**. N2/PR54 HEAD `a7859b558f899255d24709e8cf541c97a296b170`을 기반으로 세 파일만 추가한다. N54의 스키마 적용·N 저장소·인증 계약 승인과 이 검증 도구의 승인은 별개다. 사람 승인 전 자동 병합하지 않는다.

검사 코드 PR58은 main 대상 CI를 실제 실행하기 위해 main을 base로 한다. PR54 미병합 동안에는 기반 diff도 표시될 수 있으므로 먼저 해당 승인을 충족해야 한다. PR54를 건너뛰어 이 PR로 기반을 병합하지 않는다. 본 태스크가 직접 작성한 파일은 아래 세 개뿐이다.

## 범위와 소유

- `services/api/app/db/crud_probe.py`
- `services/api/tests/test_db_crud_probe.py`
- 이 문서

공통 Settings/엄격 TLS factory/모델/runner/auth/DB migration·API·NAV는 바꾸지 않는다. FR-COM-001/004, FR-OPP-004 및 FR-AUTH-002의 **합성 fixture만** 사용한다. NFR-SEC-002/003/004/005/007, NFR-PRIV-003, NFR-DATA-003, NFR-REL-001, TC-V1-COM-001/004·OPP-004의 한정 DB 검사다. 공식 권한이나 실제 사용자 신원을 부여하는 기능이 아니다.

## 기본 실행과 승인 게이트

기본 `python -m app.db.crud_probe`는 NOT_RUN을 출력하고 종료코드2로 끝난다. 다음 두 명시 opt-in이 모두 없으면 Settings·루프·engine·네트워크를 사용하지 않는다:

1. `DIT_API_RUN_CRUD_PROBE=1`: 운영자의 이 검사 실행 승인.
2. `DIT_API_CRUD_PROBE_SAFETY_REVIEWED=1`: 아래 사전 안전 검토를 **같은 대상 서버·스키마에 대해 권한 있는 운영자가 완료했다는 확인**.

두 번째 환경 변수는 승인 증거 그 자체가 아니다. 운영자는 저장소 밖의 작업 기록에 대상·기존9개 원장 보존·적용 스키마 checksum·InnoDB·트리거 검토 시각/검토자·이 실행 승인을 기록해야 한다. 비밀값/호스트/접속 문자열을 저장소·PR에 붙이지 않는다. 실행 예시의 값은 자격 정보가 아니며 접속 변수는 공통 DB 소유자가 안전한 세션에 이미 설정해야 한다.

```powershell
# 사람 승인과 사전 검토 뒤 운영자만 실행. 이 PR 작성자는 실행하지 않는다.
$env:DIT_API_RUN_CRUD_PROBE = '1'
$env:DIT_API_CRUD_PROBE_SAFETY_REVIEWED = '1'
uv run --locked python -m app.db.crud_probe
```

접속은 기존 `DIT_API_DB_*` Settings와 `create_database_engine`만 사용한다. 런타임 계정은 `ditnow_app`, MariaDB11.4/`ditnow`/엄격 CA·호스트 검증/최종 `utf8mb4_unicode_ci`를 유지한다. migration/관리자/챗봇 계정·legacy DATABASE_URL factory로 대체하지 않는다. 미설정은 engine 생성 없이 NOT_RUN이다. Windows는 기존 opt-in Selector loop factory를 사용한다. 전체 실행 시간 제한은60초다.

## 롤백을 신뢰하기 전 운영자 사전 점검

- N2의 승인된 초기 정의와 16개 P0 테이블·필수 컬럼/FK/UNIQUE/최소 GRANT가 일치해야 한다. 이름/컬럼 검사만으로 전체 제약 준비가 증명되지는 않는다.
- **16개 모두 InnoDB**이고 fixture 쓰기로 다른 저장 엔진·외부 시스템에 비트랜잭션 부작용이 발생하지 않아야 한다.
- **migration 권한 운영자가 16개 대상 테이블의 트리거가0개임을 확인**해야 한다. DML 계정은 트리거 메타데이터를 숨길 수 있으므로 DML 조회의0개를 충분한 근거로 삼지 않는다.
- 코드는 실제 연결의 버전/스키마/연결 정렬·16컬럼 준비·16개 테이블 InnoDB·보이는 트리거0을 재확인한다. 불일치하면 fixture INSERT 전에 중단한다. 기존9개 학생/학적 원장의 **행**은 읽거나 변경하지 않으며 메타데이터 확인과 구별한다.
- CREATE/ALTER/DROP/GRANT, create_all, commit, seed/reset은 이 모듈에 없다. 이 도구를 실행해 누락 스키마나 권한을 자동 수선하지 않는다.
- strict factory의 초기 연결 설정 뒤 해당 connection에만 런타임 SQL guard를 붙인다. SELECT/SHOW/SAVEPOINT/RELEASE/ROLLBACK/INSERT/UPDATE/DELETE만 허용하고 세미콜론·SET/LOCK/UNLOCK/DDL/COMMIT은 거부한다. SQLAlchemy physical commit event도 고정 오류로 차단한다. 종료 시 자신이 추가한 두 listener만 제거하여 다른 사용자/engine listener를 훼손하지 않는다. 이는 현재 검토한 어댑터의 회귀 방어이며 임의 Python/DBAPI 코드를 실행하는 sandbox가 아니다.

## 한 트랜잭션의 합성 검사

현재 실행이 생성한 무작위 UUID 두 명만 대상으로 DEMO canonical identity/profile, 한 학과, 현재 학생 소속, 학과 범위 **student 역할만** INSERT한다. 관리자 역할·legacy 학생/세션·실제 로그인 계정·학번 매핑은 만들지 않는다. 가상 기회 한 건을 같은 트랜잭션에 작성한다. 최초·최종 검사와 CRUD 조회는 이 fixture UUID 및 종속 키로만 제한하며 공개 전체 목록이나 타 사용자의 개인 레코드를 조회하지 않는다.

기존 `CurrentP0Access`, `SQLAnonymousPosts`, `SQLRecruitments`, `SQLPublicProfiles`, `SQLOpportunityCatalog`, `SQLSavedOpportunities`와 실제 도메인 서비스를 재사용한다. `P0Executor`의 일반 commit 경로를 호출하지 않고 outer connection transaction을 직접 소유하며 `AsyncSession(join_transaction_mode='rollback_only')`로 묶는다. 어댑터의 SAVEPOINT RELEASE는 최상위 commit이 아니다.

- 익명 글: 생성/본인·다른 가상 학생 조회/업데이트/CAS/중복 재시도/소프트 삭제. 공개 DTO 필드 allowlist·표시 익명·owner UUID 비노출, 다른 학생 수정404.
- 실명 모집: 생성/현재 원장 이름만 표시/조회/업데이트/CAS/중복/취소. 기존 서비스의 **취소 상태 전이**를 검사하며 물리 DELETE 구현으로 주장하지 않는다. 다른 학생 수정404.
- 개인 기회: 저장/재조회·중복 저장/본인 준비 상태·메모/항목 생성·중복·완료·삭제/tombstone/저장 삭제, 타 계정 수정404와 낡은 CAS409.
- 중첩 savepoint 내부에 가상 글+공개 projection+멱등 장부를 작성한 뒤 의도적으로 실패시켜 세 가지가 함께 사라지는지 검사한다.
- 성공·실패·취소 모두 `finally`에서 최상위 transaction을 ROLLBACK한다. commit event 예외로 SQLAlchemy transaction wrapper가 비활성화된 경우도 DBAPI rollback을 명시적으로 수행한다. 성공/일반 실패에서는 **다음 읽기 트랜잭션**에서 16개 테이블의 fixture 범위 부재를 확인하고, 확인될 때만 `committed_fixture_rows=0`을 보고한다. 취소/연결 손실/rollback·dispose 실패는 cleanup NOT_VERIFIED일 수 있으며 성공/0행 보존으로 가장하지 않는다.

결과 JSON에는 고정 검사명·상태·불리언/수치만 출력한다. DB 예외 원문·SQL·호스트·자격·fixture UUID/이름·본문·토큰을 출력하지 않는다. 새 트랜잭션 부재 검사는 fixture 경계에 대한 증거이며 서버 전체 쓰기0이나 다른 사용자의 행 보존을 전수 검사했다는 의미가 아니다.

## 실제 코드 검증

오프라인 `pytest tests/test_db_crud_probe.py`: **최종21개 PASS**. SQLite 실 SQLAlchemy 어댑터에서 전체 검사와 rollback/다음tx부재를 수행하고 실제 SQL DDL/physical commit 거부 event를 장착했다. 실패 뒤 rollback, 취소 뒤 rollback, 기본 no-network, 미설정, 잘못된 서버/스키마/collation/컬럼/InnoDB/트리거, 비밀 오류/engine dispose 실패를 확인했다. 런타임 guard 보완 후 실제 주입된 adapter의 CREATE TABLE·physical commit 시도를 차단하고 fixture 부재·외부 listener 보존을 확인하는 두 회귀를 추가했다. SQLite BEGIN shim만 DBAPI 수준에서 수행하며 운영 SQL whitelist에 BEGIN을 허용하지 않았다. 관련 두 파일 Ruff·format PASS다. 이는 MariaDB 동작·잠금·격리·동시성 증거가 아니다.

런타임 guard 보완 전 전체 API975개 PASS·OpenAPI 동일 결과를 보완 후 전체 수로 다시 주장하지 않는다. 독립 Codex 검토자는 초기19개 직접 PASS와 현재 소스의 실행 차단 finding 없음, 런타임 guard 강화를 권고했다. 새 보완은 별도 읽기 재검토·같은 HEAD CI를 거친다.

전체 회귀와 정확 PR HEAD CI 결과는 PR 본문에 별도 기록한다. 실제 원격 실행·접속·비밀값 취급은 root/승인된 운영자만 수행한다.

## 완료로 표시하지 않는 영역

운영 인증/HTTP·새 프런트 연결·legacy↔공통 UUID 승인 매핑·실제 로그인·토큰 폐기·재시작 후 committed 영속성·다중 프로세스/동시 모집 승인·화면 E2E·배포는 NOT_RUN이다. 이 도구는 서비스를 가동하거나 세 명세 CRUD의 운영 출시를 완료하는 기능이 아니다. 실제 MariaDB 검사 PASS도 rollback-only DB 증거이며 사용자 직접 검수·보안 승인·통합 게이트를 대체하지 않는다.
