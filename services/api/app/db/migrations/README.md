# P0 MariaDB 초기 스키마 검토안

TASK-N · FR-AUTH-001/002, FR-COM-001/004, FR-OPP-001/003/004 · NFR-SEC-002/004/005, NFR-PRIV-001/003, NFR-REL-001/003.

`0001_initial.review.sql`은 **16개 논리 원장의 검토용 DDL**이다. 이 원본 파일은 수정하지 않는다. 애플리케이션 import와 시작 시 자동 DDL은 없다. 기존 테이블을 변경하는 업그레이드 마이그레이션이 아니며 DROP·GRANT·계정·시드를 제공하지 않는다. TASK-N2는 이 16개 CREATE만 별도 승인된 migration 세션에서 적용할 수 있는 명시 실행 후보를 추가한다. 코드·오프라인 테스트와 실제 적용 여부는 별개다.

## 원장 및 확장 근거

기존 PR #19의 11개 원장(identities, profiles, departments, academic_memberships, role_assignments, anonymous_posts_private, recruitments, opportunities, saved_opportunities, opportunity_check_items, audit_logs)을 보존한다. 실제 P0 Protocol의 원자성 계약을 위해 다음 5개를 추가 제안한다.

| 추가 원장 | 목적 | 현재 구현 경계 |
| --- | --- | --- |
| anonymous_posts_public | 학생 응답용 작성자 없는 projection | private/public 원자 쓰기 및 공개 읽기 분리 |
| community_idempotency_claims | actor·method·path·key별 생성 중복 방지 | 원문 namespace 재비교, 삭제 후에도 claim 유지 |
| opportunity_check_idempotency | 개인 체크 항목 중복 생성 및 삭제 재생 방지 | actor·opportunity·operation·key, tombstone 유지 |
| saved_opportunity_status_events | 개인 준비 상태와 변경 이력 동시 저장 | 상태 갱신 실패/감사 실패 시 전체 rollback |
| recruitment_applications | 향후 동일 모집·동일 지원자 중복 방지용 원장 | **신청·승인 기능 미구현**, 현재 API에서 사용하지 않음 |

`recruitments`의 field/roles/accepted_count, `opportunities`의 조직·대상·게시상태·첨부 메타·신청 시작·선택적 마감일은 이미 존재하는 기능 Protocol과 맞춘다. 체크리스트에는 UNIQUE(saved_opportunity_id, sort_order)를 둔다. 승인자·관리자·실제 학생 자료는 생성하지 않는다.

## 운영 적용 전 게이트

- MariaDB는 DEC-016의 확정 제품이다. 과거 BLOCKED_TLS와 이후 root의 엄격 Selector 연결·읽기 진단은 [운영 검사](../../../../../docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)를 따른다. TASK-N2 작업자의 실제 접속·DDL은 NOT_RUN이다. 진단 성공이 이 실행 후보의 운영 승인이나 안정성 검증을 대신하지 않는다.
- CA·hostname 검증과 N의 pre-authentication TLS guard를 그대로 재사용한다. 인증서 검증 해제·평문 fallback은 허용하지 않는다.
- 현재 대상은 기존 legacy9 테이블을 보존하며 제안된16 테이블이 없는 `ditnow`다. 다른 DB·이름 충돌·예상 밖 객체·기존9 누락은 차단한다. 백업·복구·동시 DDL 작업 중지 및 적용 담당자·승인 범위를 확인한다. raw SQL 파일을 기존 DB에 blind apply하지 않는다.
- 앱 계정에는 DML만, migration 계정에는 별도 작업 세션에서만 DDL 권한을 사용한다. 앱에 migrator 자격증명을 전달하지 않는다. 실제 GRANT 검증과 관리자·시연 인증 발급 승인은 별도다.
- UUID CHAR(32), UTC DATETIME(6), InnoDB, utf8mb4/utf8mb4_unicode_ci를 제안한다. 연결 `SET NAMES`도 동일 collation으로 명시한다. SQLAlchemy 바인딩 매개변수는 로그에서 숨긴다.
- identity와 멱등 namespace는 길이 프레임 SHA-256 인덱스를 사용하고 원문을 정확히 재비교한다. collation의 대소문자 무시가 다른 identity/key를 합치지 않게 한다. 해시 충돌은 다른 사용자로 매핑하지 않는다.
- **실제 MariaDB의 FK/CHECK/unique·동시 요청·격리·deadlock·재시작 지속성 검증은 NOT_RUN**이다. SQLite는 MariaDB 행 잠금과 격리 수준을 증명하지 않는다.

## 오프라인 재생성 및 명시적 읽기 검사

