# MariaDB 운영 연결과 계정 검증

2026-10-30 KST · TASK-DB-NETWORK · 관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004, FR-AI-001; NFR-SEC-001/002/004/005, NFR-PRIV-003, NFR-OPS-001/002. 승인 근거: 사용자가 현재 작업 대화에서 제공한 운영 정보(DEC-019). 서버 설정을 직접 확인한 사실과 구분한다.

## 최신 상태 — 2026-10-30 갱신

**엄격 TLS·앱 계정 읽기 PASS, 실행 호환·스키마 통합 진행 중**. 사용자가 CA 배치를 알린 뒤 계정 정보를 보내지 않는 TLS 진단에서 CA·접속 주소 검증과 TLS1.3 연결이 성공했다. 동일한 엄격 FastAPI 엔진도 Windows `SelectorEventLoop`에서 `ditnow_app` 인증·SELECT1이 성공했다. 인증서 검증을 해제하지 않았다. 아래 초기 네트워크/인증서 차단 기록은 이력이며 운영 준비 완료를 뜻하지 않는다.

최신 사용자 제공 서버 TLS 설정과 PR #44 병합을 확인한 뒤 다시 검사했다. CA의 **인증서 DER SHA-256**은 `0E9727B1E83140A2E6D7F219117A95279F77A391FE9D97FF136D8377B5216184`로 예상값과 일치한다(PEM 파일 바이트 해시와 구분). `ssl.create_default_context(cafile=...)`, `CERT_REQUIRED`, `check_hostname=True`를 유지하고 SQLAlchemy + aiomysql에 `connect_args={"ssl": tls_context}`를 전달했다. 앱 인증 계정 일치·`SELECT 1`·현재 DB ditnow·MariaDB 11.4.13·세션 `TLSv1.3`/`TLS_AES_256_GCM_SHA384` **PASS**. 따라서 **TLS 차단 해제**이며 비밀번호·전체 계정 host·DSN은 기록하지 않았다.

최신 메타데이터는 **기존 9개 InnoDB 테이블**(students/auth_sessions/courses/course_sessions/enrollments/exams/graduation_rules/graduation_rule_categories/question_logs)과 관계를 확인했다. 모든 테이블 정렬은 utf8mb4_unicode_ci다. 과거 빈 스키마 결과로 초기화하면 안 된다. 개인 행 값은 읽지 않고 테이블·열·외래키·집계 행 수만 확인했으며, 기존 사용자·세션·학적 데이터를 변경하지 않았다. 앱의 직접 GRANT는 ditnow DML 4종과 ditnow_chatbot SELECT이며 DDL은 없다. 현재 비파괴 추가 migration과 공통 신원 매핑을 검토 중이다. 사용자가 migration·CRUD 진행을 승인했지만 보안 PR 병합·파괴적 변경 승인을 뜻하지 않는다.

### 실제 트랜잭션 DML 검사

Codex B가 임시 진단 코드를 읽기 전용 검토했고 트리거 확인을 권고했다. root가 **별도 migrator 엄격 TLS 세션**에서 검사 대상 graduation_rules의 트리거0과 InnoDB를 확인한 뒤, **앱 계정**으로 기존 키와 겹치지 않는 UUID 접두사의 가상 행1개만 INSERT→SELECT→UPDATE→SELECT→DELETE했다. `finally`에서 전체 트랜잭션을 ROLLBACK하고 다음 트랜잭션에서 해당 행 부재를 확인해 **PASS**했다. 앱의 DML 실행·롤백 증거이며 기존 행 변경0·영구 쓰기0·DDL0이다. 개인/학생 행은 읽거나 수정하지 않았다. 이는 핵심 업무3 CRUD의 API/권한·재시작 영속성 완료 증거가 아니다. 실제 DDL 거부 시험도 아직 하지 않았다.

### CA 배치 후 오류 분리와 실제 읽기 결과

