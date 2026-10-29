# TASK-O — 생활·학생지원 1차 미연결 모듈

확인일 2026-10-30. 기준 main `e2764f7a35f999fb89f1e20d151a2abc7721ccd4`. **PARTIAL / TESTED(unit)**. 이번 태스크에서는 실제 DB 접속·권한 변경·DDL·마이그레이션·운영 계정·기관 판단을 실행하지 않았다. `mvp/` 소스를 읽거나 복사하지 않았다. 실제 DB 운영 검사는 별도 공통 소유자의 업무다.

## 1. 요구사항과 구현 경계

근거: [통합 FRD](../v1-draft/02_FRD.md), [92개 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv), [권한 정책](../v1-draft/04_RBAC.md), [DB/API 초안](../v1-draft/05_DB_API.md). 기존 FR·TC·역할 enum을 변경하지 않는다.

| FR·TC | 이번 구현 | 미구현·차단 |
| --- | --- | --- |
| FR-DORM-001 · TC-V1-DORM-001 | 출처·확인일·버전이 있는 공개 생활관 안내 DTO와 빈 목록 | 공식 요금·입사 규정·정원·방 정보 적재/최신성 검증 없음 |
| FR-DORM-002 · TC-V1-DORM-002 | 주입된 가상 프로그램의 본인 신청·선택 변경·취소·상태 조회 | 실제 입사 자격 판정·심사·방 배정·반려·납부 없음. 학생 자기 배정 불가 |
| FR-HELP-001 · TC-V1-HELP-001 | 정해진 일반 안내 제목/사유 코드만 선택해 가상 문의 요청·수정·취소. 처리/답변 상태는 읽기 전용 | 담당 배정·직원 답변 작성·기관 민원 접수·민감 본문 없음 |
| FR-HELP-003 · TC-V1-HELP-003 | 공개 장애지원 안내 DTO | 장애 정보·진단서·지원 자격 신청·개인 상담 수집 없음 |
| FR-HELP-004 · TC-V1-HELP-004 | 가상 봉사 프로그램 참여 요청·취소·본인 상태 조회 | 봉사 시간 인증·공식 이수·실적 등록·직원 완료 판정 없음 |
| FR-CRED-001 · TC-V1-CRED-001 | 본인 가상 배지 조회, 가상 표시/철회 상태·공식 검증 불가 표시 | 발급·서명·공유 검증·관리자 부여·실제 철회 처리 **BLOCKED** |
| FR-HELP-002 · TC-V1-HELP-002 | 공개 안내 DTO의 `protected_help` 분류만 정의, 실제 자료 미적재 | 고충·인권·성희롱 상담 접수/본문/검색/AI/알림/일반 관리자 접근 **BLOCKED** 유지 |

관련 RBAC-DORM/HELP/CRED, NFR-SEC-002/003/004/005/006/009, NFR-PRIV-002/003/004/005, NFR-REL-001/007, NFR-UX-001/006의 부분 계약이다. 서비스에 문서가 있다는 이유로 운영 권한·보안·영속성 충족을 주장하지 않는다.

조사 출처는 추적표의 2026-10-29 기록을 유지한다: 생활관 `https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities`, 일반 민원 `https://www.dit.ac.kr/kr/index.php?pCode=cybersvccenter`, 장애지원 `https://www.dit.ac.kr/kr/index.php?pCode=stdsupportcenter`, 고충 안내 `https://www.dit.ac.kr/kr/index.php?pCode=gendercounsel`, 디지털 배지 공지 `https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice`. 이번 작업은 원문을 새로 조사하거나 자료·규정을 임의로 적재하지 않았다. 봉사 정책·운영 규정은 미확인이다. 실제 출처 데이터가 준비되지 않아 런타임 안내 레코드/가상 프로그램/사용자 시드는 제공하지 않는다.

## 2. 파일·API·데이터 후보

