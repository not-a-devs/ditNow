# TASK-J — 입학 안내·가상 지원 미연결 모듈

확인일: 2026-10-30. 기반 main `8bb0e7f21940a1b69bae0e43397952dba7555c9c`. **TESTED(unit), 운영·공식 지원 서비스 미구현**. 실제 인증·MariaDB 연결·원격 데이터 변경·기관 심사·금융 거래를 수행하지 않았다. 기존 `mvp/` 소스를 읽거나 복사하지 않았다.

## 1. 범위와 요구사항

기존 [FRD](../v1-draft/02_FRD.md), [추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv), [RBAC-ADMIS](../v1-draft/04_RBAC.md), [DB/API 초안](../v1-draft/05_DB_API.md)을 따른다. 이 모듈은 지원자를 학생으로 전환하거나 현재 역할 enum을 변경하지 않는다.

| 요구사항·테스트 | 이번 구현·검증 | 남은 범위 |
| --- | --- | --- |
| FR-ADMIS-001 · TC-V1-ADMIS-001 | 공개 모집 안내·일정·FAQ DTO, 버전·출처 검증, 서버 페이지네이션·빈 결과 | 실제 공식 자료 적재·검수·게시 권한·전체 페이지 탐색 UI 미구현 |
| FR-ADMIS-002 · TC-V1-ADMIS-002 | 주입된 가상 전형의 초안 생성·본인 수정·제출, 정책 버전·기간·허용 전형·개수·CAS·멱등 처리 | 실명 지원·민감 서류·운영 DB·기관 접수 아님 |
| FR-ADMIS-003 · TC-V1-ADMIS-003 | 본인 DTO에 `received` 읽기 상태 허용, 서류 영역은 `BLOCKED` | 담당자 접수 전환 API·서류 도착 판정·면접 배정·파일 업로드 **BLOCKED** |
| FR-ADMIS-004 · TC-V1-ADMIS-004 | `admission_result=BLOCKED`, `payment_refund=BLOCKED` 표시 | 합격 판정·고지서·실제/가상 납부 처리 미구현. 기관 효력 주장 금지 |
| FR-ADMIS-005 · TC-V1-ADMIS-005 | submitted/received에서 가상 취소 **요청**으로 전환 | 실제 등록포기 심사·확정·환불·계좌 입력 **BLOCKED** |
| FR-ADMIS-006 · TC-V1-ADMIS-006 | 공개 FAQ 읽기 DTO·텍스트 출력 | 민감 상담 본문·비밀 상담·공식 내신 산출 **BLOCKED** |

관련 비기능: NFR-SEC-002/003/004/005/006, NFR-PRIV-002/003, NFR-REL-001, NFR-UX-001. 권한·DB 영속성·요청 제한의 운영 충족을 뜻하지 않는다. 공식 조사 근거는 위 추적표의 `https://www.dit.ac.kr/ipsi/`, `https://www.dit.ac.kr/ipsi/index.php?pCode=qna`와 2026-10-29 조사 기록이다. 이번 코드는 그 내용을 새로 검증·수집하지 않았고 공식 일정·정원·성적 규칙을 임의로 적재하지 않았다. 테스트의 example.test 인용은 DTO 검증용 가상 값이며 공식 자료가 아니다.

## 2. 실제 코드와 미연결 경계

- `services/api/app/features/admissions/models.py`: DTO·가상 정책·지원 상태·입력 제한.
- `ports.py`: actor 범위 단일 트랜잭션·최신 자격·정책·CAS·멱등 원장의 어댑터 계약.
- `service.py`: 실제 실행 가능한 도메인 동작. 테스트에서만 잠금·롤백 fake 주입.
- `router.py`: **기본 dependency 503, 공용 앱에 미장착**. 인증/DB/직원 권한을 흉내 내는 기본 구현 없음.
- `apps/web/src/features/admissions/`: 신규 페이지·검증된 응답 경계·공유 HTTP 전송·의도별 재시도. App/NAV/README/공통 설정/잠금 파일은 이 태스크에서 수정하지 않았다.

통합 담당자는 `get_applicant_actor`, `get_admissions_service`에 승인된 구현을 주입해야 한다. Actor는 검증된 공통 내부 사용자 UUID이며 클라이언트 user/role/cycle claim을 믿지 않는다. 인증 공급자 subject를 직접 쓰거나 별도 지원자 계정을 자동 생성하지 않는다. 인증 미설정은 503, 승인된 bridge에서 미인증은 401, 현재 자격 취소는 403, 다른 소유자/허용되지 않은 모집 회차는 404다. `ApplicantGrant`는 테스트 가능한 제안 인터페이스이며 운영 권한 부여가 아니다.

기존 DB 초안의 `admission_cycles`/`applications(applicant_id)`에 연결하는 **후보**다. 도메인 `owner_id`는 서버 내부 소유권 검사에만 사용하고 응답·OpenAPI 공개 모델에서 제거한다. 실제 테이블·DDL·마이그레이션·시드는 만들지 않았다. application_documents/admission_decisions/admission_payments/학생 원장을 새로 생성하지 않는다. 초안의 포괄 API-ADMIS `/applications`와 달리 제안 모듈은 본인 범위를 `/me/applications`로 명시한다. 기존 실서비스 계약을 변경하지 않았으며 장착·명세 경로 통합은 API 소유자의 별도 리뷰 대상이다.

## 3. 가상 정책과 상태

