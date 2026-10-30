# TASK-DEMO-STUDENT-SERVICES-API — 가상 학생서비스 시연 API(미장착)

확인일 2026-10-30. 브랜치 `feat/demo-student-services-api-20261030`.

| 항목 | 상태 |
| --- | --- |
| 계약·문서 | **DOCUMENTED** |
| 백엔드 구현 | **IMPLEMENTED** (공용 app factory·router 집계에 **미장착**) |
| 단위·HTTP 테스트 | **TESTED: 36 PASS**, Codex가 실제 실행(합성 UUID·메모리·격리 TestClient) |
| CI·실 DB·라이브 배포·브라우저 E2E | **NOT_RUN** — 주장하지 않음 |
| 영속성(NFR-REL-001) | **NOT_PERSISTENT** — 프로세스 메모리 전용 |

## 작성자·인계

- **Codex**: 최초 범위 제한 초안(`models.py`, `service.py`, `router.py`, `__init__.py`) 작성. 커밋 전 상태로 인계.
- **Claude Code**: 초안 정확성 검토 후 설계 유지 결정(코드 변경 없음, 아래 검토 결과 참고), 테스트 [`test_demo_services.py`](../../services/api/tests/test_demo_services.py)와 본 문서 최종 작성. 명령·테스트를 실행하지 않았다.
- **Codex**: Claude 작성 테스트와 최종 모듈의 별도 검토, 실제 pytest·Ruff 검사. 긴 문자열 줄바꿈과 Ruff 자동 포맷만 보정했으며 업무 동작은 바꾸지 않았다.
- Claude Code CLI 2.1.314, 기존 `claude.ai` 인증의 단일 세션을 사용했다. `--restricted`, Read/Grep/Glob/Edit/Write만 허용, 빈 MCP·세션 비저장·명령/네트워크/DB/Git 도구 없음. 최초 inline MCP 인자 형식 오류는 모델 시작 전 파일 경로로 보정했다. `ask.py`는 사용하지 않았다.
- 루트 소유자: 공통 인증/현재 권한 연결(`get_demo_actor` override)과 API 장착(`app.state.demo_services`, `include_router`)을 별도로 수행한다. 본 태스크는 app factory·router 집계·공통 인증·DB·config·NAV·README를 변경하지 않았다.

## 범위와 요구사항 대응

사용자는 아래 원 요구사항의 **가상 시연**만 승인했다. 실제 금융·기관·개인정보 처리는 계속 **BLOCKED**이다. 92개 기능 ID와 기존 FR·TC 체계는 변경하지 않는다.

| FR · TC | 이번 구현(가상) | 차단 유지 |
| --- | --- | --- |
| FR-ADMIS-004 · TC-V1-ADMIS-004 | `ADMISSION_RESULT`: 가상 결과 화면 문구 | 실제 합격·입학 자격 판정/조회 |
| FR-ADMIS-005 · TC-V1-ADMIS-005 | `ADMISSION_WITHDRAWAL`: 가상 포기·환불 상태 | 실제 등록 취소·환불·금융 거래 |
| FR-ACA-010 · TC-V1-ACA-010 | `CERTIFICATE`: 완료 시 고정 시연 문서(가상 학생, 직인·서명·공식 효력 없음) | 공식 증명서 발급·진본 검증 |
| FR-ACA-011 · TC-V1-ACA-011 | `TUITION`: 가상 납부 확인 | 금액·계좌 입력, 실제 결제/고지 |
| FR-HELP-002 · TC-V1-HELP-002 | `PROTECTED_COUNSEL`: 고정 선택형 가상 절차 | 실제 고충 접수·상담 본문 수집 |
| TC-V1-X09 | 가상 표기·공식 효력 없음·민감정보 미수집 플래그 | — |

관련 NFR: NFR-SEC-001(서버 확인 actor만, 본문 소유자 주장 거부), NFR-SEC-002(타인 자원 404, 응답에 소유자 UUID 없음), NFR-SEC-004(엄격 입력·extra 금지·입력값 미반향·`private, no-store`), NFR-REL-001 **NOT_PERSISTENT**, NFR-UX-001(상태 라벨·가상 문구 고정).

이 API를 실제 입학 결과, 결제/환불, 공식 증명서, 비공개 상담 접수라고 부르지 않는다.

## 파일

- [`models.py`](../../services/api/app/features/demo_services/models.py): enum, 엄격 입력(`extra=forbid`, `consent` StrictBool true, `revision` strict int 1..2^31-1), 불변 `DemoItem`.
- [`service.py`](../../services/api/app/features/demo_services/service.py): `DemoServices` — 단일 `RLock` 아래 소유 확인·CAS·멱등 claim·쓰기. 네트워크·로깅·영속 저장 없음.
- [`router.py`](../../services/api/app/features/demo_services/router.py): 휴면 `APIRouter(prefix="/me/demo-services")`, 모든 성공/오류 응답 `Cache-Control: private, no-store`.
- [`test_demo_services.py`](../../services/api/tests/test_demo_services.py): 직접 서비스 + 격리 TestClient.

