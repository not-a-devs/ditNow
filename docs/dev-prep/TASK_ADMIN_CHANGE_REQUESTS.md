# TASK-ADMIN-CHANGE — 관리 변경 제안 시연 워크플로 (FR-ADM-001/003 1차)

> 현재 상태: 2026-10-30, **독립 모듈 TESTED / 통합 PARTIAL**. Claude 작성·교정 후 Codex 실제 검증 결과는 마지막 절을 따른다. 아래 NOT_RUN은 Claude 작성 시점 기록이다. 라우터 미마운트·기본 503. 실제 인증·DB·역할 부여·승인 없음.
>
> 보정(2026-10-30): 초기 테스트는 Claude가 작성하고 Codex가 실행했다. 실행에서 pytest 45건 중 23건 FAIL(모델 전체 `strict=True`가 일반 JSON enum 문자열을 거부), Vitest 2건 FAIL(비정상 id 동기 throw, 고정 선택지 문구와 겹친 목록 판정), 타입검사 1건(키 생성기 반환형)이 발견되어 보정 중이다. 보정 내용: 필드 단위 strict(`expected_revision` 정수, `consent` StrictBool+True 요구), 공개 API 일관 비동기화, 생성/제출/철회 영수증의 요청 대응 검증(같은 대상·범위·사유 DRAFT 1 / 같은 id SUBMITTED 기대+1 / 같은 id WITHDRAWN +1) 및 음성 테스트 추가. 보정 후 테스트는 **미실행(NOT_RUN)**이며 최종 결과는 Codex가 확인한다.

## 1. 범위
- FR-ADM-001(사용자·조직·역할 관리), FR-ADM-003(신규 업무 역할) 중 **제안 기록만** 시연. DRAFT→SUBMITTED→WITHDRAWN, DRAFT→WITHDRAWN.
- 제외: APPROVED/실행/역할 부여/계정 생성/실제 사용자 조회/자유 입력. 승인·실행 엔드포인트 없음.
- 모든 데이터: `record_source=DEMO`, `storage=PROCESS_MEMORY`, `official_effect=false`, `restart_reset=true`(재시작 시 초기화).

## 2. 요구사항
| ID | 내용 |
| --- | --- |
| FR-1 | 신뢰 서버 actor(`user_id: UUID`, `can_manage: bool`)만 사용. 클라이언트 소유자·역할 무시. 매 읽기·쓰기마다 `can_manage is True` 확인, 아니면 403 |
| FR-2 | 고정 코드만: 대상 `STUDENT_DEMO_A/B`, 범위 `DEPARTMENT_STUDENT/YEAR_STUDENT`, 사유 `ACADEMIC_DEMO/CORRECTION_DEMO`, `consent: true` |
| FR-3 | 서버가 소유자 설정, 본인 목록만, 타인·미존재 id는 동일 404. 응답에 소유자 UUID 없음 |
| FR-4 | 철회는 tombstone(기록 보존). 비소거 |
| NFR-1 | 본문 `extra=forbid`, strict 열거형·bool·revision. path id UUIDv4 패턴, revision 1..1,000,000 |
| NFR-2 | RLock 하의 bounded memory: 소유자당 20건(tombstone 포함), 전체 500건, 키 소유자당 100·전체 2,000. 초과 429. **기술 한도이며 정책 아님** |
| NFR-3 | POST 멱등 키 필수(`[A-Za-z0-9-]{16,100}`), 소유자 범위. 같은 키+같은 의도→원 영수증 `replayed=true`, 다른 의도→409 |
| NFR-4 | CAS: submit `expected_revision`, DELETE `?revision`. 불일치·상태 위반 409 |
| NFR-5 | 성공·오류 모두 `Cache-Control: private, no-store`, 예외는 안전한 500 |
| NFR-6 | FE: requestData 경로 접두사 1회, 런타임 타입 가드, sessionGeneration 키 작업공간·useLayoutEffect 정리, 매 await 후 epoch 확인, 동기 busy ref, 401/403 시 개인 상태·동의 삭제 및 새 세대까지 비활성, 저장소 미사용, 새 GET이 영수증과 일치할 때만 성공 표시, 모호한 오류 자동 재시도 없음 |

## 3. API 계약 (`/api/v1` 하위, 미마운트)
| 메서드 | 경로 | 요청 | 응답 |
| --- | --- | --- | --- |
| GET | `/admin-change-requests` | – | 200 `SuccessResponse[ProposalList]` |
| POST | `/admin-change-requests` | `Idempotency-Key`, `{target_code, proposal_scope, reason_code, consent:true}` | 201 `SuccessResponse[ProposalView]` |
| POST | `/admin-change-requests/{id}/submit` | `Idempotency-Key`, `{expected_revision}` | 200 |
| DELETE | `/admin-change-requests/{id}?revision=N` | – | 200 (WITHDRAWN) |

