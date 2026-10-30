# TASK-NOTICE-ACK — 공지 확인 요청·확인 집계 (FR-NOT-004) 1차 구현

> 현재 상태: 2026-10-30, **독립 모듈 TESTED / 통합 PARTIAL**. Claude 작성 후 Codex 실제 검증 결과는 마지막 절을 따른다. 아래 NOT_RUN은 Claude 작성 시점의 기록이며 실제 인증·DB·배포·운영 승인 주장은 없다.
>
> 보정(2026-10-30): 초기 테스트는 Claude가 작성하고 Codex가 실행했다(초기 실행 BE 15건·FE 8건 PASS). 리뷰에서 발견된 점을 보정 중이다: 본인 상태 GET 응답이 FE 가드(`can_request` 포함 정확한 키 집합)와 맞는지 확인하는 HTTP 계약 테스트 추가, 모호한 실패 뒤 재시도 의도(Intent)에 확인 대상 `request_revision`을 고정해 개정이 바뀌면 새 키를 쓰도록 수정하고 회귀 테스트 추가(재개 정책은 새로 만들지 않음). 보정 후 테스트는 **NOT_RUN**이며 최종 결과는 Codex가 확인한다.

## 1. 범위 (TASK / FR / NFR)
- FR-NOT-004 확인 요청·읽음 통계(정책 기반)의 **휴면(dormant) 1차 구현**. 라우터는 앱에 mount하지 않는다.
- 공지 소유자가 기존 권위 공지 참조(UUID)에 대해 명시적 opt-in으로 확인 요청을 만들고, 현재 대상자는 본인 확인만 기록하며, 소유자는 **개인 식별 없는 집계**(대상 수·확인 수)만 본다.
- 모든 데이터: `record_source=DEMO`, `storage=PROCESS_MEMORY`, `official_effect=false`, `restart_reset=true`. 프로세스 재시작 시 전부 초기화.
- NFR: 성공·오류 응답 모두 `Cache-Control: private, no-store`, 안전한 오류(본문·식별자 비노출), 요청 본문 `extra=forbid`·엄격 bool/int, RLock 하의 상한 있는 메모리 저장소, 공지 본문 중복 저장·반환 없음.

## 2. API 계약 (prefix `/notice-acknowledgements`, mount 시 `/api/v1` 아래)
| 메서드·경로 | 요청 | 응답 `data` | 권한 |
| --- | --- | --- | --- |
| `POST /request` | 헤더 `Idempotency-Key` (`^[A-Za-z0-9_-]{16,128}$`), 본문 `{notice_id: UUID, opt_in: true, revision?: int≥0}` | `{notice_id, request_revision}` + DEMO 플래그 | 현재 공지 소유자만 |
| `GET /{notice_id}` | — | `{notice_id, requested, request_revision\|null, can_request, can_acknowledge, acknowledged, acknowledged_at\|null, can_view_summary}` + DEMO 플래그 | 현재 소유자 또는 현재 대상자 |
| `POST /{notice_id}/ack` | 헤더 `Idempotency-Key`, 본문 `{request_revision: int≥1}` | `{notice_id, request_revision, acknowledged: true, acknowledged_at}` + DEMO 플래그 | 현재 대상자 본인만 |
| `GET /{notice_id}/summary` | — | `{notice_id, request_revision, eligible_total, acknowledged_count, audience_basis: "TRUSTED_PORT_CURRENT"}` + DEMO 플래그 | 현재 소유자만 |

- `opt_in`은 반드시 JSON `true`. `false`/누락/문자열은 400이며 요청을 만들지 않는다.
- `revision`: 생략=없으면 생성·있으면 현재 반환, `0`=아직 없어야 함, `N`=현재 요청 revision과 같아야 함(불일치 409).
- `ack`의 `request_revision`이 현재와 다르면 409. 이미 확인했으면 기존 시각을 반환(중복 기록 없음).
- 멱등 키: (actor, 작업, notice_id, key) 네임스페이스. 같은 키+같은 본문=저장된 결과 재생, 다른 본문=409. 재생 전에도 현재 접근 권한을 재검사.
- 오류: 공지 없음·접근 불가=404(존재 비노출), 접근 가능하나 역할 불일치=403, 포트 응답 불일치/대상 상한 초과=503, 저장 상한=429, 기본(미구성)=503.
- 응답에 소유자·학생 UUID·이름·공지 본문 없음.

## 3. 신뢰 경계·가정
- `get_actor`는 기본 503. 승인된 공통 신원 브리지만 서버 검증 `Actor(user_id)`를 주입한다. 본문으로 소유자·역할·대상 지정 불가.
- 서비스는 `app.state.notice_acknowledgements`에 명시 주입된 `NoticeAcknowledgementService`만 사용, 없으면 503.
- `NoticeAccessPort.resolve(notice_id)`가 기존 캠퍼스 공지 원장의 **현재** 소유자·대상(상한 10,000)·대상 수를 매 작업마다 반환. `eligible_total != len(audience)`이면 fail-closed(503). 정책 추론 없음.
- 잠금/UOW: 메모리 구현은 하나의 RLock 안에서 포트 조회·CAS·멱등 claim·쓰기를 수행. DB 어댑터는 같은 트랜잭션에서 공지 행→요청→확인/claim 순으로 잠그고 실패 시 전체 롤백해야 함(`ports.py` 문서화).
- 대상에서 제외되면 상태 조회·확인 불가(404), 집계는 현재 대상과 교집합만 센다. 소유자 변경 시 이전 소유자는 집계 불가.
- 상한: 요청 1,000 / 확인 50,000 / 멱등 claim 50,000.

