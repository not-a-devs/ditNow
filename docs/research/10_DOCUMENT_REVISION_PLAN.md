# 기존 17개 패키지 파일 개정 계획

**계획만 작성했다.** 기존 파일은 이번 작업에서 수정하지 않았다. 우선순위는 “v1.0 명세의 정확성” 기준이며 [해커톤 P0/P1/P2](../09_RELEASE_SCOPE.md)를 변경하는 제안이 아니다. 결정 변경은 [DECISION_LOG 프로토콜](../11_DECISION_LOG.md)을 따른다.

| 기존 파일 | v1.0에서 반영할 내용 | 선행 근거/결정 |
|---|---|---|
| `00_START_HERE.md` | 16 Markdown+manifest 17파일 구분, research 증거 우선순위/확인 수준 정의 | [01 감사](01_CURRENT_DOCUMENT_AUDIT.md) |
| `01_PRD.md` | 지원자/졸업생/사서/상담자/생활관·기업 페르소나, 공개 사이트·업무 서비스의 장기 여정 | [02](02_OFFICIAL_SITE_INVENTORY.md), [03](03_CONNECTED_SYSTEMS_AUDIT.md); DEC-001~014 유지 |
| `02_FRD.md` | [CSV 신규 44 ID](04_FULL_FEATURE_CATALOG.csv) 반영; `FR-ACA-002`, `FR-CAMP-001`을 새 ID 참조 상위 항목으로 정리; 입력/출력/CRUD/상태/예외/AC 확장 | [05](05_FUNCTIONAL_REQUIREMENTS_GAPS.md); OPEN-R01~R16 |
| `03_NFR.md` | `NFR-ID-001~002`, `PRIV-004~005`, `SEC-008~009`, `REL-006~008`, `OPS-005~006`, `UX-006~007`, `AI-005` 후보 추가 | [06](06_NON_FUNCTIONAL_REQUIREMENTS_GAPS.md); 운영 수치 승인 |
| `04_POLICY_RBAC.md` | 지원자/졸업생/사서/상담·고충 담당/생활관/기업/입학·재무 담당의 범위 매트릭스, 신원 전환 | OPEN-R01/04/05/06/07/08/12 |
| `05_DATA_MODEL.md` | 출처 원장, 학사·입학·증명·도서·생활관·민원/상담 엔터티와 상태/무결성 추가 | [07](07_DATA_PROVENANCE_AND_SEEDS.md); 운영 원장 결정 |
| `06_ARCHITECTURE.md` | 내부 가상 원장과 향후 학교 시스템 동기화 경계; 이벤트/검색/알림 일관성; 외부 발급/결제 경계 | [08](08_INTEGRATION_ARCHITECTURE.md); OPEN-R02/06 |
| `07_IA_UX.md` | 공개 방문자·지원자·학생·졸업생·교직원·사서·상담자 화면; 공식/시연 배지; 신청 상태 | [02](02_OFFICIAL_SITE_INVENTORY.md), [05](05_FUNCTIONAL_REQUIREMENTS_GAPS.md) |
| `08_TEST_QA.md` | 입학/학사/출결/도서·예약/민감 상담의 권한·경합·상태·시연 오인 테스트 | [05](05_FUNCTIONAL_REQUIREMENTS_GAPS.md), [06](06_NON_FUNCTIONAL_REQUIREMENTS_GAPS.md) |
| `09_RELEASE_SCOPE.md` | 새 기능은 장기 설계 범위로만 표시; 해커톤 구현 약속 확대 금지 | DEC-002, 기존 P0/P1/P2 유지 |
| `10_AI_RUNBOOK.md` | 기능별 `existence_level`/`rule_level`/출처 확인 게이트와 미확인 질문 에스컬레이션 | [04 CSV](04_FULL_FEATURE_CATALOG.csv), [09](09_UNVERIFIED_AND_OPEN_QUESTIONS.md) |
| `11_DECISION_LOG.md` | OPEN-R01~R15를 팀 검토용으로 제안; 확정 기록은 실제 승인자·날짜 후에만 | [09](09_UNVERIFIED_AND_OPEN_QUESTIONS.md) |
| `12_HACKATHON_GATE.md` | 2026 행사 규칙은 이력으로 유지; 장기 제품 NFR로 혼입 금지 | 공식 대회 최신 안내 재확인 필요 |
| `13_EXISTING_SERVICE_AUDIT.md` | 이 폴더의 공개 메뉴/연결 시스템/출처를 링크하고 템플릿 상태 해소 | [02](02_OFFICIAL_SITE_INVENTORY.md), [03](03_CONNECTED_SYSTEMS_AUDIT.md), [04 CSV](04_FULL_FEATURE_CATALOG.csv) |
| `14_GLOSSARY.md` | 아레테/ASTRA·캠퍼스락·지원자·시연 데이터·존재/규칙 검증·공식 원장 정의 | [03](03_CONNECTED_SYSTEMS_AUDIT.md), [07](07_DATA_PROVENANCE_AND_SEEDS.md) |
| `15_PLATFORM_BASELINE.md` | 각 항목을 확인됨/부분/가정/미확인으로 매핑; 출결·입학·증명·도서·생활관 명시 | [04 CSV](04_FULL_FEATURE_CATALOG.csv) |
| `manifest.json` | `read_order`에 13·14 포함, research 11개 파일 경로·버전/상태 표시 | [01 감사](01_CURRENT_DOCUMENT_AUDIT.md) |

## 권장 개정 순서와 게이트

1. 담당자가 `OPEN-R01~R06` 및 기존 `OPEN-001~009` 중 v1.0에 필요한 결정을 승인·보류한다.
2. `11_DECISION_LOG`에 실제 승인/보류 상태를 기록한 뒤 PRD→FRD/RBAC→데이터 모델/아키텍처→UX/NFR/QA 순으로 동시 대조한다.
3. `FR-ACA-002`, `FR-CAMP-001` 기존 ID를 삭제하지 않고 “상위/이전 호환 참조”로 남긴다. 새 ID 44개의 중복 검사 및 수용 조건을 연결한다.
4. 각 사실 주장에 원본 URL·확인일을 달고, 학교 처리 규칙 미확인은 `UNKNOWN`으로 남긴다. 제품 설계안은 학교 사실과 분리한다.
5. 마지막에 manifest/read order/용어/추적표를 갱신한다. **이번 작업 이후 자동 개정·개발 착수는 하지 않는다.**

저장소 루트 [README](../../README.md)의 AI 길찾기 중심 제품 설명/스택과 확정 [PRD](../01_PRD.md)·[결정 대장](../11_DECISION_LOG.md)의 통합 캠퍼스 방향이 충돌한다. 이는 17개 패키지 바깥의 별도 포지셔닝 개정 후보이며 이번 작업에서 README를 바꾸지 않았다. [mvp/README](../../mvp/README.md)의 localStorage 시연 범위도 “서버 DB 완료”로 승격하지 않는다. `NAV.md`는 이미 `docs/research/` 경로와 이 충돌을 안내하므로 이번 조사 파일 추가만으로 탐색 경로 수정은 필요하지 않다.
