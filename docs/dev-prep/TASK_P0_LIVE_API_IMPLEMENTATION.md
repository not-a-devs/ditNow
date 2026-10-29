# TASK-P0-LIVE-API — 공통 DB·세션과 핵심 업무 HTTP 연결

확인일 2026-10-30. **구현·오프라인 검증 / 보안·인증·DB 승인 대기**다. 기반은 main이 아닌 root 통합 준비 `7f7eabbb44f09caeaac79798baab8a69485ab453`이며 PR13/19/26/28/37/48/49/54/58의 승인과 본 작업의 승인은 별개다. 작성자는 원격 DB·자격·계정 생성·DDL·시드를 실행하지 않았다. 이전 root의 TLS/migration/rollback probe 증거는 이 HTTP 경로의 실제 검증이 아니다.

관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-001/003/004; TC-V1-AUTH-001/002, TC-V1-COM-001/004, TC-V1-OPP-004; NFR-SEC-001~007, PRIV-001/003, REL-001/003/004, DATA-003. 기존 92개 ID와 사용자 제품 결정을 보존한다.

## 변경·계약

- `services/api/app/integrations/platform_runtime/`: 읽기 전용 승인 binding, 최소 본인 DTO, 단일 엔진·기존 토큰 권위·현재 권한 검증. 자동 사용자/학과/역할/승인 레코드 생성은 없다.
- `services/api/app/api/v1/p0.py`: 기존 DTO·헤더 파서·도메인 서비스의 얇은 async HTTP 연결. AsyncSession을 sync HTTP threadpool에 전달하지 않는다. 자원 처리는 기존 `P0Executor`의 `AsyncSession.run_sync`와 transaction을 사용한다.
- `app/db/p0_runtime.py`: 선택적인 async `verify_principal`을 자원 UOW 내부에서 도메인 작업 직전에 실행한다. 기존 미지정 동작과 공개 catalog 경로는 보존한다.
- 공통 config/factory/auth/assistant/logging: 명시 gate, 같은 엄격 엔진 재사용, 현재 본인 `/auth/me`, 일관된 no-store/CORS, 생명주기 폐기. 기존 `chatbot/app/auth.py::issue_token`에는 선택적 현재 학번 한정 expired-session 정리만 추가하며 기본 호출의 기존 정리 동작은 유지한다.
- `app/repositories/community_sql.py`: 승인된 논리 모집 삭제 후 cancelled를 공개 get/list에서 제외한다. 폐기 행·멱등 claim은 삭제하지 않는다. 기존 closed 공개는 유지한다.

기존 `POST /api/v1/auth/login` 입력/`LoginData`, logout의 `{status:ok}`는 보존한다. `GET /api/v1/auth/me`는 `data{user_id,display_name,record_source:'DEMO',department_id,department_code,academic_year,community_access}`만 반환한다. UUID/학과가 필요한 본인 세션 projection을 익명 글 응답에 재사용하지 않는다.

기존 익명·모집·기회·개인 저장·체크 API 경로/DTO/Idempotency-Key/If-Match를 재사용한다. If-Match는 기존 파서대로 bare 정수 또는 strong quoted 숫자만 받으며 weak tag는 거부한다. 익명 create/recruit create는201과 `Idempotent-Replayed`를 유지하고 저장 PUT·체크 POST는 생성201/기존200이다.

사용자에게 승인된 모집 D는 **`DELETE /recruitments/{id}?revision=N` → `data{id,deleted:true}`**다. 기존 `cancel()`의 open→cancelled/CAS/소유 검사를 사용하며 공개 목록과 본인/타인 상세에서 숨긴다. 반복 삭제·이전 create키 재생은404로 부활하지 않는다. `POST /close`의 closed는 삭제가 아니며 기존 closed→cancelled409도 유지한다. 물리 삭제·지원 이력 삭제·새 상태 전이는 없다.

## 명시 활성화와 승인 권위

기본 `DIT_API_P0_RUNTIME_ENABLED=false`, `DIT_API_P0_SCHEMA_APPROVED=false`, `DIT_API_P0_IDENTITY_APPROVAL_IDS=[]`다. 세 설정과 완전한 기존 `DIT_API_DB_*`가 충족된 경우에만 공통 엄격 엔진 한 개를 구성한다. flag만 켜고 gate가 부족하면 protected API는503이며 DB 엔진을 만들지 않는다. flag가 꺼졌을 때 업무 경로는 전역 미등록이고 `/auth/me`는503이다. 서버 시작에 연결·DDL·seed를 하지 않는다.

`P0_SCHEMA_APPROVED`는 운영자 사전 검토 확인값이며 스스로 승인을 생성하지 않는다. 첫 사용에 실제 엔진의 MariaDB11.4/ditnow/연결 collation/필수 컬럼을 추가 검사한다. 이것만으로 GRANT/FK/CHECK/배포 준비가 검증된 것은 아니다. 실제 최소 권한·스키마 checksum·운영 승인은 root의 별도 기록을 따른다. 인증·인가·DB 보안 PR은 자동 병합하지 않는다.