## 4. 프런트엔드
- `apps/web/src/features/notice-acknowledgements/`: `sessionGeneration` 키로 작업공간 재생성, `initialNoticeId` 주입 가능, 라우트 미연결.
- `requestData` 경로에 `/notice-acknowledgements` 접두사 1회, 모든 응답 런타임 가드(정확한 키·DEMO 플래그·notice_id 일치).
- 모든 await 후 epoch 확인, 동기 busy ref, `useLayoutEffect` 정리(abort·epoch 증가), 401/403 시 모든 개인 상태·동의 삭제 후 새 세대까지 비활성화, 저장소 사용 없음.
- 쓰기는 체크박스 동의 후에만, 성공 표시는 POST 영수증과 새 GET 결과가 일치할 때만. 불확실한 실패(0/5xx)는 자동 재시도 없이 같은 의도의 같은 키로 수동 재시도.
- UUID·개인 식별을 화면에 출력하지 않는다(입력창 값 제외).

## 5. 테스트 (작성만, NOT_RUN)
- `services/api/tests/test_notice_acknowledgements.py`: opt-in false/추가 필드 거부, 소유자·대상 흐름, 요청 없음, 타 소유자·비소유자 403/404, 대상 철회·소유자 이전 즉시 반영, 포트 불일치 fail-closed, 요청/확인 CAS, 멱등 재생·본문 충돌·actor 네임스페이스, 상한, 동시성(요청·확인 단일 기록), 기본 503·no-store·전역 미노출, HTTP 흐름·식별자 비노출, 내부 오류 안전 응답.
- `apps/web/src/features/notice-acknowledgements/index.test.tsx`: 기본 503, 동의 전 무쓰기·접두사 1회·이중 클릭 1회 전송, 영수증 불일치 시 성공 미표시, 불확실 실패 후 같은 키 수동 재시도, 소유자 요청·집계(UUID 미표시), 401/403 정리·세대 교체 복구, 늦은 응답 무시, 응답 가드·잘못된 참조.

```
cd services/api && uv run pytest tests/test_notice_acknowledgements.py   # NOT_RUN
cd apps/web && npm test -- src/features/notice-acknowledgements          # NOT_RUN
```
(정확한 실행 명령은 저장소 README 기준으로 Codex가 확인)

## 6. 파일 소유
- `services/api/app/features/notice_acknowledgements/{__init__,models,ports,service,router}.py`
- `services/api/tests/test_notice_acknowledgements.py`
- `apps/web/src/features/notice-acknowledgements/{api.ts,index.tsx,index.test.tsx}`
- `docs/dev-prep/TASK_NOTICE_ACKNOWLEDGEMENTS.md`

## 7. 차단·후속 (BLOCKED/TODO)
- BLOCKED: 실제 공통 신원 브리지(`get_actor`), 캠퍼스 공지 원장 기반 `NoticeAccessPort` 어댑터, MariaDB 스키마·UOW, 앱 mount·라우트 연결 — 별도 승인 필요.
- 확인 대상 정책(누가 대상인지)·공식 효력 여부는 미확정 정책으로 이 모듈이 결정하지 않는다.
- 요청 재개(새 라운드)·마감·알림 연동은 범위 밖.
- 공유 파일(NAV, 상태 CSV, App/router)은 수정하지 않았다.

## Codex 실제 검증 (2026-10-30)

- FR-NOT-004 / TC-V1-NOT-004. NFR-SEC-002/003/005/006, NFR-PRIV-002/003, NFR-REL-003/004, NFR-UX-001/004/005에 연결하며, 실제 권한·DB 영속성 전체 충족을 주장하지 않는다.
- BE 16 PASS, FE 9 PASS, 전체 신규 웹 563 PASS. 모의 신원·메모리 원장 및 HTTP TestClient 테스트이며 실제 학교·실제 DB 검증이 아니다.
- 잠금 의존성 설치, 신규 웹 타입 검사·빌드, Ruff 정적/포맷 검사, 에이전트 105경로/8스킬, 기능 추적표 92 ID 검사 PASS. 기본 통합 앱은 미마운트로 보존했다.
- 최초 구현은 Claude 제한 세션, 실패 교정은 추가 Claude 제한 세션 1개가 세 작업 트리의 각 허용 기능 파일만 수정했다. Codex는 소스 검토·명령 실행·Ruff 자동 포맷을 수행했다.
- 미해결 통합 게이트: 현재 공통 신원·운영자 권한 브리지 및 업무 포트 승인, 공통 bearer/no-store 보호 prefix 등록(405 등 라우팅 오류 포함), 앱 연결, 운영 남용 제한, DB/영속 원장이다. 클라이언트 역할 값이나 시연 편의상 true 권한으로 이를 대체하지 않는다.
- 변경 파일 소유 범위 밖의 NAV/상태표/공통 파일 갱신은 root 통합 담당자 소유다. 실제 사용자·관리자 계정 생성·외부 호출·DB·배포·자동 병합은 수행하지 않았다.

- 최종 전체 API 회귀: 1529 PASS, 기존 Starlette 경고 1개. 원격 DB·실제 인증·학교 업무 호출 없이 수행했습니다.
