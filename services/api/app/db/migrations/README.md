# P0 MariaDB 초기 스키마 제안

TASK-A-DB · FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004 · NFR-SEC-002/PRIV-001/REL-001/003. `0001_initial.review.sql`은 11개 논리 P0 원장의 **검토용 초기 DDL**이다. 적용 명령·DROP·권한 부여·계정/시드는 제공하지 않는다. 앱 import나 시작 시 스키마를 생성하지 않는다.

MariaDB는 확정이나 클라우드 접속정보·버전·계정 권한·인증·비용은 미확정이다. Docker CLI는 있으나 daemon에 연결할 수 없어 실제 MariaDB 실행은 **NOT_RUN**이다. 테스트의 SQLite FK/제약·소유권 검증 및 MariaDB 방언 DDL 컴파일을 실제 MariaDB 통합 검증으로 표시하지 않는다.

UUID는 이 제안에서 CHAR(32), 시각은 UTC DATETIME(6), 엔진은 InnoDB/utf8mb4다. 클라우드 버전·문자셋·CHECK/FK·트랜잭션·최소 GRANT 적용을 확인한 뒤 별도 승인한다. PostgreSQL RLS를 전제하지 않는다. subject의 원문 길이 때문에 큰 복합 인덱스 대신 길이 프레임 SHA-256 인덱스를 사용하고 조회 시 원문 두 값을 정확히 재비교한다. 해시 일치는 인증이 아니며 충돌 시 다른 사용자로 매핑하지 않는다.

`IdentityRepository`는 이미 검증된 주체를 활성 내부 ID에만 조회하며 사용자/역할을 자동 생성하지 않는다. 소속 겹침은 조회에서 거부하지만 관리자 변경 트랜잭션의 기간 중복 방지 정책은 아직 미구현이다. `SavedOpportunityRepository`는 서버가 정한 actor 소유/부모 범위와 revision을 확인하며 트랜잭션 commit은 호출자가 소유한다. 모든 보호 API의 현재 권한 검증과 인증 공급자는 별도다. 익명 읽기는 Pydantic 공개 projection만 반환하고 익명 신원 열람/쓰기·public 읽기 테이블 선택은 승인 대기다.

재생성 함수는 `app.db.schema.initial_schema_sql()`이며 네트워크·DB 연결을 사용하지 않는다. 실제 연결은 `DatabaseSettings`를 명시적으로 전달한 engine에서만 가능하다. TLS는 기본 인증서 검증과 서버 이름 검증을 요구하고 SQL 바인딩 값은 로그에서 숨긴다. 이 연결 도우미는 현재 앱에 연결하지 않았다.

공식 참고(2026-10-30 확인): [SQLAlchemy MariaDB 방언](https://docs.sqlalchemy.org/en/20/dialects/mysql.html), [세션/트랜잭션](https://docs.sqlalchemy.org/en/20/orm/session_basics.html), [MariaDB GRANT](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant). 시연용 가상 데이터만 테스트하며 mvp 소스를 사용하지 않는다.