| 구분 | 결과 |
|---|---|
| CA 로드·서버 인증서/주소 검증 | PASS, CERT_REQUIRED·check_hostname 유지, TLS1.3 |
| 계정 없는 TLS-only 진단 | 인증 패킷0·쿼리0·쓰기0, MariaDB 공식 SSLRequest 절차 사용 |
| 기본 Windows Proactor async | FAIL: OperationalError 2003 → OSError 22 → SSLWantReadError. SSLCertVerificationError는 관찰되지 않음 |
| Windows Selector async | PASS: 기존 엄격 SQLAlchemy/aiomysql factory·앱 계정 인증·SELECT1 |
| 실제 읽기 전용 schema 검사 | VERIFIED_TLS, MariaDB11.4·ditnow 일치, 기존 legacy 9개 테이블 존재·제안16개 테이블 없음, 개인 행 값 읽기0·쓰기0 |
| 연결 collation | 보완 뒤 실서버 PASS: N27ff factory의 dialect 초기화 후 listener가 utf8mb4_unicode_ci 유지. 기존 불일치 원인은 SQLAlchemy dialect의 후속 SET NAMES |
| 운영 상태 | Windows helper·접속 listener 코드 및 오프라인 독립36개·실서버 읽기 재검증 PASS, 승인된 migration·CRUD 통합 검증 전 |

앞선 진단은 체인의 모든 SSLError를 인증서 실패로 분류해 SSLWantReadError까지 포함한 **오분류**였다. 원문 예외·DSN·비밀값을 출력하지 않는 진단으로 위 유형을 분리했다. 현재 CA/SAN 불일치가 확인됐다고 주장하지 않는다. 담당자에게 요청한 서버 인증서 설정 확인과 별개로, 현재 신뢰 검증 성공 사실을 사용자에게 갱신했다.

