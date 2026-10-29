# TASK-PROFILE — 본인 활동 프로필 1차 구현

상태: **IMPLEMENTED / TESTED(독립 FE·도메인 단위), 전체 FR-AUTH-003은 PARTIAL**. 기본 provider503·API/App 미마운트, 실제 인증·MariaDB 어댑터·공개 협업 연결은 BLOCKED/NOT_RUN이다. DEC-017/018/020, RBAC-AUTH, NFR-SEC-002/003/004/007, NFR-PRIV-003, NFR-DATA-003, NFR-REL-001, NFR-UX-001/003, TC-V1-AUTH-003에 연결한다.

## 명세와 범위

[기존 데이터 모델](../05_DATA_MODEL.md)은 `profiles.interest_tags` 및 `realname_activity_profiles`의 skills/interests/bio를 정의하며 [RBAC](../v1-draft/04_RBAC.md)는 본인 프로필 편집만 허용한다. 이번 범위는 이 활동 필드만 사용한다. 새 닉네임 필드·별도 학생/실명 원장·회원가입·프로필 생성·역할 승인·공식 실명 인증 정책을 추가하지 않는다.

- `skills`, `interests`, `bio`만 서버 주입 `ProfileEditPolicy`의 현재 허용목록과 개정 아래 편집한다. 미주입 정책은503, 빈 목록은 조회만 가능하다.
- `display_name`, 학과명, 학년은 기존 원장의 본인 읽기 전용 projection이다. 학번·실명·학과·학년·역할·계정상태·레코드 출처·새 nickname 입력은 요청 DTO가 거부한다.
- 표시 이름은 DEMO 원장의 값이며 학교 실명 인증을 보장하지 않는다. 이 본인 API의 `SELF_ONLY`는 프로필 공개 정책이 아니다. 모집의 기존 실명 프로필이나 익명 게시글에 자동 연결·배포하지 않는다.
- 관심사는 단일 port의 `interests`로 표현한다. 공통 DB 소유자가 기존 `profiles.interest_tags`와 `realname_activity_profiles.interests` 중 승인된 원본·매핑을 확정해야 한다. 두 필드/두 원장에 임의 중복 저장하거나 변경을 동기화하지 않는다. 물리 매핑 미확정은 실제 DB 통합 차단이며 테스트 fake가 이를 해결하지 않는다.

## 소유 파일과 API

- `services/api/app/features/profiles/{models,ports,service,router}.py`
- `services/api/tests/test_profiles_firstpass.py`
- `apps/web/src/features/profiles/{api.ts,index.tsx,index.test.tsx}`
- 이 문서만 수정한다. App/router/NAV/공통 인증/공통 types/DB 모델/migration/lockfile은 변경하지 않는다.

| 제안 API | 입력 | 결과 |
| --- | --- | --- |
| GET `/api/v1/profiles/me` | 공통 인증의 내부 UUID actor | 현재 본인 표시/활동 필드·개정·시각·DEMO·현재 편집 정책 |
| PUT `/api/v1/profiles/me` | skills/interests/bio, expected_revision, expected_policy_revision, Idempotency-Key | 저장한/동일 요청 재확인한 현재 본인 projection |

타인 UUID를 입력·경로로 받지 않는다. 응답에 user_id·issuer/subject·역할·토큰·학번을 넣지 않는다. API는 읽기/수정만 제공하고 missing profile404를 자동 생성으로 바꾸지 않는다. 기술/관심사는 각각20개·항목당30문자·중복 거부, 소개500문자 제한은 자원/시연 계약 기본값이며 학교 규정이 아니다. 빈 활동 필드는 가능하다. 실제 연락처/민감정보를 입력하지 않도록 안내하며 임의 정규식으로 모든 개인정보를 차단했다고 주장하지 않는다.

## 현재 권한·트랜잭션 계약

`ProfileStore.transaction(actor_id)`는 현재 계정/학생 자격·편집 정책·기존 활동 프로필을 순서대로 잠그고, 대기 후 현재 커밋된 값을 재조회해야 한다. 현재 actor 불일치/계정 비활성401, 학생 자격 없음403, 본인 행 없음/잘못된 소유자404, 정책 미주입503이다. UI의 비활성화는 권한 근거가 아니다.

