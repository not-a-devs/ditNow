# TASK-N P0 SQL 저장소 기반

상태: **IMPLEMENTED / TESTED(로컬 SQLite), 운영 미연결**. 실제 MariaDB 원격 연결·DDL·CRUD는 **BLOCKED_TLS / NOT_RUN**. 인증서 검증을 유지하며 실제 인증 공급자·관리자 발급·운영 데이터 처리 승인은 별도다.

## 실행 경계

- `p0_runtime.P0Executor`는 검증된 `VerifiedPrincipal`을 받아 한 번의 async session transaction 안에서 기존 sync 도메인 서비스와 실제 SQLAlchemy 저장소를 `AsyncSession.run_sync`로 실행한다. async aiomysql 드라이버의 IO를 사용하며 sync 네트워크 클라이언트를 운영 요청에서 호출하지 않는다.
- 호출 callback은 해당 실행 안에서 서비스 DTO를 반환해야 한다. 세션/ORM/서비스를 밖으로 반출하거나 예외를 삼켜 부분 변경을 commit하지 않는다. SQL 저장소는 독립 commit을 하지 않으며 임의의 별도 dependency로 직접 노출하지 않는다.
- `run`은 현재 active DEMO identity/profile 및 정확히 하나의 유효 소속과 학생 역할을 다시 조회한다. 토큰의 active·소속·역할을 그대로 믿지 않는다. `run_personal`은 자신의 기회 준비만 처리하며 active DEMO identity/profile을 요구한다. 직원의 개인 기회 관리에 학생 역할을 강제하지 않는다.
- `public_opportunities`는 승인된 공개 catalog 조회만 허용한다. published 및 OFFICIAL_PUBLIC/DEMO 출처 이외의 레코드는 응답하지 않는다.
- engine 생성·서버 router mount·로그인·계정/역할 생성·DDL·seed는 하지 않는다. 기존 보호 dependency와 feature router의 공급자 미설정 503은 유지한다. 익명 콘텐츠 API가 실제 연결된 것처럼 표시하지 않는다.

## 무결성 및 개인정보

익명 생성은 private/public/claim을 한 transaction에 저장한다. 학생 공개 조회는 작성자 없는 public 테이블을 읽고, 작성자 확인은 별도 owner ID집합에서 `is_owner` boolean으로만 환원한다. 타인 private 레코드는 owner 조건으로 404 처리한다. 모집의 공개 실명은 가상 프로필 표시명만 반환한다.

현재 권한을 확인한 뒤 멱등 replay를 조회한다. namespace는 actor·operation·resource 경계에 귀속되며 원문을 재비교한다. 본문이 다른 같은 key는 기존 서비스에서 409다. 삭제된 글이나 체크 항목의 claim을 남겨 재시도가 되살리지 않게 한다. 체크리스트 부모 소유권·정렬 위치 unique·최대 50개, 상태 CAS와 감사 원장의 동시 저장을 검증한다.

동일 actor identity와 업무 부모/대상 row를 `FOR UPDATE`로 잠그고 revision CAS를 적용한다. 모집 정원에는 작성자 1명과 accepted_count를 포함하며 현재 인원보다 줄이지 못한다. 모집 신청·승인/철회 endpoint와 accepted_count 갱신 트랜잭션은 **미구현**이다. 추가된 신청 원장은 이를 구현한 증거가 아니다.

가상 identity 및 역할의 관리자 변경 경로는 없다. 향후 발급·폐기 경로는 identity→membership/role 및 업무 row의 일관된 잠금 순서를 따르고 현재 권한의 재검증·deadlock 실패 처리를 별도 검토해야 한다. 실패 시 자동으로 write를 반복하지 않는다.

기존 `repositories/p0.py`는 PR #19의 호환 검토안으로 보존한다. 그 파일의 `AnonymousPostRepository.get_public`은 private 원장에서 projection하므로 학생 공개 조회 adapter로 사용하지 않는다. 신규 runtime은 별도 public 테이블을 읽는 `community_sql.SQLAnonymousPosts`만 사용한다. 모든 업무의 일반 감사 로그·운영 접근 감사는 아직 구현하지 않았으며 현재 상태 이벤트 원장의 테스트로 대신 완료 표시하지 않는다.

## 파일 및 테스트

| 경로 | 책임 |
| --- | --- |
| `models.py`, `schema.py`, `migrations/` | 논리 원장 및 미적용 초기 DDL |
| `p0_runtime.py` | async transaction과 sync 도메인의 단일 경계 |
| `../repositories/p0_access.py` | 현재 identity/profile·소속·학생 역할 검사 |
| `../repositories/community_sql.py` | 익명 projection, 모집 및 가상 실명 프로필 |
| `../repositories/opportunities_sql.py` | 공개 catalog, 개인 저장·상태 감사·체크 tombstone |
| `live_check.py` | 명시적 opt-in 읽기 진단, 기본 연결 금지 |

`tests/test_p0_sql_adapters.py`는 파일 SQLite+aiosqlite의 새 세션 지속성, owner/현재 권한, CAS, 멱등 replay, case별 key, projection 및 상태 감사 실패 rollback, 부모 삭제 tombstone, 모집 정원, 공개 catalog를 검증한다. fake 저장소 대신 실제 SQLAlchemy 저장소를 사용하고, 가상 fixture는 pytest 임시 DB에만 넣는다. SQLite의 명시적 BEGIN을 사용해 savepoint 이후 바깥 rollback도 검사한다.

```powershell
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m app.export_openapi --check
```

DB 서버 버전·실제 잠금 경쟁·GRANT·DDL 적용·운영 재시작·백업 복구·HTTP 보호 라우트 통합은 이 단위 테스트가 검증하지 않는다. 기존 92개 FR과 공개 OpenAPI endpoint 목록을 변경하지 않는다. 원격 초기 적용 전에 [마이그레이션 검토 게이트](migrations/README.md)를 충족해야 한다.
