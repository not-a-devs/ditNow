# TASK-IDENTITY-BRIDGE — 기존 세션과 공통 UUID의 명시적 연결

## 상태와 범위

- 2026-10-30, `IMPLEMENTED` / 전용 단위 테스트 `TESTED`. **비활성 보안 계약이며 운영 인증 완료가 아니다.** 사람 승인 전 PR을 병합하거나 활성화하지 않는다.
- 관련: FR-AUTH-001~003, RBAC-AUTH, NFR-SEC-001~005, NFR-ID-001~002, NFR-PRIV-002~003, NFR-OPS-004. 기존 92개 기능 ID를 변경하지 않는다.
- 기준: [DEC-017·020](../11_DECISION_LOG.md), [공통 권한](../v1-draft/04_RBAC.md), [P0 계약](../v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md). 기존 NFR의 JWT 표현은 새 JWT를 도입할 근거가 아니며 최신 DEC-020의 기존 학번 로그인·불투명 세션 토큰 권위가 우선한다.
- 변경: `services/api/app/integrations/identity_bridge/`, `services/api/tests/test_identity_bridge.py`, 본 문서만. 로그인·로그아웃 DTO/라우트, 공통 Settings/App/auth, DB 모델·migration·비밀번호·세션 발급 코드를 변경하지 않는다.

## 동작 및 완료 조건

1. `IdentityBridge`의 issuer·token verifier·common ledger가 하나라도 미설정이면 `503 UNAVAILABLE`. 기본 dependency도 항상 503이다. 앱/라우터 등록은 하지 않는다.
2. 서버가 주입한 `ExistingLegacyTokenVerifier`는 **새 AsyncSession**에서 기존 `chatbot.app.auth.resolve_token`을 그대로 호출한다. 이어 존재하는 `students.student_id`만 선택한다. 이름·비밀번호 해시·학년을 조회하거나 새 로그인/토큰/비밀번호 저장소를 만들지 않는다.
3. 토큰이 없거나 부정·만료·폐기되면 401. 학번/역할/UUID를 요청 body, 헤더의 자체 선언, 오래된 token claim에서 받지 않는다. token은 `SecretStr`로 전달하고 로그를 남기지 않는다.
4. 검증된 기존 학생 PK를 **정확한 문자열 그대로**, 서버에 승인된 issuer와 함께 조회한다. 대소문자 정규화·학번 UUID cast·이름/학년/비밀번호 해시 유사성 매칭·자동 계정 생성은 없다.
5. 승인 매핑은 순방향과 역방향 각각 정확히 한 건이어야 한다. issuer/subject 원문까지 비교하여 해시 충돌·DB collation 별칭·다른 학생이 같은 UUID를 쓰는 연결을 거부한다. 승인 상태·승인 시각·미폐기·기존 레코드의 명시적 DEMO 확인이 모두 필요하다. 승인자/대상 UUID는 실제 UUID 자료형의 non-nil 값이어야 하며, 승인 증빙이 빠진 손상 스냅샷을 승인으로 간주하지 않는다.
6. 같은 common-ledger UOW에서 현재 identity가 active·DEMO인지, profile도 해당 UUID·DEMO인지 확인한다. 현재 유효기간의 active 학적이 정확히 하나이고 현재 student 역할이 platform 전체 또는 해당 학과 범위에 있어야 한다. 클라이언트 역할이나 기존 `students.grade/dept_id`로 권한을 발급하지 않는다. 교수/관리자 권한을 부여하는 기능은 없다.
7. 매핑 누락/중복/비승인/신원·profile·소속·역할 부적격은 동일한 403이다. 내부 오류는 원문 없이 503으로 변환한다. 응답은 서버 내부 dependency용 `{user_id: UUID, active: true}`만이며 학번·이름·역할·승인자·issuer/subject를 포함하지 않는다. **이 DTO를 익명 글 공개 응답으로 재사용하면 안 된다.**

## 공통 원장 연결 의무 및 승인 게이트

