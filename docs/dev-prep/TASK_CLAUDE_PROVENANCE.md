# TASK_CLAUDE_PROVENANCE — 출처·시연 데이터 표시 안내 (FR-ADM-004 일부)

> 상태: 2026-10-30 · 작성: Claude (builder) · 테스트/리뷰/커밋/PR: Codex 별도 수행
> 검증: Claude 작성 당시 **NOT_RUN**. 이후 Codex의 격리 테스트 결과는 아래에 별도 기록한다. 관리 업무·전체 FR 완료를 주장하지 않는다.

## 범위
- FR-ADM-004 중 **출처 라벨의 의미 설명과 공통 출처 배지 표시**만 구현한다.
- 출처 등록·수정·게시 승인(초안>검증>게시), 소유자·변경 이력, 관리자 화면, `source_records` 저장은 **구현하지 않았다**(content_administration = `NOT_IMPLEMENTED`).
- 관리자 권한·실제 데이터·학교 통합 로그인(SSO)·금전 효력은 없다.

## 파일
| 영역 | 경로 |
| --- | --- |
| BE DTO | `services/api/app/features/data_provenance/schemas.py` |
| BE 고정 카탈로그 | `services/api/app/features/data_provenance/service.py` |
| BE 라우터 | `services/api/app/features/data_provenance/router.py` |
| BE export | `services/api/app/features/data_provenance/__init__.py` |
| BE 테스트 | `services/api/tests/test_data_provenance.py` |
| FE 모델/가드 | `apps/web/src/features/data-provenance/models.ts` |
| FE 공통 배지 | `apps/web/src/features/data-provenance/SourceLabel.tsx` |
| FE 페이지 | `apps/web/src/features/data-provenance/index.tsx` |
| FE 스타일 | `apps/web/src/features/data-provenance/styles.module.css` |
| FE 테스트 | `apps/web/src/features/data-provenance/index.test.tsx` |

## API 계약 (루트 소유자가 `/api/v1` 아래 mount 해야 노출됨 — 현재 미mount)
- `GET /api/v1/data-provenance` → `SuccessResponse[ProvenanceOverview]`
- `GET /api/v1/data-provenance/labels/{label}` → `SuccessResponse[ProvenanceLabelInfo]`; `label ∈ DEMO|OFFICIAL_PUBLIC|PLATFORM|UNKNOWN`, 그 외 400 `VALIDATION`
- DTO: `ProvenanceLabelInfo{label,title,description,user_guidance}`, `ProvenanceStatus{school_sso_connected:false, financial_effect:"NONE", persistence:"IN_PROCESS_FIXED", content_administration:"NOT_IMPLEMENTED"}`, `ProvenanceOverview{catalog_version,feature_ids,notice,status,labels[4]}`
- 공통 규칙: `PrivateNoStoreRoute`(성공·오류 모두 `Cache-Control: private, no-store`), 공통 `ErrorResponse` 봉투, 쿼리 파라미터는 종류와 관계없이 400(임의 URL 입력 차단), GET만 제공.
- 공개 안내이므로 actor를 읽지 않는다. 클라이언트가 보낸 사용자·학과·역할 헤더는 응답에 영향을 주지 않는다. 향후 보호 경로가 추가되면 루트가 공통 actor를 주입해야 한다.
- fail-closed: 카탈로그가 네 라벨을 정해진 순서로 정확히 한 번씩 갖지 않으면 503 `UNAVAILABLE`; 의존성 예외는 500 `INTERNAL`(상세 비노출).
- 주입점: `create_data_provenance_router(DataProvenanceDependencies(catalog=...))`; 기본 `router`는 고정 카탈로그.

## 데이터
- 고정 합성 문구만 프로세스 메모리에 둔다. MariaDB 저장·시드·마이그레이션 없음, 재시작 시 동일 내용으로 재생성. UUID·비밀값·설정 목록·URL을 응답에 포함하지 않는다.

## 테스트 (작성됨, NOT_RUN)
- BE: 네 라벨·상태 상수, 라벨별 조회, 미지 라벨 400, 쿼리 거부, 신원 헤더 무시, GET 전용, UUID/URL/비밀 문자열 부재, 불완전·순서 변경·중복 카탈로그 503, 의존성 예외 500, 복사본 반환·재시작 동일성.
- FE: 네 배지 각각, 미지 값→`UNKNOWN`, 페이지가 고정 경로만 요청·네 라벨·상태 표시, 잘못된 응답(SSO true 등) 거부와 재시도, 네트워크 실패 status 알림, `isOverview` 가드.

## 한계·후속
- App 라우트·내비게이션·전역 router mount·`api.ts` 타입 생성·OpenAPI 스냅샷·NAV/진척 CSV는 이 작업의 쓰기 범위 밖이라 갱신하지 않았다(루트 소유자 후속).
- 다른 화면에서 `SourceLabel`을 실제로 쓰도록 연결하는 작업은 하지 않았다.
- 관리 워크플로(CRU·승인·감사)와 RBAC-ADM은 정책 미확정(UNKNOWN)으로 BLOCKED.

## Codex 독립 검증 및 보완 — 2026-10-30
- Claude 종료 후 제한 경로 소스·DTO·질의 거부·오류와 테스트를 읽었다. 공개 설명 고정 값만 응답하며 실제 데이터 원장/관리자 기능을 제공하지 않는다.
- App 안의 중첩 main을 피하도록 페이지 root를 section으로 바꾸었다. 오류 표시는 비동기 최종 문구를 기다리게 정정했고 StrictMode의 취소된 이전 요청 실패가 현재 성공을 지우지 않는 회귀를 추가했다.
- BE `pytest -q tests/test_data_provenance.py` **20 PASS**; FE 전용 **10 PASS**; TypeScript·빌드 PASS. scoped Ruff check/format PASS(초기 포맷1개 정정).
- npm 잠금 설치는 offline 캐시만 사용. 실제 App/router 연결·관리 승인·DB·운영 서버·브라우저는 **NOT_RUN**. 이 설명 UI는 출처 등록/검증/게시/감사 관리 완료가 아니다.