근거(확인2026-10-30): [MariaDB SSLRequest](https://mariadb.com/docs/server/reference/clientserver-protocol/1-connecting/connection), [Python 이벤트 루프](https://docs.python.org/3.13/library/asyncio-eventloop.html). Windows 루프 차이는 실제 비교 검사 결과이며 특정 라이브러리의 보편적 결함으로 일반화하지 않는다. 글로벌 이벤트 루프 정책·TLS 보안 설정을 변경하지 않았다.

DPAPI CLIXML을 저장소 밖에서 읽어 자식 진단 프로세스에만 비밀값을 주입했다. 아래 표는 **초기 검사 이력**이며 최신 schema/TLS 성공 결과를 대신하지 않는다. 비밀번호·해시·원문 GRANT·개인 레코드는 출력하지 않았다.

| Codex 실제 읽기 검사 (2026-10-29 16:19 UTC) | 결과 |
|---|---|
| 엔진/DB | 11.4.13-MariaDB-ubu2404 / ditnow |
| ditnow_app 직접 GRANT | USAGE; ditnow.* SELECT·INSERT·UPDATE·DELETE; ditnow_chatbot.* SELECT. 직접 DDL 없음 |
| ditnow_migrator 직접 GRANT | ditnow.*와 ditnow_chatbot.* ALL PRIVILEGES. 런타임 주입 금지 |
| 현재 schema | ditnow 테이블 0개, 양 계정 메타데이터 결과 일치 |
| DB 문자/정렬 | utf8mb4 / utf8mb4_unicode_ci |
| 진단 클라이언트 연결 정렬 | utf8mb4_uca1400_ai_ci; 실제 어댑터에서 운영 정렬과 일치 여부 검토 |
| PyMySQL 진단 TLS | 암호화 활성. 인증서 신뢰/호스트 검증을 입증한 결과는 아님 |
| FastAPI용 async SQLAlchemy/aiomysql 엄격 TLS | FAIL, 인증서 검증 실패를 안전한 오류로 반환 |
| DDL·migration·seed·실제 CRUD 쓰기 | NOT_RUN, 변경 0 |

사용자가 저장소 밖 `.ditnow-secrets/mariadb-ca.pem` 배치를 알린 뒤 기본 async 검사 두 번이 실패해 반복을 중단했다. 이후 사용자가 정확한 오류 유형 진단을 요청해 무인증 TLS-only 검사와 로컬 단계별 오류 분리·다른 루프 비교를 수행했고 위 성공/호환성 결과를 확인했다. 비밀값·개인키 원문을 출력하지 않았다.

**검증 해제 금지**를 유지한다. 엄격 TLS·기존 schema·가상 행 트랜잭션 DML/롤백을 확인했고, 리뷰된 비파괴 추가 migration→업무 CRUD/영속성 검사 순서로 진행한다. 기존 자료·관리자·운영 권한 변경은 별도 게이트다. 직접 GRANT 확인은 계정별 최소 권한 설계의 최종 적합성 승인과 구분한다. 원격 DDL·seed·업무 CRUD 영구 쓰기는 아직 없다.

## 초기 확정 정보와 최초 검사 이력

| 항목 | 사용자 제공 기준 | 실제 검증 |
|---|---|---|
| 운영 위치 | 팀원 개인 서버 Proxmox VM, Tailscale 사설망 전용 | VM/서비스 설정 NOT_RUN |
| 엔진·문자 | MariaDB 11.4, utf8mb4 / utf8mb4_unicode_ci | 서버 handshake/변수 조회 NOT_RUN |
| 포트 | 3307 | 이 개발 환경에서 TCP 5초 시간 초과 |
| 플랫폼 원장 | ditnow | schema/버전/기존 데이터 NOT_RUN |
| 챗봇 전용 자료 | ditnow_chatbot | schema/기존 개인 원장 이관 범위 NOT_RUN |
| 앱 계정 | ditnow_app, DML만 허용·DDL 금지 | 인증·SHOW GRANTS NOT_RUN |
| migration 계정 | ditnow_migrator, 승인된 스키마 변경에 사용 | 인증·GRANT·migration NOT_RUN |
| 챗봇 계정 | ditnow_chatbot | 실제 권한/대상 DB NOT_RUN; 런타임 DDL 사용 금지 |

사용자가 제공한 Tailscale 대상 주소는 로컬 진단에만 사용했다. 비밀번호·실서버 DSN을 코드/PR/로그에 기록하지 않는다. 프로젝트 내부에 MariaDB 컨테이너나 별도 서버를 만들지 않는다.

## 실제 네트워크 검사

- Python `socket.create_connection((사용자 제공 대상, 3307), timeout=5)` 실행: **FAIL / TimeoutError / 약 5.02초**. 포트 연결이 완료되지 않아 서버 handshake를 받지 못했다.
- 로컬 `tailscale status --json`에서 필요한 상태만 선별: **BackendState=NoState, SelfOnline=false, TargetVisible=false**. 전체 peer/사용자 정보는 기록하지 않는다.
- `DIT_API_DB_*`·`DIT_API_DATABASE*` 환경 변수 이름 검사에서 해당 키 없음. 비밀번호 조회나 추측 로그인을 하지 않았다.
- 이 결과는 DB 비밀번호 오류 또는 MariaDB 서비스 장애의 증거가 아니다. 먼저 로컬 Tailscale 연결을 확보해야 한다.

## 초기 네트워크 차단 당시 요청 이력

1. 이 개발 PC의 Tailscale 로그인/연결 및 서버와 동일 tailnet 접근 허용. 인증은 사람이 수행한다.
2. 대상 VM이 Tailscale online인지, 해당 노드 간 ACL/grant가 TCP 3307을 허용하는지 확인.
3. VM의 MariaDB 실제 수신 포트·bind-address·호스트 방화벽을 확인. 공용 인터넷에 3307을 열지 않는다.
4. 통신 복구 후 계정별 허용 host·DB 범위·GRANT와 TLS 인증서/검증 방법을 전달. TLS 실패를 이유로 자동 검증 해제하지 않는다.
5. 비밀번호는 승인된 로컬 환경/비밀 저장소로 전달한다. PR·이슈·채팅·검사 로그에 보내지 않는다.

외부 인프라 담당자에게 메시지를 전송하지 않았다. 이 문서는 전달 가능한 필요한 설정 목록이다. 자동 Tailscale 로그인·ACL/방화벽 변경도 수행하지 않았다.

## 개발·실행 책임 경계

- services/api가 공통 로그인·내부 사용자 UUID·학적·역할의 권위다. chatbot 전용 DB는 별도 최종 사용자/학적 원장이 아니다. 기존 standalone 학생/세션 자료는 현황·이관·삭제 정책 검토 전 자동 복제하거나 삭제하지 않는다.
- FastAPI가 현재 역할·소속·소유권을 매 요청 검증한다. MariaDB 계정 권한·FK·UNIQUE·트랜잭션은 추가 방어선이다. PostgreSQL RLS를 전제하지 않는다.
- 통합 services/api 런타임은 ditnow_app을 사용한다. 챗봇 전용 자료 접근은 승인된 챗봇 계정 범위에 한정하고 migrator는 어떤 런타임에도 주입하지 않는다. migrate 계정/비밀은 앱 설정·브라우저·OpenAPI에 포함하지 않는다. migration은 승인된 별도 명령/환경이며 startup create_all·자동 seed를 하지 않는다.
- 초기 DDL 제안이 존재해도 기존 DB 조회·백업·스키마 비교·리뷰 전 적용하지 않는다. DROP/RESET/기존 데이터 재시드는 승인 없이 금지한다.
- DIT_API_ 설정 정책을 유지하고 DB 필드는 명시 입력으로 확장한다. 기존 공개 health·시설 조회는 DB 없이 계속 동작하며 DB 준비 성공으로 표시하지 않는다.
- 기존 챗봇의 async SQLAlchemy/aiomysql과 통합 API의 드라이버·pool·트랜잭션·문자셋/UTC 처리 호환을 단위/계약으로 먼저 확인한다. SQLite/DDL 컴파일은 MariaDB 11.4 통합 시험을 대신하지 않는다.

## 현재 후속 수용 기준

| 순서 | 검사 | 현재 |
|---|---|---|
| 1 | Tailscale online·대상 가시성·TCP 3307 | PASS, Codex 환경 재확인 |
| 2 | 해당 계정 인증·버전/문자셋·현재 DB 읽기 | 엄격 TLS·Selector async 앱/migrator 인증 PASS, N27ff 연결 collation 보완 실검증 PASS |
| 3 | 앱 계정 DML/DDL 분리·계정별 GRANT 검토 | 직접 GRANT·가상 행 DML/롤백 PASS; 실제 DDL 거부 시험 NOT_RUN |
| 4 | 기존 스키마/데이터 조사·백업·비파괴 migration 리뷰 | 기존 9개 테이블/관계·집계 확인 PASS; 백업·적용 NOT_RUN, PR #37 제안 검토 |
| 5 | migrator 적용·버전 확인·앱 계정 DML 검증 | 사용자 실행 승인 있음; 스키마 비교·보존 확인 후 수행, 현재 NOT_RUN |
| 6 | 공통 가상 계정·두 계정 CRUD·재로그인/영속성·RAG 허용 자료만 접근 | NOT_RUN |

DDL 거부 검사는 운영 DB에 임의 테스트 테이블을 만들거나 지워서 수행하지 않는다. 먼저 SHOW GRANTS/전용 검증 환경과 인프라 담당자 승인 방법을 사용한다. DB 실행 호환·스키마/인증 통합의 남은 게이트만 보류하고 신규 앱·서비스·테스트·공개 RAG 및 92개 기능의 독립 구현은 계속한다. 인증서 검증을 완화하거나 같은 원격 검사를 맹목적으로 반복하지 않는다.