- `IdentityLedger`는 provider-neutral **읽기 전용 Protocol**만 있다. 현재 N 미병합 ORM을 직접 import하지 않고, 구현체·runtime fake·실DB 접근·migration은 제공하지 않는다.
- `ApprovedMapping`은 새 identity 테이블이 아니다. 기존 `identities(issuer, subject, UUID)`에 대한 **검토·승인 증빙을 포함한 서버 내부 projection**이다. 향후 adapter는 승인된 manifest/감사 기록과 공통 원장을 결합해야 한다. 현재 N의 `identities`만으로는 `approved_by/approved_at/legacy_source_kind`를 입증할 수 없다. 승인 증빙이 없으면 매핑을 반환하면 안 된다. 이 메타데이터의 저장·승인·폐기 방식과 실제 issuer 값은 별도 사람 검토 대상이다.
- 기존 legacy 9개 테이블의 모든 행이 DEMO라는 가정은 금지한다. 이 모듈의 테스트 데이터만 명시적으로 가상이다. `students`에 없는 provenance를 이름/학번 형식으로 추측하면 안 된다.
- adapter는 current locking read, 일관된 잠금 순서, forward/reverse uniqueness, 승인 폐기/subject 재지정과의 직렬화, 소속·role 재조회 의무를 지켜야 한다. 제한된 목록이나 캐시를 전체 후보처럼 반환하면 안 된다. 실제 격리수준/잠금·동시성 증거는 아직 없다.
- 토큰 확인용 새 세션과 공통 원장 UOW는 현재 요청에서 순서대로 실행된다. **분산 원자적 인증/진행 중 요청의 즉시 폐기를 보장하지 않는다.** 실제 자원 조회/변경은 자신의 operation UOW에서 현재 principal·소속·scope·소유권·상태를 다시 검사해야 한다. 인증/권한 캐시나 세션 발급 역할을 이 bridge에 추가하면 안 된다.
- 세션 factory는 승인된 동일 시스템의 엄격 TLS 엔진을 주입해야 한다. 모듈은 engine/환경 파일을 만들거나 읽지 않는다. DB 제품·GRANT·TLS/Windows loop·migration은 해당 단일 소유자의 작업이다.
- 기존 auth/login·logout 계약, frontend auth callback, 보호 API dependency 등록은 다른 소유자 범위다. **본 PR만으로 어느 보호 API도 활성화되지 않는다.**

## 검증

전용 `uv run --locked pytest tests/test_identity_bridge.py -q`: **61 PASS**.

- 기본/부분 미설정, 부정 token, 없는/만료/폐기 세션, 매핑 누락/중복/원문 불일치/역방향 충돌.
- inactive identity, 비DEMO·타계정·없는 profile, 학적 중복/만료/미래/naive 시각, 다른 학과·타인·폐기/만료/미래 역할, 관리자 역할만 존재하는 경우 거부.
- 동일 토큰 재호출 중 subject·소속·역할 변경을 즉시 재조회. 최소 DTO/frozen/추가 PII 필드 거부. 비밀/원문 오류 로그 없음.
- 실제 기존 `issue_token/resolve_token/revoke_token`을 **임시 SQLite의 가상 students/auth_sessions 두 테이블**에서 사용하여 유효·폐기·만료·없는 토큰 재확인. 서버 시작이나 운영 DB에서 테이블을 생성한 증거가 아니다.
- F 독립 읽기 전용 리뷰에서 `approved_by=None`인 손상 dataclass가 통과하는 P2를 재현했다. 실제 UUID/non-nil·strict active/학적 자료형 검증과 10개 회귀를 추가했다. 운영 공격이나 실제 DB 행 발견 증거는 아니다. 변경 후 독립 재검증은 PR에 기록한다.

로컬 추가 검증: 전체 API **740 PASS**(기존 Starlette/httpx deprecation 경고 1건), `uv sync --locked`, 전체 Ruff check/format 133개 파일, OpenAPI snapshot 일치, `node scripts/check-agent-config.mjs`, 92개 진행표 검사, 사전 MVP `npm ci/typecheck/build` 모두 PASS. MVP npm 설치 audit은 0건이며 새 앱이나 MVP 소스는 변경하지 않았다. 본 문서의 상대 링크 3건 존재 확인 PASS.

전체 회귀·정적 검사·동일 HEAD GitHub CI 및 독립 리뷰 결과는 최종 PR에 기록한다.

`NOT_RUN`: 실제 MariaDB bridge adapter, 승인 manifest 적용, cross-process 토큰 폐기 경합/DB 잠금, 실제 사용자·운영 권한, 보호 API 연결, 브라우저 통합. `OPEN-002/003`의 남은 보안/권한 승인 조건을 해결했다고 표시하지 않는다.

NAV 및 공통 보드 수정은 root 단일 소유자에게 요청한다. 본 작업의 새 탐색 경로는 이 문서와 PR에서 제공하며 공유 파일을 동시에 수정하지 않는다.
