# FRD 보완 계약 — v1.0 개정 초안

이 문서는 [기능 카탈로그 92건](04_FULL_FEATURE_CATALOG.csv)의 신규 ID 44건을 기존 `FR-ACA-002`, `FR-CAMP-001` 등에 대응시킨다. **학교 현행 사실**은 URL이 달린 항목만 해당한다. 아래 상태기계·신규 동작은 모두 **설계 가정**이며 운영 승인 전 확정 규정이 아니다. 기존 [FRD](../02_FRD.md)와 [결정](../11_DECISION_LOG.md)의 확정 방향은 유지한다.

## 공통 기능 계약

모든 신청형 기능은 `actor_id`, 업무 대상 ID, 소유 조직/학기, 생성·수정 시각, 상태, 처리자, 근거 출처를 기록한다. 학생/지원자는 본인 건만 조회·수정하고, 담당자는 승인된 업무 범위 내에서만 조회·처리한다. 조회는 목록→상세, 작성은 입력→검증→접수번호/상태→재조회로 끝난다. 권한·누락·기한·중복·동시 처리 오류를 각각 구별하고, 공식 처리로 확정되지 않은 결과는 `신청/시연`으로 표시한다. 완료 테스트는 정상 제출/재조회, 타인 ID 접근 거부, 중복 제출, 마감 경계, 담당자 변경 이력을 포함한다. 각 기능의 세부 입력·출력·CRUD·상태·증거는 [CSV](04_FULL_FEATURE_CATALOG.csv) 행을 기준으로 한다.

## 공개 사이트·학과 (신규 6건)

