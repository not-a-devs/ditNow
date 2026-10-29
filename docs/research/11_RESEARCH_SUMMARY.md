# DIT Campus v1.0 근거 조사 요약

조사일: **2026-10-29 KST**. 결과물은 기존 v0.2를 수정한 v1.0 확정본이 아니라 **v1.0 작성을 위한 근거와 보완안**이다. 애플리케이션 코드·마이그레이션은 작성하지 않았다.

## 정량 결과

| 지표 | 결과 | 계산 기준 |
|---|---:|---|
| 기존 패키지 | 17파일 | `docs/` Markdown 16 + `manifest.json` 1 |
| 기존 FRD ID | 48 | `02_FRD.md` 기능 카탈로그 |
| 신규 보완 기능 ID | **44** | `04_FULL_FEATURE_CATALOG.csv`의 `prior_frd_id` 공란 |
| 조사 카탈로그 합계 | **92** | 기존 48 + 신규 44; ID 중복 0 |
| 존재 수준 `VERIFIED` | **40** | 공개 공식 페이지/공지의 기능·메뉴 확인 |
| 존재 수준 `PARTIAL` | **17** | 관련 기능은 있으나 동일 범위/세부가 불완전 |
| 존재 수준 `INFERRED` | **26** | 제품 결정 또는 일반 설계 후보; 학교 현행 주장 아님 |
| 존재 수준 `UNKNOWN` | **9** | 공개 근거 부족 |
| 처리 규칙 `PARTIAL` / `UNKNOWN` | **36 / 56** | 규칙 `VERIFIED`는 0; 로그인 이후 정책·운영 규정 미확인 |

수치는 [CSV](04_FULL_FEATURE_CATALOG.csv) 행 단위이며 홈페이지의 “모든 기능 총수”가 아니다. 44건은 기존 FRD에서 **독립 상세 ID가 없거나 거대한 항목 안에 묶인 보완 기능 수**다. 이 중 40건은 공개 페이지에서 기능/메뉴 존재 확인, 2건은 부분 확인, 2건은 설계 후보. 학교의 모든 내부 기능을 확인했다는 뜻이 아니다.
기존 FRD의 복합 항목 7개(FR-NOT-001, FR-NOT-003, FR-OPP-001, FR-COURSE-003, FR-COURSE-004, FR-ATT-001, FR-ACA-001)는 공개 페이지에서 일부 동작만 확인되므로 존재 수준을 PARTIAL로 보수적으로 분류했다. 작성·수정·삭제·이력·상태 전이는 확인되지 않은 범위다.

## 주요 확인

