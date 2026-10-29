# 미확인 사항과 결정 요청

확인일 2026-10-29. `UNKNOWN`은 실패가 아니라 공개 근거 부족이다. 로그인/개인정보 영역을 추측하지 않았다. 아래는 기존 [OPEN-001~009](../11_DECISION_LOG.md)을 **그대로 유지**하고 v1.0 설계에 필요한 결정을 추가한 목록이다. 이번 작업에서 어느 항목도 확정으로 승격하지 않았다.

## 기존 미결정 보존

`OPEN-001` README 3 CRUD, `OPEN-002` 스택/지역/미디어 비용, `OPEN-003` 시연 역할 생성 책임, `OPEN-004` 공지 중요도·재알림·확인통계, `OPEN-005` 익명 학과게시판의 교수/조교 참여, `OPEN-006` 녹화·녹음, `OPEN-007` 원격/대리 출석·학사 규정, `OPEN-008` 명칭/CI 사용권, `OPEN-009` 채팅·신고·탈퇴 보존/관리자 조회는 모두 미결정. 기존 안전 기본값은 [결정 대장](../11_DECISION_LOG.md)을 따르고 새로운 학교 조사로 자동 변경하지 않는다.

## v1.0 추가 결정 후보 (새 ID는 아직 결정 기록 아님)

