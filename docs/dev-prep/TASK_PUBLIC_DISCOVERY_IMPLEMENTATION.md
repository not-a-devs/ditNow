# TASK-P 공개 통합검색 1차 구현

2026-10-30 · FR-HOME-002의 **공개 자료 부분** · TC-V1-HOME-002 · NFR-UX-001/004, NFR-SEC-002, NFR-PRIV-001/003.

## 범위와 완료 기준

공개 대학·학과 편집 안내와 출처 미검증 시설 스냅샷을 기존 서비스에서 읽어 정규화 검색·종류 필터·통합 페이지·근거 및 내부 이동을 제공한다. 개인 시간표·성적·신청·대화 및 보호 자료 검색은 **미구현**이다. 전체 FR-HOME-002 완료로 표시하지 않는다.

원장·검색 자료를 복제하지 않고 `PublicCampusService.list_guides`와 기존 `CampusSearch.search`를 재사용한다. 신규 DB·계정·외부 fetch·학교 비공개 API·LLM·유료 서비스·인증 정책 변경은 없다. 기존 `mvp/` 소스는 읽거나 복사하지 않았다.

## 계약

`GET /api/v1/discovery?q=...&kind=all|guide|facility&offset=0&limit=10`

- q: 1~200자. NFKC·casefold·공백 정규화, 공백/기호만 입력 및 보이지 않는 제어 문자 거부.
- kind: `all` 기본값. offset 0~200, limit 1~20. 공통 성공/오류 envelope 사용.
- 대학 안내는 기존 최대100개 스냅샷을 기존50개 페이지로 읽는다. 시설은 기존 어댑터에서 최대101개를 조회해100개로 제한하고 초과를 확인한다.
- `(kind, source ID)`로 정렬하며 종류별 ID namespace를 둔다. 점수가 같은 시설이 재조회돼도 같은 bounded 후보 집합에서는 페이지가 안정적이다.
- `total`/`counts`는 수집된 유효 후보 수다. `complete=false`는 후보 상한·부적합/중복 source ID 등으로 완전한 집계가 아님을 뜻한다. UI는 일부 범위 안내를 표시한다. 실시간 학교 전체 검색량이라고 주장하지 않는다.
- 대학 근거: 공식 페이지 존재 VERIFIED, 처리 규칙 PARTIAL, 최신성 UNKNOWN 및 확인 날짜/원문. 이는 편집 요약이며 학교의 현재 공식 처리 정책을 보장하지 않는다.
- 시설 근거: 기존 시설 JSON, verification UNKNOWN. 공식 안내와 합쳐 VERIFIED로 승격하지 않는다.
- `generated=false`, `personal_data_access=false` 고정. 외부 source URI를 API가 fetch하지 않는다.
- 상세 경로는 서버가 고정한 `/app/information?guide=<encoded ID>` 또는 `/app/ai?q=<encoded name>`뿐이다. 프런트도 경로·단일 파라미터·종류와 근거의 일치를 검증한다.

공통 router와 App·navigation·OpenAPI·NAV는 공유 소유자가 통합한다. 대상 대학/시설 화면의 query 초기값 처리 역시 공유 소유자 범위다. 이 모듈 단독 커밋 시점의 실제 앱 탐색 통합·브라우저 전체 여정은 **NOT_RUN**이며, 공유 통합 후 다시 검사해야 한다.

## 파일과 상태

| 경로 | 책임 | 상태 |
| --- | --- | --- |
| `services/api/app/features/discovery/` | 공개 서비스 조합, DTO, dependency router | IMPLEMENTED / TESTED(전용 테스트 앱) |
| `services/api/tests/test_discovery.py` | 정규화·전역 정렬/페이지·100개 상한·근거·400/503 | TESTED |
| `apps/web/src/features/discovery/` | 검색 폼·필터·집계·근거·내부 링크·재시도·검증 | IMPLEMENTED / TESTED(Vitest) |
| 공유 router/App와 대상 deep link | 신규 앱 실제 진입/이동 | 통합 담당자 작업 |

요청은 공통 `requestData('/discovery?...')`로 API prefix를 한 번 적용한다. 결과 도착 시 제목으로 focus를 이동하고, 진행/빈/오류 상태를 구분한다. 실패 재시도와 페이지 이동은 적용된 검색을 유지하며 수정 중인 입력 초안을 덮어쓰지 않는다. 화면 이탈·새 요청 시 이전 요청을 취소하고 늦은 응답을 무시한다. 원본 예외나 잘못된 응답을 화면에 표시하지 않는다.

## 검증 증거

- API 전용 pytest 18개 성공: Unicode 정규화, 종류 선택 시 불필요 source 미호출, 안내100개/시설 상한101번째 확인, 안정적 합산 페이지, 중복/부적합 source ID, 빈 결과, 입력400, 공통 envelope, 공급자503. 실제 기존 공개 source 어댑터의 시설 ID 조회·개인 성적 질의 빈 결과도 로컬에서 확인했다.
- FE 전용 Vitest 15개 성공: 입력/폼 제출, 근거 차이, 내부 링크, 재시도 초안 보존, 페이지 검색 유지, 빈/로딩/취소, 응답·출처·집계·링크 위장 거부, 실제 공통 client의 prefix 계산.
- 실제 브라우저 390/1280·keyboard: 모듈 단독 시점 **NOT_RUN**, 공유 통합 후 담당자 검사 필요.
- 원격 DB/실제 신원/배포/개인 검색: **NOT_RUN / 범위 밖**.

PR 최종 HEAD에서 전체 API/웹 회귀·정적 검사·타입·빌드와 실제 CI를 다시 확인한다. 독립 AI 리뷰는 사람의 정책 승인을 대신하지 않는다.