- `services/api/app/features/student_life/models.py`: 공개 DTO, 가상 정책·요청·읽기 전용 배지, 선택 입력과 상태 제약.
- `ports.py`: 현재 자격·정책·잠금·CAS·원자 멱등 처리의 어댑터 계약. 운영 구현 아님.
- `service.py`: 실제 실행 가능한 도메인 서비스. `router.py`: 기본 actor/store dependency 503, **공용 factory·router에 미장착**.
- `apps/web/src/features/student-life/`: 신규 화면·응답 검증·공통 HTTP 전송·재시도. 실제 App/메뉴·OpenAPI 등록은 통합 소유자의 별도 작업이다.

제안 API:

| 경로 | 동작 |
| --- | --- |
| GET `/api/v1/student-life/guides?offset=&limit=` | 최대 50개 공개 안내. 공식 자료는 www.dit.ac.kr의 안전한 HTTPS 원문+aware 확인일 필수. UNKNOWN/DEMO는 공식 인용을 빌리지 않음 |
| GET `/api/v1/student-life/me` | 본인 가상 요청·배지·허용된 가상 정책. `sensitive_support=BLOCKED` |
| POST `/api/v1/student-life/me/requests` | 선택 코드로 가상 신청/문의/참여 요청 생성 |
| PATCH `/api/v1/student-life/me/requests/{request_id}` | requested 상태에서 선택 변경. expected_revision/expected_policy_revision 필수 |
| POST `…/{request_id}/cancel` | 현재 자격·기간·상태를 다시 검증해 가상 취소 |

개별 초안 API-DORM/HELP/CRED 경로를 실제로 대체한 것이 아니라 본인 생활 영역의 미장착 제안 경로다. 장착 전 API 소유자 리뷰가 필요하다. 기존 DB 초안의 `dorm_applications`, 일반 `service_requests`, 봉사 참여 후보 원장, `demo_badges`에 연결할 수 있으나 물리 테이블을 확정하거나 생성하지 않았다. `support_cases`/`case_access_logs`의 민감 고충 자료를 일반 요청 레코드에 합치지 않는다. `dorm_rooms` 배정·`dorm_assignments`·공식 배지 원장 쓰기는 구현하지 않았다.

`LifeActor`/`LifeGrant`는 향후 승인된 공통 서버 bridge의 제안 인터페이스이며 별도 계정·역할·자격 증명을 만들지 않는다. 내부 사용자 UUID와 현재 프로그램 접근 범위를 서버가 재검증해야 한다. 미설정은 503, 미인증은 승인된 bridge에서 401, 비활성 자격은 403, 타인/허용 범위 밖 자원은 404다. 학생·담당자·민감 상담자·발급담당 권한을 자동 부여하지 않는다.

## 3. 가상 정책·상태·개인정보

`DemoLifePolicy`는 프로그램 UUID/유형/가상 이름/버전/허용 선택/신청 기간/취소 종료 시각/본인 개수/프로그램 요청 한도를 **기본 운영값 없이** 주입한다. 정책 registry 미설정은 503이다. 모델의 문자·목록·숫자 상한은 기술 검증 한도이며 학교 규칙이나 실제 생활관 정원이 아니다. capacity는 이 시연의 요청 수 한도이며 방 배정·행사 정원 판단이 아니다.

- 생활관: requested → (외부 가상 fixture의 processing 읽기) → cancelled. 배정·반려 판정 없음.
- 일반 안내 문의: requested/processing/answered 읽기, 요청 수정·취소만 구현. answered의 답변은 두 가지 가상 안내 코드로 한정하며 직원 답변 입력 API는 없다.
- 봉사: requested/participating/completed 읽기, 참여 요청·취소만 구현. 시간·학점·실적 인정 없음.
- 배지: DEMO_ISSUED/DEMO_REVOKED **조회만**. `official_effect=false`, `verification=NOT_OFFICIALLY_VERIFIABLE` 고정. 서명/이메일/공유 URL 없음.

생성·수정은 주입 기간 `[opens_at, closes_at)` 안에서만 가능하다. 취소는 요청/처리/가상 참여 상태와 주입된 종료 시각을 검사한다. 취소 시에도 현재 계정과 프로그램 권한을 재확인한다. 자격 회수 후 취소권을 별도 허용할지는 미확정이므로 권한을 임의로 확대하지 않는다. 완료/답변 기록의 변경·삭제/보존기간·취소 후 재신청 규정은 운영 승인 대상이다. 시연에서는 cancelled만 요청 수 집계에서 제외하며 기존 키로 재시도하면 기존 취소 상태를 반환한다. 새 의도의 재요청은 최신 정책·정원을 다시 검사한다.