`DemoAdmissionPolicy`는 기본 운영값 없이 명시적으로 주입한다. 모집 회차 UUID, 정책 버전, 가상 전형 목록, 작성/제출 기간, 취소 요청 종료 시각, 지원 개수를 포함한다. 모델의 최대 목록 길이·문자 길이는 기술 입력 한도이며 학교 정원·규정이 아니다. 정책 부재는 503이다.

```text
draft --본인 수정/CAS--> draft
draft --가상 제출/CAS--> submitted
submitted 또는 received --가상 취소 요청/CAS--> withdrawal_requested
received: 읽기 전용 상태. 담당자 bridge/접수 판정 API 없음.
```

초안 작성·수정·제출은 주입한 기간 `[opens_at, closes_at)` 안에서만 가능하다. 정책 버전이 변경되면 본인이 초안을 최신 정책 버전으로 수정하기 전 제출할 수 없다. 허용 전형도 다시 검사한다. 취소 요청은 주입된 종료 시각이 없으면 거부한다. 이들은 안전한 **시연 설계 가정**이며 공식 학교 정책이 아니다. 실업무 상태·취소 승인·복구·삭제/보존기간은 별도 결정이 필요하다.

가상 별칭은 `가상 지원자 A/B/C`, 지원 동기는 정해진 가상 목적 코드 선택만 허용한다. 이름·주민번호·주소·전화·성적·민감 상담 자유 입력과 서류 업로드 폼이 없다. 추가 입력 필드도 서버에서 거부한다. 사용자가 직접 가상 접수·합격·납부 상태를 입력할 수 없다.

## 4. API·트랜잭션·재시도

모듈을 `/api/v1` 아래 장착할 때의 제안 경로다. 현재 공용 OpenAPI에는 추가하지 않았다.

| 메서드·경로 | 동작 |
| --- | --- |
| GET `/admissions/guides?offset=&limit=` | 최대 50개 공개 안내. 공식은 안전한 http(s) URL+aware 확인일 필수, DEMO/UNKNOWN은 공식 인용을 빌려 쓰지 않음 |
| GET `/admissions/me` | 본인 가상 지원서·허용 회차 정책. 소유자 UUID 응답 제외 |
| POST `/admissions/me/applications` | 가상 초안 생성, 201 |
| PATCH `/admissions/me/applications/{application_id}` | draft만 수정, expected_revision·expected_policy_revision 필수 |
| POST `…/{application_id}/submit` | draft의 가상 제출 요청 |
| POST `…/{application_id}/withdraw` | submitted/received의 가상 취소 요청 |

쓰기마다 `Idempotency-Key`가 필수다. 원장은 `(검증된 actor, 고정 동작+자원, key)`와 정규화 본문 해시를 연결한다. 같은 키/다른 본문은 409다. 동일 의도 재시도는 현재 권한·소유권을 다시 확인해 기존 레코드를 읽고, 삭제된 자원을 재생성하지 않는다. CAS는 멱등 처리와 별개다. 응답·검증/권한/내부 오류 모두 `Cache-Control: private, no-store`다. SQL·payload·비밀값을 오류 응답에 넣지 않는다.

실제 어댑터는 회차/사용자 범위 잠금·현재 자격·기간·개수·소유자/parent/CAS를 한 트랜잭션에서 검사하고 레코드+멱등 원장+최소 이벤트를 함께 커밋해야 한다. 감사 실패 때 전체 롤백하고 replay/감사 원장의 접근 권한을 공개 안내 읽기와 분리해야 한다. 테스트의 Python RLock은 MariaDB 동시성·격리·GRANT 검증이 아니다. 접근/남용 제한과 기록 보존기간은 실제 연결 전 게이트다.

프런트는 `/admissions/…`만 공통 `requestData`에 전달해 `/api/v1`을 한 번 붙인다. 같은 path+본문의 불명확 실패는 같은 키를 유지하며 입력 변경·성공은 새 의도다. 보호 요청의 401/403 때 본인 자료를 지운다. 성공 문구는 서버 응답을 받았을 때만 표시한다. 실제 E2E·DB 영속성·운영 세션 검증 전 기능 완료로 승격하지 않는다.

## 5. 실제 검증과 남은 승인

- `uv sync --locked`: 성공, 공통 의존성 변경 없음.
- 신규 백엔드 21개 포함 전체 `pytest`: **418 PASS**, 기존 Starlette/httpx 경고 1개.
- `ruff check .`, `ruff format --check .`: 성공(71개 파일).
- 신규 프런트 10개 포함 전체 Vitest: **150 PASS**. TypeScript 검사·Vite 빌드 성공.
- `npm ci`, `npm audit --omit=dev --audit-level=moderate`: 운영 취약점 0개.
- 공용 OpenAPI 스냅샷 일치. 에이전트 설정 54경로/8개 스킬, 92개 기능 추적 오류 없음.
- 최초 테스트 작성 중 optional mock 인자 TypeScript 오류를 수정한 뒤 위 검사를 재실행했다.
- 독립 리뷰·동일 HEAD GitHub CI: PR에서 실제 확인 후 기록. 로컬 자기 검토를 독립 리뷰로 표시하지 않는다.

**NOT_RUN/BLOCKED:** 실제 MariaDB·운영 권한·DB 영속성/경합·공통 로그인·지원자 bridge·담당자 권한·공식 자료 검수·기관 지원/합격·서류·금융·민감 상담·내신 산출·브라우저 390/1280 E2E. 사람 승인 없이 활성화하지 않는다. 현재는 미장착 코드·단위 검증만 검토할 수 있다. 다음 단계는 독립 코드 리뷰 → 승인된 공통 신원/가상 정책 책임자 확인 → 제한된 DB 어댑터·장착 PR → 2계정 E2E다.
