# MariaDB 운영 연결과 계정 검증

2026-10-30 KST · TASK-DB-NETWORK · 관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004, FR-AI-001; NFR-SEC-001/002/004/005, NFR-PRIV-003, NFR-OPS-001/002. 승인 근거: 사용자가 현재 작업 대화에서 제공한 운영 정보(DEC-019). 서버 설정을 직접 확인한 사실과 구분한다.

## 확정 운영 정보와 아직 확인하지 않은 사실

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

## 인프라 담당자에게 필요한 확인

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

## 후속 수용 기준

| 순서 | 검사 | 현재 |
|---|---|---|
| 1 | Tailscale online·대상 가시성·TCP 3307 | BLOCKED_NETWORK |
| 2 | TLS·해당 계정 인증·버전/문자셋·현재 DB 읽기 | NOT_RUN |
| 3 | 앱 계정 DML/DDL 분리·계정별 GRANT 검토 | NOT_RUN |
| 4 | 기존 스키마/데이터 조사·백업·비파괴 migration 리뷰 | NOT_RUN |
| 5 | migrator 적용·버전 확인·앱 계정 DML 검증 | NOT_RUN / 사람 승인 필요 |
| 6 | 공통 가상 계정·두 계정 CRUD·재로그인/영속성·RAG 허용 자료만 접근 | NOT_RUN |

DDL 거부 검사는 운영 DB에 임의 테스트 테이블을 만들거나 지워서 수행하지 않는다. 먼저 SHOW GRANTS/전용 검증 환경과 인프라 담당자 승인 방법을 사용한다. 네트워크가 막혀도 신규 앱·서비스·테스트·공개 RAG 및 92개 기능의 독립 구현은 계속한다.