- `FR-WEB-001~004`: 대학 소개/조직/상징, 캠퍼스 지도·VR·교통·주차, 정보공개·공시, 홍보 콘텐츠를 별도 콘텐츠 유형으로 다룬다. 작성/수정자는 승인된 해당 부서, 읽기는 공개. 게시 전 검토·버전·게시일·첨부·외부 원본 링크가 필요하다. 삭제는 공개 자료 보존 정책에 따라 보관 상태로 처리한다. 링크 오류·기간 경과 시 원본 갱신 상태를 표시한다. [대학 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=compusvr), [정보공개](https://www.dit.ac.kr/kr/index.php?pCode=information0101).
- `FR-DEPT-007~008`: 학과 소개/교수/교육과정과 학과 공지/뉴스/활동을 학과별 소유 콘텐츠로 추가한다. 공식 학과 공지는 기존 `FR-NOT-001` 원본을 재사용하고, 뉴스·활동은 공지로 가장하지 않는다. 학과별 메뉴/게시판 차이가 있으므로 타입과 노출 설정을 둔다. [컴퓨터소프트웨어과](https://www.dit.ac.kr/cs/), [부동산재테크정보과](https://remc.dit.ac.kr/remc/).

## 입학 (신규 6건)

입학 지원자는 학생 계정과 다른 신원·전형 권한이다. 원서 제출/합격/납부/환불은 공개 메뉴만 확인되었으므로 **실제 운영 규칙은 미확인**이다. [입학 홈](https://www.dit.ac.kr/ipsi/), [원서접수 로그인](https://apply.dit.ac.kr/index3.action), [상담 게시판](https://www.dit.ac.kr/ipsi/index.php?pCode=qna).

| ID | 신규 동작·입출력 | 제안 상태/검증 포인트 |
|---|---|---|
| `FR-ADMIS-001` | 전형/모집학과/정원/일정/요강 파일을 연도별 원본으로 등록·검색. | 초안→게시→마감. 이전 학년도 자료와 당해 모집을 혼동하지 않음. |
| `FR-ADMIS-002` | 지원자 자기 지원서 임시저장·제출, 접수번호/제출시각 반환. | 작성중→제출→접수. 필수 서류/중복 지원/기간 규칙은 모집요강별 확정 전 보류. |
| `FR-ADMIS-003` | 본인 서류 도착·면접 대상/시간 조회. | 대기→확인/보완→완료. 민감 결과는 공개 검색 인덱스 제외. |
| `FR-ADMIS-004` | 합격 결과·고지서·납부 상태를 독립 원장으로 표시. | 심사→발표→등록. 발표 전 노출·타 지원자 조회 차단; 실제 금융 확인 주체 미정. |
| `FR-ADMIS-005` | 등록포기/환불 신청과 처리번호·결과 제공. | 신청→검토→승인/반려→완료. 결제·환불 실행은 권한/계약 없으면 시연 불가. |
| `FR-ADMIS-006` | FAQ, 상담 신청, 비밀 상담 게시판, 내신 산출 입력을 분리. | 질문→답변완료. 비밀글 기본 비공개; 계산 근거·전형연도 표기. |

## 학사·학적·증명 (신규 9건, 기존 `FR-ACA-001~002` 분해)

- `FR-ACA-003`: 개설강좌·강의계획서 조회. 입력은 학기/학과/반, 출력은 분반·시간·정원·계획서. 교무 담당만 게시, 학생 조회. 개설 취소/변경 이력을 남긴다. [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo).
- `FR-ACA-004`: 신청/정정/취소를 학기별 개설 분반에 연결. 정원·중복·시간 충돌·이수학점·수강 자격을 서버 트랜잭션에서 검사한다. **13~21학점 등 공개 페이지 숫자는 해당 시점 안내로 저장하며 전학기 고정 규칙으로 하드코딩하지 않는다.** 신청확인서·시간표 재조회가 완료 조건. [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo).
- `FR-ACA-005`: 학생 본인 성적·이수·졸업 요건을 분리 조회; 성적 입력/확정/정정 권한은 별도. 졸업 요건은 입학연도·과정별 버전으로 계산하고, 미확인 규칙이면 `확인 필요`를 반환. [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo), [졸업 안내](https://www.dit.ac.kr/kr/index.php?pCode=graduationinfo).
- `FR-ACA-006~008`: 휴·복학, 재입학, 전과는 서로 다른 신청서·면담/서명·승인 경로다. 상태 `신청→서류/상담 확인→승인/반려→학적 반영`; 승인 전 학과·학년 채널/분반 권한을 바꾸지 않는다. 반영 후에는 `FR-AUTH-002` 소속과 `FR-DEPT-001~005` 권한을 재계산하고 구독을 끊는다. [휴학](https://www.dit.ac.kr/kr/index.php?pCode=leavabsence), [재입학](https://www.dit.ac.kr/kr/index.php?pCode=reenteruniv), [전과](https://www.dit.ac.kr/kr/index.php?pCode=changemajor).
- `FR-ACA-009`: 성적포기 안내는 시기·성적 범위·교수 면담·신청서 교무부 제출·학생정보시스템 결과 조회를 설명한다. 온라인 신청 여부와 성적 **정정** 절차는 미확인이다. 신청과 확정 성적을 분리하고 원본 변경은 권한자 승인·감사 후에만. [성적포기 안내](https://www.dit.ac.kr/kr/index.php?pCode=scorerenounce).
- `FR-ACA-010`: 증명 종류/언어/매수 선택→자격 확인→신청·결제→발급/실패/취소를 분리한다. 공식 인터넷 발급은 제3자 운영이므로 DIT Campus 시연에서 진본 증명서 생성 금지. 영문 이름 등록·변경은 별도 본인확인. [증명 안내](https://www.dit.ac.kr/kr/index.php?pCode=certificate).
- `FR-ACA-011`: 등록금 고지/납부 확인 원장과 수강 자격 연계. 공개 수강 안내에 납부 선행이 명시되나 결제 API/분납·환불 규칙은 미확인. [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo).

## LMS와 출결 (신규 5건)

`FR-LMS-001~003`은 온라인 콘텐츠·학습 출석·시험 응시다. 교수의 분반 게시/수강생 열람, 기간·제출·피드백·재응시 권한을 분리하고 원본 콘텐츠/시도/평가 이벤트를 보존한다. 공개 공지는 이 기능들의 **존재**만 확인하므로 진도율·시험 시도횟수·채점 방식은 설계 가정으로 둔다. `FR-LMS-002`와 `FR-ATT-001~004`의 공식 출결 병합 규칙은 미정. [아레테 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice).

`FR-ATT-003`: 학교는 캠퍼스락 앱의 블루투스/인증번호 출석과 교수 앱/웹 관리를 공개했다. 신규 서비스의 출결 세션→체크→교수 확인 흐름에 `check_method`와 오류/정정 이유를 저장하되, 실제 현장 재실 증명으로 과장하지 않는다. `FR-ATT-004`: 모바일학생증은 도입 사실만 확인, 발급·폐기·제시 규칙은 보류. [캠퍼스락 공지](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11).

## 도서관·취업·생활관·지원 (신규 14건)

| ID | 제안 흐름과 핵심 데이터 | 학교 확인 범위 |
|---|---|---|
| `FR-LIB-001` | 검색어/자료유형→서지·소장·전자 접근정보. 사서만 원장 수정. | [검색·전자정보 메뉴](https://library.dit.ac.kr/Cheetah/DITL/Index/) |
| `FR-LIB-002` | 본인 대출/연장/예약→기한·상태, 사서 반납·예외 처리. 소장본 단위 중복 대출 금지. | [MyLibrary 메뉴](https://library.dit.ac.kr/Cheetah/DITL/Index/); 거래 규칙 미확인 |
| `FR-LIB-003` | 희망도서 신청→사서 검토→구입/반려·알림. | [희망도서 메뉴](https://library.dit.ac.kr/Cheetah/DITL/Index/); 심사 미확인 |
| `FR-LIB-004` | 공간/시간 선택→예약→취소/이용. 동일 슬롯 배타 제약. | [스터디룸/시네마존 메뉴](https://library.dit.ac.kr/Cheetah/DITL/Index/); 제한 미확인 |
| `FR-JOB-001` | 채용/아르바이트 공고 등록·필터·마감·저장, `FR-OPP-001` 공통 기회 원본 연결. | [취업센터](https://job.dit.ac.kr/page/main/) |
| `FR-JOB-002` | 개인 희망진로/이력서 작성·공유 동의·상담자 접근. | [별도 등록 링크](https://job.dit.ac.kr/page/main/); 내용 미확인 |
| `FR-JOB-003` | 프로그램 신청·참여와 상담 예약/기록을 별도 상태로. | [프로그램·상담 메뉴](https://job.dit.ac.kr/page/main/) |
| `FR-JOB-004` | 기업 계정→채용의뢰→담당자 검토→공개/반려. | [기업 회원·의뢰 메뉴](https://job.dit.ac.kr/page/main/) |
| `FR-DORM-001` | 시설/수칙/공지 게시·개정, 생활관 운영자만 편집. | [생활관 페이지](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities) |
| `FR-DORM-002` | 재학생/신입생 구분 신청→확인→배정/반려/취소. | [신청/확인 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities); 실제 절차 미확인 |
| `FR-HELP-001` | 민원 분류→접수→담당자 지정→답변/종결; 본인·담당자 범위. | [사이버종합민원](https://www.dit.ac.kr/kr/index.php?pCode=cybersvccenter) |
| `FR-HELP-002` | 인권·성희롱 고충은 별도 보안 영역, 최소 접근·감사·비공개 상태. 공개 안내의 전화·방문·신고서 이메일 접수를 존중하고 온라인 접수는 추가 승인 필요. | [고충 안내](https://www.dit.ac.kr/kr/index.php?pCode=gendercounsel); 내부 보존·처리 규칙 미확인 |
| `FR-HELP-003` | 장애학생 지원 항목 안내와 요청·처리 상태, 접근 가능한 UX. | [장애학생지원](https://www.dit.ac.kr/kr/index.php?pCode=stdsupportcenter) |
| `FR-HELP-004` | 봉사 공고/참여·활동 기록. 실제 신청 경로 미확인. | [봉사단 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=notice) |

## 운영 (신규 2건) 및 기존 ID 보완

`FR-ADM-003`은 입학 담당자·사서·상담자·생활관 담당자·기업 계정을 `role_assignments`의 업무 범위로 추가하는 설계 후보. `FR-ADM-004`는 콘텐츠/시연 데이터의 출처·검증시각·공식성 배지를 관리한다. 이 둘은 현재 학교에 동일 기능이 있다는 주장이 아니다.

`FR-CRED-001`은 [디지털 배지 공지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice)의 이수→주관부서 발급→등록 이메일 수신→지갑 생성·수령·공유 흐름을 학사/비교과 성과와 연결한다. 발급 기준·진본 검증·철회는 미확인이다. `FR-CAMP-003`은 [복지편의시설 페이지](https://www.dit.ac.kr/kr/index.php?pCode=welfareinfo)의 층별 시설·운영시간·교내식당·시설물 사용신청서를 캠퍼스 정보와 신청 상태로 분리한다. 시설물 신청서 다운로드가 곧 온라인 승인 서비스라는 뜻은 아니다.

기존 `FR-NOT-001~005`, `FR-DEPT-001~006`, `FR-COM-001~007`, `FR-OPP-001~006`, `FR-COURSE-001~007`, `FR-HOME-001~003`, `FR-AI-001~003`는 현재 ID와 결정 상태를 유지한다. 공개 게시판은 `FR-COM-001`의 **익명성**을 증명하지 않는다. `FR-COURSE-005`의 수업 질문은 LMS Q&A가 존재하지만 실시간 수업 채팅은 신규 기능이다. 공고의 제출 방식은 `external_document_submission`, `external_web`, `internal_application`, `information_only` 등으로 공고별 구분하는 안을 제시하며 사용자 확정 외부 장학 흐름은 그대로 보존한다.

## 명세 추적·결정 표

| ID | 근거 | 기존 명세 | 빈 영역 | 보완안 | 결정 필요 | 우선 |
|---|---|---|---|---|---|---|
| `FR-ADMIS-001~006` | [입학 홈](https://www.dit.ac.kr/ipsi/) | PRD/FRD에 별도 ID 없음 | 지원자/전형/서류/합격·납부 | 6개 흐름과 지원자 권한 | OPEN-R01/R04 | HIGH |
| `FR-ACA-003~011` | [수강](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo), [증명](https://www.dit.ac.kr/kr/index.php?pCode=certificate) | `FR-ACA-002` 한 줄 | 학사·학적·증명·등록 원장 | 업무별 신청/승인/조회 분리 | OPEN-R02/R03/R06 | HIGH |
| `FR-LMS-001~003` | [아레테 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice) | `FR-COURSE-003~004` 일부 | 온라인 강의·출석·시험 | 학습 이벤트/시험 시도 별도 | OPEN-R02 | HIGH |
| `FR-ATT-003~004` | [캠퍼스락 공지](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11) | `FR-ATT-001~002` | 실제 방식·모바일학생증 | 방법·판정/시연 구분 | OPEN-007/R02 | HIGH |
| `FR-LIB-001~004` | [도서관](https://library.dit.ac.kr/Cheetah/DITL/Index/) | `FR-CAMP-001` | 서지/대출/예약 분리 | 4개 자원·상태·정원 | OPEN-R07 | MED |
| `FR-JOB-001~004` | [취업센터](https://job.dit.ac.kr/page/main/) | `FR-OPP-001` 일부 | 기업·진로·이력서/상담 | 공개 공고/개인 기록 분리 | OPEN-R12 | MED |
| `FR-DORM-001~002` | [생활관](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities) | `FR-CAMP-001` | 신청·배정 | 생활관 담당 범위·상태 | OPEN-R08 | MED |
| `FR-HELP-001~004` | [민원](https://www.dit.ac.kr/kr/index.php?pCode=cybersvccenter) | `15_PLATFORM_BASELINE`만 | 민원·고충/장애·봉사 | 민감도별 별도 흐름 | OPEN-R05 | HIGH |
| `FR-WEB-001~004`, `FR-DEPT-007~008` | [대학](https://www.dit.ac.kr/kr/index.php?pCode=compusvr), [학과](https://www.dit.ac.kr/cs/) | PRD의 공개 정보 범주 | 콘텐츠 소유·버전 | 출처/공식성·학과별 메뉴 | OPEN-R10/R11/R13 | MED |
| `FR-CRED-001`, `FR-CAMP-003` | [배지 공지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice), [편의시설](https://www.dit.ac.kr/kr/index.php?pCode=welfareinfo) | `FR-CAMP-001` 및 학사 기준 일부 | 공식 배지/시설 신청서 흐름 | 발급 권한·시설 정보/신청 분리 | OPEN-R13/R16 | MED |
| `FR-ADM-003~004` | [기존 결정](../11_DECISION_LOG.md)에서 도출 | `FR-ADM-001~002` | 새 업무 역할·출처 관리 | 범위 RBAC/시연 배지 | OPEN-R01/R13 | HIGH |

현행 `mvp/`는 [README](../../mvp/README.md)와 [저장소](../../mvp/src/shared/data/store.ts)에 따라 브라우저 기반 시연이다. 위 보완안이나 기존 FRD의 수용 조건을 이미 서버에서 충족했다고 판단하지 않는다.