허용되지 않은 필드를 실제 변경하면403, 낡은 정책/프로필 개정409다. 동일 key/body는 현재 권한·정책·소유자를 재확인하고 현재 본인 projection을 `replayed=true`로 반환한다. 같은 key/다른 body409, 타인과 key를 공유해도 원장은 actor로 분리한다. 행 삭제 후 replay로 재생성하지 않는다. 저장소는 actor+CAS 조건으로 활동 필드만 갱신하며 원본 실명·학적·계정 상태는 보존해야 한다. 변경 행·멱등 장부·최소 개정 이벤트는 동일 트랜잭션에서 커밋/롤백한다. 이벤트/오류 로그에 과거/현재 소개나 관심사 본문을 기록하지 않는다.

물리 FK/UNIQUE·CAS SQL·MariaDB 현재 읽기/행 잠금·권한 회수 직렬화·교착·세션 원장·영속성·분산 인증은 공통 소유자의 후속 구현·승인 대상이다. 테스트 RLock은 이 계약의 예시일 뿐 실제 MariaDB 동시성 증거가 아니다.

## 새 프런트와 통합 조건

본인 프로필 조회·로딩·없음·503·401/403·허용 필드 없음·편집·저장·충돌·재조회 안내를 제공한다. 저장 실패는 입력과 같은 요청 키를 유지하고 입력 변경은 새 키를 발급한다. 401/403은 개인 값·초안·의도를 지운다. Abort/요청 세대 검증으로 unmount·StrictMode의 오래된 읽기/저장 결과를 폐기한다.

독립 검토에서 쉼표 포함 단일 태그가 UI의 쉼표 분리로 둘로 바뀌는 P2를 발견했다. 기술/관심사를 서버가 항목 안에서 금지하는 개행으로 구분하는 '한 줄에 한 항목' 편집으로 바꾸고, 읽기 전용 필드는 원본 배열/값을 전송한다. 소개만 허용/모든 활동 필드 허용의 두 정책에서 단일 `C,C++`·쉼표 포함 관심사 원형 보존 회귀를 추가했다. 서버에 새 쉼표 금지 정책을 만들지 않았다.

공통 인증 소유자가 계정/세션 변경 시 `<ProfilePage sessionGeneration={generation} />`의 generation을 증가시키거나 컴포넌트를 remount해야 한다. 현재 이 연결은 없다. 세션·토큰을 별도 발급/저장하거나 로그인 UI를 중복 구현하지 않는다. 현재 shared transport를 사용하며 운영 Bearer 주입도 공통 소유자의 후속이다. 사전 `mvp/`는 읽거나 복사하지 않았다.

## 검증 기록과 남은 게이트

API 응답의 identity 필드·정책 extra 거부, Unicode 경계, 자기 범위·권한 회수/replay·CAS·롤백·동시 가상 UOW·private no-store·안전 오류를 검사한다.

| 실제 검사(2026-10-30, base main `2dc8187`) | 결과 |
| --- | --- |
| 전용 BE·최종 FE | BE27개 PASS, 태그 보완 후 FE12개 PASS |
| Python 전체/Ruff/포맷/OpenAPI | 전체863개 PASS, 관련6파일 Ruff·포맷 PASS, 기존 런타임 OpenAPI 동일 |
| 태그 보완 전 웹 전체 `vitest run --maxWorkers=2` | 28파일370개 PASS. 보완 후 전체 수라고 재표시하지 않음 |
| 태그 보완 후 `npm run build` | 타입 검사 포함 PASS |
| OpenAPI 타입 비교·npm ci | PASS, 취약점0 |
| 독립 Codex 검토 | 읽기 전용 BE27/초기FE10 직접PASS, 태그 P2 발견·보완 후 FE12 직접PASS/현재 미활성 범위 잔여 차단 finding 없음 |

새 PR HEAD의 실제 GitHub CI·탐색/92개 추적 검사는 PR 본문에 별도 기록한다. 로컬 전체 검사를 반복해 같은 결과를 부풀리지 않는다. AI 검토와 위 테스트가 운영 승인이나 실제 DB 증거는 아니다.

실제 DB 접속·비밀정보 조회·DDL/migration·시드·계정 생성·보호 API 운영 활성화·브라우저 E2E·배포는 실행하지 않는다. 실제 과업 검증 전 전체 FR을 VERIFIED로 표시하지 않는다. 프로필·신원 보안 PR이므로 사람 승인 전 OPEN 유지·자동 병합 금지다. 탐색 경로/전체92개 상태 등록은 공유 소유자가 별도 처리한다.