- `ProposalView`: `id, target_code, proposal_scope, reason_code, state, revision, created_at, updated_at, submitted_at, withdrawn_at, record_source, storage, official_effect, restart_reset, replayed`.
- `ProposalList`: `items[], owner_cap` + 같은 DEMO 표식.
- 오류: 400 VALIDATION, 401(actor `None`), 403(`can_manage` 거짓), 404, 409, 429(기술 한도), 500, 503(기본/미주입).
- 주입: `get_actor` 의존성 override(기본 503), `app.state.admin_change_requests = AdminChangeRequestService()`(없으면 503).

## 4. 가정·차단 요소
- 가정: 통합 담당자가 현재 신원·역할을 매 요청 재검증해 `can_manage`를 계산한다. 이 작업은 그 계산을 구현하지 않는다.
- BLOCKED: 실제 관리자 역할 정의·부여, 승인 정책, 실DB 영속, 라우터 마운트, App 라우트 연결, 감사 원장 연계 — 별도 승인 필요(OPEN-002/003).
- DELETE는 멱등 키가 없어 FE가 자동 재시도하지 않고 재조회로 확인한다.

## 5. 파일 소유
- `services/api/app/features/admin_change_requests/{__init__,models,service,router}.py`
- `services/api/tests/test_admin_change_requests.py`
- `apps/web/src/features/admin-change-requests/{api.ts,api.test.ts,index.tsx,index.test.tsx}`
- 이 문서. 공유 파일(App/router/factory/auth/config/NAV/README) 미수정.

## 6. 테스트 (작성만, 미실행)
| TC | 내용 |
| --- | --- |
| TC-ACR-01 | 기본 앱 미마운트, actor/서비스 미주입 503 + no-store |
| TC-ACR-02 | 전체 수명주기·DEMO 표식·소유자 UUID 비노출·tombstone |
| TC-ACR-03 | 고정 코드 외·추가 필드·consent 비true·멱등 키 형식 400 |
| TC-ACR-04 | 교차 소유자 404·목록 비노출, 키 소유자 범위 |
| TC-ACR-05 | 권한 회수 후 읽기·쓰기·재생 모두 403, 미인증 401 |
| TC-ACR-06 | 멱등 재생·충돌, CAS 409, strict revision |
| TC-ACR-07 | 동시 submit 단일 승자, 동일 키 동시 create 1건 |
| TC-ACR-08 | 소유자·키 한도 429, 재시작 초기화, naive clock 503, 안전한 500 |
| TC-ACR-FE-01~ | 가드·경로 접두사·키 재사용·영수증 일치, 동의 없는 쓰기 차단, 불일치 성공 미표시, 자동 재시도 없음, busy 이중 클릭, 401/403 정리·비활성·새 세대 복구, 늦은 조회/쓰기 응답 무시, 503, 저장소 미사용 |

명령(NOT_RUN):
```
cd services/api && uv run pytest tests/test_admin_change_requests.py && uv run ruff check app/features/admin_change_requests tests/test_admin_change_requests.py
cd apps/web && npm run typecheck && npx vitest run src/features/admin-change-requests
```

## 7. TODO
- 통합 담당자의 actor 공급자·마운트·App 라우트 연결(별도 승인).
- 실행 결과에 따른 테스트 보정(Codex 실행·리뷰).

## Codex 실제 검증 (2026-10-30)

- FR-ADM-001/003 / TC-V1-ADM-001/003. NFR-SEC-002/003/005/006, NFR-PRIV-002/003, NFR-REL-003/004, NFR-UX-001/004/005에 연결하며, 실제 권한·DB 영속성 전체 충족을 주장하지 않는다.
- BE 55 PASS, FE 19 PASS, 전체 신규 웹 573 PASS. 모의 신원·메모리 원장 및 HTTP TestClient 테스트이며 실제 학교·실제 DB 검증이 아니다.
- 잠금 의존성 설치, 신규 웹 타입 검사·빌드, Ruff 정적/포맷 검사, 에이전트 105경로/8스킬, 기능 추적표 92 ID 검사 PASS. 기본 통합 앱은 미마운트로 보존했다.
- 최초 구현은 Claude 제한 세션, 실패 교정은 추가 Claude 제한 세션 1개가 세 작업 트리의 각 허용 기능 파일만 수정했다. Codex는 소스 검토·명령 실행·Ruff 자동 포맷을 수행했다.
- 미해결 통합 게이트: 현재 공통 신원·운영자 권한 브리지 및 업무 포트 승인, 공통 bearer/no-store 보호 prefix 등록(405 등 라우팅 오류 포함), 앱 연결, 운영 남용 제한, DB/영속 원장이다. 클라이언트 역할 값이나 시연 편의상 true 권한으로 이를 대체하지 않는다.
- 변경 파일 소유 범위 밖의 NAV/상태표/공통 파일 갱신은 root 통합 담당자 소유다. 실제 사용자·관리자 계정 생성·외부 호출·DB·배포·자동 병합은 수행하지 않았다.

- 최종 전체 API 회귀: 1568 PASS, 기존 Starlette 경고 1개. 원격 DB·실제 인증·학교 업무 호출 없이 수행했습니다.
