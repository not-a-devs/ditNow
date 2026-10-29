# TASK-N2 — 명시적 MariaDB 초기 적용 기반

확인일2026-10-30. 기준 N PR37 HEAD27ff517. 사용자 safe migration 방향은 승인되었으나 실제 실행은 root의 별도 코드/인프라 검토와 적용 단계다. 작성자는 실제 DB·비밀값·원격 DDL·시드를 실행하지 않았다. 인증·관리자·보안 경계 변경을 자동 병합하지 않는다.

## 범위·파일

- `services/api/app/db/migration_runner.py`: 독립 CLI, 기본 무연결 dry run, 별도 migration 자격, 엄격 TLS, 고정 ditnow/버전/체크섬, 사전 metadata 검사, 동시 잠금, 외부 진행 manifest, 명시 apply/resume.
- `services/api/tests/test_db_migration_runner.py`: 오프라인 정상·충돌·진행·실패·비밀/기존 자료 보존 계약 시험.
- 기존 migration README 및 본 기록만 보강한다. 원본16 DDL·공통 인증·runtime Settings·공통 router·시드는 수정하지 않는다.

관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004; NFR-SEC-002/004/005, NFR-PRIV-001/003, NFR-DATA-003, NFR-REL-001/003, NFR-OPS-001/002. 실제 기능·인증·업무3CRUD 완료를 뜻하지 않는다.

## 독립 사전 검토와 증거 범위

B의 read-only 검토는 N16 CREATE-only와 기존 legacy9 모델의 테이블 교집합0, 외부 FK target0, compiler snapshot 일치 및 정규화 체크섬을 확인했다. 이는 실제 DB의 정의·자료 검증이나 raw SQL blind apply 허가가 아니다. root의 strict TLS·현재 collation/DB/버전 읽기 성공과 app 계정의 되돌린 가상 DML 시험은 별도 [운영 기록](07_DB_CONNECTIVITY_AND_ROLES.md)으로 관리한다. 그 결과가 N2 코드의 원격 적용·장부·재개 검증을 대신하지 않는다.

## 안전 경계와 차단 조건

원본은 `0001_initial.review.sql`, 버전 p0-initial-v1, LF 정규화 SHA256 `157fae7e2d0798a39c2f048f29c605b1d5625b0cb1b8081985731285c0268a1b`다. 원본·compiler·고정 체크섬 일치가 필요하다. CREATE만16개 실행하며 IF NOT EXISTS/자동 schema create/drop/ALTER/GRANT/계정·데이터 시드는 없다.

대상은 `ditnow`, 계정은 별도 `ditnow_migrator`, MariaDB11.4·utf8mb4_unicode_ci·검증 TLS·FK/CHECK 활성·strict mode다. 기존9 전부 존재하고 신규16 이름 충돌·예상 밖 객체가 없어야 한다. 운영자 전용 저장소 밖 manifest 및 별도 advisory/local 잠금을 사용한다. 전용 DB 관리 테이블을 추가하지 않는 이유와 ACL·정전·동시 관리자 변경의 한계는 [실행 안내](../../services/api/app/db/migrations/README.md)에 기록한다.

CREATE는 implicit commit이다. 각 statement 전 PENDING, 실제 생성 정의 확인 후 APPLIED를 기록하며 중간 실패 시 자동 DROP/skip/rollback을 하지 않는다. 완료 기록은 기존 정의가 정확히 같을 때 명시 resume으로만 재사용한다. 성공 여부가 불명확한 PENDING+테이블 존재, 장부 손상/손실, endpoint·기존9·완료 정의 변경은 사람의 별도 조정 전 차단한다. 실제 권한·참여자 정책·공통 UUID 매핑·학번 원장 복제는 범위 밖이다.

## 검증과 다음 작업

상태: IMPLEMENTED/TESTED(오프라인 simulator), 실제 운영 적용 NOT_RUN. 테스트는 기본CLI 무접속·자격 미조회, 잘못된 대상/계정·TLS 설정·잠금·충돌 차단, 기존9 보존,16 CREATE와 버전/체크섬, 정상 부분 재개, DDL 뒤 오류와 장부 쓰기 실패의 불확실성 차단, 공개 저장소 안의 장부 거부, 민감 오류 비출력을 검사한다. 실제 명령·테스트 수·CI HEAD는 PR 본문에 기록한다.

다음은 B/F 독립 검토, root의 approved endpoint metadata-only inspect, 기존 스키마/백업/작업 동시성 확인, 사람의 명시 적용 단계다. 앱에 migrator 자격을 넣거나 서버 시작에 runner를 연결하지 않는다. 적용 후 FK/CHECK/GRANT·실제 영속성·업무3CRUD·공통 auth bridge는 별도 검증이며 자동 완료로 바꾸지 않는다.
