# P0 MariaDB 초기 스키마 검토안

TASK-N · FR-AUTH-001/002, FR-COM-001/004, FR-OPP-001/003/004 · NFR-SEC-002/004/005, NFR-PRIV-001/003, NFR-REL-001/003.

`0001_initial.review.sql`은 **16개 논리 원장의 미적용 DDL**이다. 적용 명령·DROP·GRANT·계정·시드는 제공하지 않는다. 애플리케이션 import와 시작 시 자동 DDL은 없다. 최초 빈 스키마용 검토안이며 기존 테이블을 변경하는 업그레이드 마이그레이션이 아니다.

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

- MariaDB는 DEC-016의 확정 제품이다. 이 작업의 실제 원격 접속·DDL·CRUD는 **NOT_RUN / BLOCKED_TLS**다. 담당자가 수행한 별도 읽기 진단 결과와 이 코드의 SQLite 테스트를 혼동하지 않는다.
- 사용자 요청에 따라 인프라 담당자에게 CA PEM 및 접속 주소와 일치하는 SAN 인증서를 요청한 상태다. `~/.ditnow-secrets/mariadb-ca.pem` 준비 후 담당자가 엄격한 CA·hostname 검증을 재검사한다. 인증서 검증 해제나 평문 fallback은 허용하지 않는다.
- 적용 담당자는 기존 스키마의 빈 상태를 다시 확인하고, 백업·소유자·16개 원장 및 제약 리뷰·사용자 승인 범위를 확인한다. 기존 테이블이 있으면 이 초기 DDL을 그대로 실행하지 않는다.
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