- 대학 메인에는 대학소개, 대학생활(공지/학사/복지/생활/취업/아레테), DIT 소식과 입학·학과 링크가 있다. [대학 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=compusvr), [입학 메뉴](https://www.dit.ac.kr/ipsi/).
- 수강신청은 학생정보시스템에서 개설강좌 조회·선택·시간표/내역 확인으로 안내된다. 학사일정·휴복학·재입학·전과·증명서 안내도 공개돼 있다. [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo), [학사일정](https://www.dit.ac.kr/kr/index.php?pCode=univschedule), [증명 안내](https://www.dit.ac.kr/kr/index.php?pCode=certificate).
- 아레테/ASTRA 공지는 온라인 강의·출석 확인·과제·시험·공지·질의응답을 명시한다. 캠퍼스락 공지는 별도 대면 전자출결과 모바일학생증 도입을 명시한다. [LMS 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice), [캠퍼스락 공지](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11).
- 도서관은 검색·전자자료·대출현황/연장/예약·희망도서·그룹 공간 예약 메뉴, 취업센터는 채용·이력서/희망진로·프로그램/상담·기업 채용의뢰 메뉴를 제공한다. [도서관](https://library.dit.ac.kr/Cheetah/DITL/Index/), [취업센터](https://job.dit.ac.kr/page/main/).
- 생활관 신청/확인, 입학 지원/결과/납부 조회, 사이버민원·고충·장애학생지원이 공개 메뉴로 확인된다. [생활관](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities), [입학](https://www.dit.ac.kr/ipsi/), [민원](https://www.dit.ac.kr/kr/index.php?pCode=cybersvccenter).
- 성적포기 안내는 상담·서면 신청과 학생정보시스템 결과 조회를 설명하고, 디지털 배지 공지는 이수→발급→이메일/지갑 수령을 설명한다. 복지시설 페이지는 운영시간과 시설물 사용신청서 링크를 제공한다. [성적포기](https://www.dit.ac.kr/kr/index.php?pCode=scorerenounce), [배지 공지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice), [시설](https://www.dit.ac.kr/kr/index.php?pCode=welfareinfo).

## 설계 충돌과 시급한 결정

1. `FR-ACA-002`/`FR-CAMP-001`에 너무 많은 업무가 묶여 있다. 44개 신규 ID로 분해하되 원 ID는 상위 참조로 보존한다.
2. `FR-ATT-001`의 코드/QR 옵션은 현행 캠퍼스락의 블루투스/인증번호와 같다고 볼 수 없다. 온라인 LMS 출석과 대면 출결의 권위 원장·대사 규칙도 미정이다. [캠퍼스락 공지](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11), [LMS 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice).
3. 독립 플랫폼 비전과 현재 **학교 데이터·SSO 실제 연동 금지**를 장기/시연 범위로 분리해야 한다. [PRD](../01_PRD.md).
4. 가장 급한 결론은 신원·학적/출결 원장(`OPEN-R01~R03`), 입학/납부/환불(`R04`), 고충 비밀 처리(`R05`), 공식 증명/결제(`R06`)의 운영 주체와 권한이다. 현재 시연 데이터로만 흐름을 설계한다. [미확인 목록](09_UNVERIFIED_AND_OPEN_QUESTIONS.md).
5. [루트 README](../../README.md)의 AI 길찾기 중심 “DIT NOW” 설명/기술 스택과 확정 [PRD](../01_PRD.md)의 통합 캠퍼스 방향이 다르다. [사전 MVP](../../mvp/README.md)는 브라우저 저장 시연이므로 서버 보안·DB 구현 완료로 볼 수 없다. 기존 파일은 수정하지 않았다.

## 범위와 한계

공개 메뉴와 대표 상세 페이지·공식 공지, 학과 표본 2곳을 열람했다. 학생정보·아레테·입시관리·생활관 신청·도서관 개인 기능의 로그인 이후 화면과 모든 학과/게시물은 조사하지 못했다. 해당 기능의 **존재**와 **세부 규칙**을 분리해 [연결 시스템 감사](03_CONNECTED_SYSTEMS_AUDIT.md)와 [CSV](04_FULL_FEATURE_CATALOG.csv)에 남겼다. 개인정보를 수집하거나 비공개 API에 접근하지 않았다.

## 산출물 안내

[01 문서 감사](01_CURRENT_DOCUMENT_AUDIT.md) · [02 공식 사이트](02_OFFICIAL_SITE_INVENTORY.md) · [03 연결 시스템](03_CONNECTED_SYSTEMS_AUDIT.md) · [04 기능 CSV](04_FULL_FEATURE_CATALOG.csv) · [05 FRD 보완](05_FUNCTIONAL_REQUIREMENTS_GAPS.md) · [06 NFR 보완](06_NON_FUNCTIONAL_REQUIREMENTS_GAPS.md) · [07 데이터 출처/시연](07_DATA_PROVENANCE_AND_SEEDS.md) · [08 통합 설계](08_INTEGRATION_ARCHITECTURE.md) · [09 미확인/결정](09_UNVERIFIED_AND_OPEN_QUESTIONS.md) · [10 개정 계획](10_DOCUMENT_REVISION_PLAN.md).