자유 텍스트·실명·학번·전화·주소·장애/건강 정보·고충·성희롱 사연·파일 업로드 필드가 없다. 가상 생활관 A/B, 일반 절차/시설 안내, 가상 봉사 A/B 선택 코드만 허용한다. 클라이언트 owner_id/role/state/답변/배지 효력 입력도 거부한다. 일반 민원을 민감 고충 접수 우회 경로로 사용하지 않는다. 공개 고충 안내의 실제 출처가 없으면 데이터 목록을 비워 두며 연락처·절차를 만들어 넣지 않는다.

## 4. 원자성·오류·클라이언트 계약

모든 쓰기는 필수 `Idempotency-Key`, `(검증 actor, 고정 동작/자원, key)`와 정규화 본문 해시를 연결한다. 같은 키·다른 본문은 409다. 같은 키 재생도 현재 자격·소유권·parent를 확인하고 삭제 기록을 재생성하지 않는다. expected_revision과 정책 버전은 별도 검사하며 키가 CAS를 우회하지 않는다.

실제 어댑터는 사용자·프로그램·자원을 잠그고 현재 자격/정책/기간/요청 수/소유자/parent/CAS를 한 트랜잭션에서 검사한다. 레코드·최소 이벤트·멱등 원장을 함께 커밋하고 일부 실패 시 전부 롤백해야 한다. replay와 감사 열람은 공개 안내 읽기 권한에서 분리한다. 테스트 fake의 RLock·롤백은 MariaDB 격리·권한·영속성 증거가 아니다. 운영 요청 제한·감사 접근·보존 기간은 아직 미구현이다.

공개/본인 응답과 400/403/500/503 오류에 `private, no-store`를 적용한다. 공개 모델은 내부 owner_id를 제거하고 예외 원문을 응답/로그에 넣지 않는다. 프런트는 런타임 타입·출처·DEMO·공식 효력 없음·민감 영역 BLOCKED를 검사한다. 경로는 `/student-life/…`만 전달해 공통 `/api/v1` prefix를 한 번 사용한다. 불명확 실패의 동일 의도는 같은 키를 유지하고 선택값 변경·성공은 새 키로 분리한다. 401/403 때 본인 요청·배지를 지운다. 서버 성공 응답 전 저장 성공을 표시하지 않는다.

## 5. 실제 검증·후속 게이트

- `uv sync --locked`: 성공, 공통 의존성/lock 변경 없음.
- 신규 백엔드 **27개** 포함 전체 pytest **460 PASS**. 기존 Starlette/httpx 경고 1개.
- Ruff check·84개 파일 format check 성공, 공용 OpenAPI 스냅샷 일치(미장착 경로 추가 없음).
- 신규 프런트 **12개** 포함 전체 Vitest **172 PASS**, TypeScript·Vite 빌드 성공.
- npm ci·운영 의존성 audit 취약점 0개. agent 54경로/8개 스킬 및 기존92개 추적 오류 없음.
- 초기 추가 테스트의 누락 import를 수정한 뒤 전체 Python 검사를 재실행했다.
- 같은 HEAD GitHub CI·독립 리뷰는 실제 PR 결과를 기록한다. 자기 검토를 독립 리뷰로 표시하지 않는다.

**NOT_RUN/BLOCKED:** 이번 태스크의 실제 DB/스키마/GRANT/네트워크, 공통 로그인 bridge, 가상 정책 책임자·운영 자격 승인, 직원 답변/생활관 배정/봉사 완료 판정, 공식 배지 발급·서명·관리자 부여, 민감 고충 접수·처리, 2계정 E2E·DB 경합·390/1280 실브라우저. 공유 auth/DB/migration/config/lock/App/NAV/README는 소유 범위 밖으로 변경하지 않았다. 독립 코드 리뷰 후에도 실제 활성화는 별도 승인과 어댑터 검증이 필요하다.