| ID/급 | 결정할 내용 | 현재 근거/이유 | 결정 전 안전 처리 |
|---|---|---|---|
| `OPEN-R01` HIGH | 실제 운영 신원 원장·학교 승인 및 학생/지원자/졸업생 전환 책임 | [학생정보시스템](https://std.dit.ac.kr/)과 [입학 조회](https://apply.dit.ac.kr/index3.action)가 별도 | 가상 계정만; 재학생 인증 표시 금지 |
| `OPEN-R02` HIGH | 학생정보·LMS·캠퍼스락 중 학적/분반/출결의 최종 원장과 대사 규칙 | [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo), [LMS 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice), [캠퍼스락 공지](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11) | 내부 가상 원장 분리; 공식 출석 주장 금지 |
| `OPEN-R03` HIGH | 수강 정원·대기·정정 기간·학점·졸업 요건의 학년도별 규정 승인 | [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo), [졸업 안내](https://www.dit.ac.kr/kr/index.php?pCode=graduationinfo) | 공개 안내를 버전 있는 참고 데이터로만 |
| `OPEN-R04` HIGH | 입학 지원/서류/합격/등록·환불의 실제 처리 권한·개인정보·결제 계약 | [입학 메뉴](https://www.dit.ac.kr/ipsi/) | 시연 지원서·가상 결과만 |
| `OPEN-R05` HIGH | 고충·인권 상담 비밀 범위, 접근 감사, 보존/삭제, 긴급 대응 | [고충 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=gendercounsel) | 일반 게시판/검색/AI와 격리; 내용 시드 금지 |
| `OPEN-R06` HIGH | 증명서 발급 효력·진본 확인·수수료·결제/환불 및 제3자 계약 | [학교 안내](https://www.dit.ac.kr/kr/index.php?pCode=certificate) | 공식 증명서 생성/결제 금지 |
| `OPEN-R07` MED | 도서관 대출/연장/예약 자격·연체·예약 취소·그룹실 운영 규칙 | [도서관 메뉴](https://library.dit.ac.kr/Cheetah/DITL/Index/) | 메뉴 존재만 반영; 시연 거래는 가상 |
| `OPEN-R08` MED | 생활관 지원 대상·우선순위·배정·납부/취소 규칙 | [생활관 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities) | 신청/확인은 가상 상태만 |
| `OPEN-R09` MED | 외부 장학/근로/교내 사업별 접수 유형·선발 상태·담당 조직 | [장학 게시판](https://www.dit.ac.kr/kr/index.php?pCode=scholarship) | 공고별 `submission_mode`; 사용자 확정 외부 직접 제출 유지 |
| `OPEN-R10` MED | 학과의 현재 유효 코드·명칭·합과/폐과 이력 | [학교 첫 화면](https://www.dit.ac.kr/kr/)과 [대학 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=compusvr)의 표시 차이 | 출처별 표시 보존; 동일 조직으로 임의 병합 금지 |
| `OPEN-R11` MED | 학과/학교 공지 작성·승인·정정·철회 권한과 공개/비공개 경계 | [대학 공지](https://www.dit.ac.kr/kr/index.php?pCode=notice), [학과 공지 표본](https://www.dit.ac.kr/cs/) | 기존 RBAC 기본값 유지; 실제 학교 운영권 주장 금지 |
| `OPEN-R12` MED | 취업·기업 회원/이력서 공유 동의 및 상담 데이터 처리 | [취업센터](https://job.dit.ac.kr/page/main/) | 가상 이력서 또는 메타만; 기업 실계정 없음 |
| `OPEN-R13` MED | 공식 공개 자료의 재배포·첨부 보관·자동 갱신 허용과 책임자 | [학교 공지](https://www.dit.ac.kr/kr/index.php?pCode=notice) | 원본 URL·확인일 중심, 파일 복제 보류 |
| `OPEN-R14` MED | 서비스별 보존기간, RPO/RTO, 백업 위치/접근, 운영 SLA | [기존 NFR](../03_NFR.md)에는 운영 수치 없음 | 목표 `TBD`, 실운영 완료 주장 금지 |
| `OPEN-R15` LOW | YBM/Microsoft 365/AI-ONE/외부 AI 취업 도구를 장기 제품에 자체 구현할 범위 | [대학 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=notice), [AI-ONE 로그인](https://www.dit.ac.kr/kr/?pCode=aione) | 링크/메뉴 발견으로 전체 기능 복제 약속하지 않음 |
| `OPEN-R16` MED | 디지털 배지 발급자·이수 증거·진본/철회/지갑 연계와 시연 표시 | [학교 배지 공지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice) | 가상 배지만; 공식 증빙 주장 금지 |

## 접근 불가·부분 조사 범위

- [학생정보시스템](https://std.dit.ac.kr/) 공개 응답에는 화면 내용이 없었다. 학적·성적 수정, 로그인 후 수강 UI는 [수강 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo)에서 설명되는 범위만 확인했다.
- [아레테](https://arete2.dit.ac.kr/) 공개 수집 내용은 `ASTRA` 표시뿐이다. LMS 기능은 [공식 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice)에 명시된 범위이고 세부 동작은 미확인.
- [도서관 MyLibrary](https://library.dit.ac.kr/Cheetah/DITL/Index/) 하위 거래 페이지는 일부 수집 실패/로그인 필요. 대출 연장/시설 예약 **메뉴 존재**와 실제 제한 조건을 구분했다.
- [입시관리](https://applymng.dit.ac.kr/apply/)는 연결만 확인되고 페이지 수집 실패. [생활관 신청](https://nds.dit.ac.kr/nnds/guest.jsp)은 공개 응답 내용이 없었다.
- 학과 사이트는 [컴퓨터소프트웨어과](https://www.dit.ac.kr/cs/)와 [부동산재테크정보과](https://remc.dit.ac.kr/remc/)를 대표 표본으로 상세 열람했다. 모든 학과의 모든 게시물을 조사하지 않았다.
- 게시판의 관리자 글쓰기·승인, 학생 자유게시판 익명 여부, 민원/상담 비밀글 열람 범위, 교직원 내부 화면은 로그인 없이 확인할 수 없다.

## 확인 필요성을 낮추는 다음 증거

학교 담당자 승인 하에 **개인정보를 제거한** 학생/교직원 화면 메뉴 목록, 현행 학사 규정 버전, 권한별 업무 흐름, 도서관/생활관 운영 규정, 데이터 재사용·연계 권한을 확인한다. 실제 계정 로그인/비공개 API 접근은 이번 조사 범위에 포함되지 않았다.