`app.db.schema.initial_schema_sql()`은 네트워크 없이 현재 ORM의 검토용 DDL을 생성한다. 원격 연결을 자동 실행하는 pytest는 없다.

담당자가 인증서·권한을 검증한 뒤 runtime 앱 계정의 `DIT_API_DB_*` 환경 변수를 비밀 저장소에서 주입하고, `DIT_API_RUN_DB_INTEGRATION=1`을 명시한 프로세스에서만 다음을 실행할 수 있다.

```powershell
uv run --locked python -m app.db.live_check
```

이 명령은 TLS 검증 연결, 버전·연결 collation·스키마명 boolean 확인과 테이블/열 이름 검사만 한다. 운영 레코드 조회·DDL·시드·영구 쓰기는 하지 않는다. 출력은 비밀값·호스트·원본 SQL 오류를 포함하지 않는다. `column_names_ready`는 제약·인덱스·GRANT·업무 CRUD의 완료를 뜻하지 않는다. 기본 opt-in 미설정 시 연결 없이 종료한다.

## 관련 구현 및 근거

- 트랜잭션 실행기/권한/저장소 경계: [DB 구현 안내](../README.md).
- 실제 runtime 연결 후보: `app.core.db_connection.create_database_engine`의 async SQLAlchemy+aiomysql 및 강제 TLS. 기존 PR #19의 `app.db.session` 동기 도우미는 호환 검토용이며 runtime에 mount하지 않는다.
- 공식 기술 근거(2026-10-30 확인): [SQLAlchemy MariaDB 방언](https://docs.sqlalchemy.org/en/20/dialects/mysql.html), [AsyncSession.run_sync](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#running-synchronous-methods-and-functions-under-asyncio), [aiomysql 연결 옵션](https://aiomysql.readthedocs.io/en/stable/connection.html), [MariaDB 문자셋·collation](https://mariadb.com/docs/server/reference/data-types/string-data-types/character-sets/setting-character-sets-and-collations).

## TASK-N2 명시적 실행 후보 — 검토·사람 승인 전 자동 실행 금지

`app.db.migration_runner`는 별도 CLI이며 서버 시작/라우터/일반 설정에 등록하지 않는다. 기본 실행은 DB 접속·환경 자격 조회·파일 쓰기가 없는 계획 출력이다.

```powershell
uv run --locked python -m app.db.migration_runner
```

버전은 `p0-initial-v1`, 정규화 LF 원본 SHA-256은 `157fae7e2d0798a39c2f048f29c605b1d5625b0cb1b8081985731285c0268a1b`다. Windows 체크아웃 CRLF의 raw 파일 해시와 구분한다. ORM 재생성 문자열과 원본·고정 체크섬 모두 같아야 한다. 원본을 임의로 변경하고 checksum만 갱신하는 우회는 제공하지 않는다.

### 자격과 사전 검사

승인된 운영자만 `DIT_MIGRATION_HOST`, `DIT_MIGRATION_DATABASE=ditnow`, `DIT_MIGRATION_USER=ditnow_migrator`, `DIT_MIGRATION_PASSWORD`, `DIT_MIGRATION_TLS_CA_FILE`을 비밀 저장소에서 별도 프로세스에 주입한다. 포트는3307이다. `DIT_API_*`나 runtime `Settings`를 migration 계정으로 바꾸지 않는다. 비밀번호/DSN을 CLI 인수·Git·로그·manifest에 넣지 않는다.

연결은 N의 `TLSRequiredConnection`, 검증 CA/hostname, 5초 TCP/TLS/auth와 쿼리 제한, LOCAL INFILE/SQL echo 금지를 사용한다. SQLAlchemy dialect가 없는 단독 aiomysql 세션에 정적 연결 collation을 적용하고 실제 값을 검사한다. `ditnow`·실제 `CURRENT_USER()` migrator·MariaDB11.4·연결 collation·FK/CHECK 활성·strict SQL mode를 확인한다. 이것은 GRANT 전체 검증·관리자 정책 승인을 대신하지 않는다.

### 장부 선택과 동시 실행

새 DB 원장을 추가하지 않고 **저장소 밖의 운영자 전용 manifest**를 선택했다. 16개 검토 DDL을 변경하지 않으며 실제 DB에 17번째 관리 테이블을 임의 생성하지 않기 위해서다. manifest에는 버전·체크섬·endpoint 결합 해시·기존9 정의 해시·각 statement/진행/생성 정의 해시만 저장하며 원문 SQL·비밀번호·호스트·개인 레코드는 저장하지 않는다.

운영자는 Git/worktree 밖의 사전 생성한 비공개 디렉터리를 지정하고 소유자 전용 ACL·백업·파일 보존을 책임진다. 이 도구는 ACL을 검증하지 않으며 Windows 파일 모드만으로 ACL 보장을 주장하지 않는다. 파일은 같은 디렉터리 임시 파일·fsync·replace로 갱신한다. 이는 DB와 파일의 분산 원자 트랜잭션이나 정전 내구성을 보장하지 않는다. 손실/불일치는 자동 복구 대신 차단한다.

하나의 전용 연결에서 이름 고정 `GET_LOCK`을 보유하고 각 CREATE 직전 소유권을 재검사한다. 별도 로컬 exclusive `.migration-lock`으로 다른 endpoint/process가 동일 manifest를 재사용하는 것도 차단한다. 프로세스 비정상 종료 후 남은 lock/`.pending-write`는 자동 삭제하지 않는다. 운영자가 원 프로세스 종료·DB 잠금 해제·기록과 실제 정의를 확인한 뒤 수동 조정해야 한다. 다른 모든 DDL 작업자도 같은 잠금 절차를 따라야 하며 비협조적 관리자 변경을 서버 권한으로 봉쇄한 것은 아니다.

### inspect / apply / resume

다음은 승인 후 운영자가 사용할 **명령 후보**이며 이번 코드 작성에서 원격 실행하지 않았다. 실제 경로는 사전 승인한 저장소 밖 디렉터리로 대체한다.

```powershell
# 메타데이터·장부 일치 검사만. 장부/DDL 쓰기 없음.
uv run --locked python -m app.db.migration_runner --inspect --confirm-database ditnow --expected-checksum 157fae7e2d0798a39c2f048f29c605b1d5625b0cb1b8081985731285c0268a1b --manifest C:\ditnow-operator-state\p0-initial-v1.json
# 별도 검토와 사람 승인 후에만 apply를 명시한다.
uv run --locked python -m app.db.migration_runner --apply --confirm-database ditnow --expected-checksum 157fae7e2d0798a39c2f048f29c605b1d5625b0cb1b8081985731285c0268a1b --manifest C:\ditnow-operator-state\p0-initial-v1.json
```

- 각 CREATE 전 PENDING을 장부에 fsync하고, 성공 후 실제 `SHOW CREATE TABLE` 정의 해시와 APPLIED를 기록한다. 기존9의 정확한 정의 해시를 전후 비교한다. 데이터 건수·개인 원문은 읽지 않는다. AUTO_INCREMENT 값 등 메타 정의가 달라도 자동 정규화하여 무시하지 않고 차단한다.
- 중간 실패 시 이미 성공한 CREATE가 커밋되어 있을 수 있다. DROP·자동 되돌리기·자동 skip은 없다. MariaDB DDL의 implicit commit 때문에 rollback 성공을 주장하지 않는다.
- 기존 장부를 사용하려면 위 명령에 `--resume`을 추가해야 한다. endpoint·원본 버전/체크섬·기존9·APPLIED 테이블의 정확한 서버 정의가 같을 때만 기록된 완료 이후부터 재개한다.
- PENDING인데 해당 테이블이 존재하면 DDL 성공 후 기록 전 실패일 수 있으므로 **차단**한다. 원문과 실제 정의의 독립 검토·장부 조정을 운영자가 수행하기 전 임의 채택하지 않는다. PENDING 대상이 없고 기록된 이전 정의가 일치하면 명시 resume으로 해당 CREATE를 다시 시도할 수 있다.
- 장부가 없는데 대상16 중 하나라도 존재하면 같은 모양이어도 자동 채택하지 않는다. 기존 객체·legacy9·데이터를 삭제하거나 이름을 바꿔 해결하지 않는다.
- 이 도구는 auth bridge·학생/비밀번호/세션 복제·학번→UUID cast·학년→역할 자동 발급·시드·일반 앱 DML 권한 부여를 하지 않는다.

동작 시험은 `tests/test_db_migration_runner.py`의 오프라인 메타/implicit commit simulator다. 실제 MariaDB 잠금·정전·DDL·파일시스템 장애·FK/CHECK 실행·배포를 검증하지 않는다. [태스크 기록](../../../../../docs/dev-prep/TASK_EXPLICIT_MARIADB_MIGRATION.md)을 함께 본다.

확인 근거(2026-10-30): [MariaDB GET_LOCK](https://mariadb.com/docs/server/reference/sql-functions/secondary-functions/miscellaneous-functions/get_lock)은 연결 종료 시 해제되고 transaction과 독립인 이름 잠금이다. [DDL implicit commit](https://mariadb.com/docs/server/reference/sql-statements/transactions/sql-statements-that-cause-an-implicit-commit)은 CREATE 실패를 포함한 commit 가능성과 rollback 한계를 설명한다.