## API 계약(장착 시 `/api/v1/me/demo-services`)

| 메서드·경로 | 입력 | 결과 |
| --- | --- | --- |
| GET `''` | — | `data={source_kind:"DEMO", persistence:"PROCESS_MEMORY", official_effect:false, items:DemoItem[]}` 최신순, 삭제 제외 |
| POST `''` | `Idempotency-Key`, `{kind, scenario, consent:true}` | 201 `DemoItem`, `resource_version=revision` |
| POST `/{UUID}/advance` | `Idempotency-Key`, `{revision}` | 200 `REQUESTED→IN_PROGRESS→COMPLETED` |
| DELETE `/{UUID}?revision=N` | — | 200 `{id, deleted:true}` |

- `Idempotency-Key`: 16..100자 `[A-Za-z0-9_-]`, (소유자, 작업, 키) 범위.
- `DemoItem` 필드: `id, kind, scenario, status, status_label, title, revision, created_at, updated_at, outcome_text, document_text, source_kind, persistence, official_effect:false, sensitive_content_collected:false`. 소유자 UUID·실명 등 개인정보 필드 없음.
- `outcome_text`는 COMPLETED에서만 종류별 고정 가상 문구, `document_text`는 완료된 CERTIFICATE에서만.
- 의존성: `get_demo_actor` 기본 503, 루트가 검증된 정규 UUID의 `DemoActor`로 override. `get_demo_service`는 `request.app.state.demo_services`가 `DemoServices`일 때만, 아니면 503.

## 오류·동시성 규칙

| 상황 | 결과 |
| --- | --- |
| 형식 오류·extra 필드·consent false/1·키 형식 | 400, 입력값 미반향 |
| 타 소유자·없는 ID·삭제 후 advance | 404 |
| 오래된 revision·완료 후 advance·삭제 revision 불일치 | 409 |
| 같은 키 다른 payload / 삭제된 생성 결과 재요청 | 409(부활 없음) |
| 같은 키 같은 payload | 최초 응답 재생 |
| 같은 revision DELETE 재요청 | 200 |
| 기술 메모리 한도(소유자 20 / 전체 200, 삭제 tombstone 포함 / claim 1000, 축출 없음) | 429 |
| actor·service 미설정 | 503 |

한도는 대학 정책이 아닌 메모리 보호용 기술 한도다. 재시작 시 전체 초기화, 다중 워커는 각자 별도 원장을 가진다.

## 테스트 범위와 실제 실행

5종×2시나리오 생애주기, 동일 소유자 목록·순서, B 소유자 advance/delete 404와 본문 owner/user_id 거부, 엄격 입력·PII 추가 필드 미반향, consent false/1, 멱등 생성·advance 재생과 충돌, tombstone 비부활, stale/terminal 409, 소유자·전체·claim 한도(모듈 상수 monkeypatch), 동일 키 동시 생성 1건, 동시 CAS 정확히 1건 성공, 재시작 초기화, actor/service 미설정 503, 성공·오류·malformed·미지정 경로 `private, no-store`, 공용 app factory에 경로 미노출. `DIT_API_*` 환경변수는 값 조회 없이 삭제하고 고정 합성 UUID·키만 사용한다. 실 DB·브라우저·네트워크 없음.

2026-10-30 Codex 실제 실행:

- `uv sync --frozen --group dev`: 고정 의존성 설치 성공, 기존 lockfile 변경 없음.
- `uv run --frozen pytest tests/test_demo_services.py -q`: **36 PASS**. 기존 Starlette TestClient 사용 중단 예정 경고 1개.
- `uv run --frozen ruff check app/features/demo_services tests/test_demo_services.py`: 성공.
- `uv run --frozen ruff format --check app/features/demo_services tests/test_demo_services.py`: 5개 파일 성공.
- `uv run --frozen pytest -q`: 전체 API **1,551 PASS**, 기존 Starlette 경고 1개(52.19초).
- 에이전트 설정 105개 경로·미러 8쌍, 92개 기능 ID, 본 문서 상대 링크 5개, Git staged diff 검사 성공.
- 원 기능 추적표의 위 5개 TC ID를 실제 CSV 행과 대조했다. 92개 ID와 기존 문서는 수정하지 않았다.
- CI·실제 공유 인증 활성화·프런트 연결·외부 서버·DB·실제 학생 정보·금융·LLM·브라우저는 이 태스크에서 **NOT_RUN**이다.

## 검토 결과·남은 우려

- Claude의 초안 검토와 Codex의 후속 검토에서 이 가상 범위의 새 차단 문제는 발견하지 못했다. Codex 자신의 최초 초안을 외부 독립 승인으로 간주하지 않으며 사람의 운영 승인과 별개다.
- claim·tombstone은 축출하지 않으므로 프로세스 수명 동안 한도 도달 후 429가 지속된다(의도된 동작, 재시작으로만 초기화).
- 다중 워커/재시작 간 일관성 없음 — 시연 전용, 운영 영속 저장 **NOT_RUN**.
- 실제 장착·인증 연결·프런트 연동 검증은 루트 소유자 후속 작업이다.