mapping은 검증된 학번과 정확한 `issuer=urn:ditnow:student-login:demo:v1`, `subject=학번`의 canonical identity를 연결한다. digest 검색 후 원문을 대소문자까지 다시 비교한다. `AuditLogRow`의 pin된 UUID, 정확한 event `identity_binding_approved`, resource_kind `identity_binding`, entity_id=해당 identity, source_kind=DEMO를 모두 확인한다. 승인 행은 비어 있거나 복수로 모호하면 거부한다.

감사 actor는 별도 CLI가 준비할 로그인 불가 **disabled·역할0·DEMO operator identity**이며 반드시 존재해야 한다. actor가 학생 본인이거나 null이거나 역할 행을 가지면 거부한다. 이 operator는 실제 사람/관리자 계정이 아니며 행 존재 자체가 사람 승인을 의미하지 않는다. 권위는 별도 사람 승인과 운영자가 서버 설정에 pin한 승인 UUID에서 온다. 이 API는 operator·학생·감사·역할 행을 작성하지 않는다.

현재 canonical DEMO identity/profile, 유효한 단일 DEMO membership와 학과, 일치하는 현재 student 역할/범위를 매 요청 검사한다. legacy는 학번 PK·비밀번호·세션 권위만 사용한다. legacy dept/grade의 오래된 호환 복사본은 역할 부여나 현재 학적 차단 근거가 아니다. canonical 소속·학생 역할이 함께 승인 변경되면 다음 요청부터 이를 사용한다. 개인 원장/클라이언트가 전달한 UUID·role·학년으로 권한을 부여하지 않는다.

## 세션·트랜잭션·정보 경계

토큰은 기존 authenticate/issue_token/resolve_token/revoke_token을 재사용한다. 새 token store나 모의 인증을 만들지 않는다. live issue_token의 만료 정리는 현재 로그인 학생에만 한정해 다른 legacy 세션을 정리하지 않는다. 기존 토큰 TTL/폐기 권위는 바꾸지 않으며 비밀번호 변경 시 토큰 폐기 정책·다중 worker 제한은 별도 운영 게이트다.

토큰의 subject를 일단 조회한 뒤 legacy Student→AuthSession→canonical identity→승인 감사/operator→profile/membership/role 순서로 현재 행을 잠그고 토큰을 다시 판정한다. 공개 catalog 외 업무 UOW 안에서도 이 과정을 재실행해 dependency 이후 폐기된 token/binding/role로 쓰지 못한다. 기존 CurrentP0Access와 SQL의 자원/부모 소유권·CAS 검사를 계속 적용한다. SQLite 테스트는 이 경계에서 재검증을 증명할 뿐 MariaDB 다중 연결 잠금·deadlock 성능의 증거가 아니다.

P0 개인/익명/모집·기회 응답은 root_path·오류·validation·404·redirect를 포함해 private,no-store다. URL·토큰·본문·학번을 요청 로그에 남기지 않는다. CORS는 명시 origin만 사용하며 GET/POST/PUT/PATCH/DELETE 및 Content-Type/Authorization/If-Match/Idempotency-Key만 허용한다. 응답에는 X-Request-ID/Idempotent-Replayed만 추가 노출한다. origin wildcard와 클라이언트 신원 override는 없다.

공통 런타임이 활성화되면 assistant도 같은 엄격 엔진과 검증된 토큰/binding을 재사용한다. 공개 시설 질문은 기존 RAG 경로다. **개인 학사 RAG reader는 canonical 이름·소속·학년 및 승인된 동일 subject의 수강/성적을 안전하게 조합하는 후속 작업 전503**이다. 오래된 legacy 학적을 현재 canonical 원장인 것처럼 반환하지 않으며 이 차단이 핵심 로그인/CRUD를 막지 않는다. 외부 LLM·유료 서비스 호출은 이 작업에서 실행하지 않았다.

## 검증·잔여

전용 HTTP/SQLAlchemy/SQLite 테스트는 엄격 factory만 로컬 SQLite 엔진으로 주입하고 MariaDB readiness 보고를 명시적으로 stub한다. 실제 토큰 helpers·canonical 매핑·도메인·SQL adapters·fresh session·rollback은 실행한다. 테스트 DB의 두 학생·disabled operator·학과·감사·공고는 임시 fixture이며 실제 운영 provisioning이 아니다.

정상 로그인→me→익명 CRUD·모집 C/R/U/논리 D·개인 기회/체크 CRUD, 타 계정404, CAS409, 생성 재생·삭제 tombstone, 출처/issuer/pin/감사 actor·현재 소속/역할 폐기, dependency→UOW 사이 token/binding/role 폐기, locked token 재확인, canonical 변경과 오래된 legacy 복사본 분리, 업무 실패 시 private/public/claim 원자 rollback, root_path no-store/CORS/기본 미구성503을 검사한다. 명령·수·HEAD CI는 PR 본문에 기록한다.

실제 MariaDB HTTP CRUD·지속 저장·동시 잠금·두 시연 계정 생성·공통 UUID 운영 활성화·개인 학사 RAG·FE/브라우저·배포·사람 승인·최종 보안 리뷰는 NOT_RUN/대기다. 원본16DDL·운영 schema·migration·seed를 이 태스크에서 수정하지 않았다. NAV/OpenAPI snapshot·프런트 생성 타입 최종 통합은 root가 소유한다.
