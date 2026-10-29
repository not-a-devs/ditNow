# 공식 연결 시스템 감사

확인일: 2026-10-29 KST. `VERIFIED`는 공개 메뉴·공지에서 **기능 존재**가 확인되었다는 뜻이다. 로그인 이후 업무 규칙은 별도 `PARTIAL/UNKNOWN`이다.

| 시스템/진입 | 공개 확인 동작 | 존재/규칙 | v1.0 경계 |
|---|---|---|---|
| [입학안내](https://www.dit.ac.kr/ipsi/) → [원서접수센터](https://apply.dit.ac.kr/index3.action) | 모집/상담/결과와 접수·면접·합격·납부 조회 메뉴. 원서접수센터는 수험번호·성명·생년월일 로그인 폼. | VERIFIED/PARTIAL | 지원자 원장·전형/서류/결제/결과를 별도 권한 도메인으로 설계. 조회 메뉴의 내부 동작 미확인. |
| [학생정보시스템](https://std.dit.ac.kr/) | 대학 메뉴에서 연결. [수강신청 안내](https://www.dit.ac.kr/kr/index.php?pCode=classreginfo)가 수강관리/개설강좌/시간표/성적조회 설명. 직접 공개 페이지는 내용이 표시되지 않음. | VERIFIED/PARTIAL | 학적·성적·수강 원장 필요. 기존 시스템 접속/실제 동기화 주장 금지. |
| [아레테/ASTRA](https://arete2.dit.ac.kr/) | 공개 진입은 `ASTRA` 표시. [학교 공지](https://www.dit.ac.kr/kr/index.php?idx=17577&mode=view&pCode=notice)는 온라인 강의, 출석 확인, 과제, 시험, 공지, Q&A와 모바일 앱 변경을 명시. | VERIFIED/PARTIAL | LMS 학습 출석과 대면 전자출결을 분리 모델링. 진도·평가 상세 규칙 미확인. |
| [캠퍼스락 출결](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11) / [교수 웹](https://bs.bnkcampus.com/) | 학교 공지는 2025-2학기 도입, 학생 블루투스/인증번호 출석, 교수 앱/웹 관리, 모바일학생증 초기 도입을 명시. | VERIFIED/PARTIAL | `FR-ATT`의 코드/QR 옵션과 현재 학교 사용 방식을 구분. 위치 인증·지각 판정 등은 미확인. |
| [도서관](https://library.dit.ac.kr/Cheetah/DITL/Index/) | 자료 통합검색, 신착/인기/주제, 전자책·저널, 대출현황/연장/예약, 희망도서, 그룹스터디룸/시네마존 예약, 도서관 안내·게시판 메뉴. | VERIFIED/PARTIAL | 서지·소장/대출·예약·회원 자격 분리. MyLibrary는 로그인 규칙 미확인. |
| [취업지원센터](https://job.dit.ac.kr/page/main/) | 채용/아르바이트, 기업 채용의뢰, 희망진로·이력서 등록(별도 `nds`), 취업 프로그램, 상담, 해외취업, AI 자기소개서/면접 외부 연결. | VERIFIED/PARTIAL | 개인 취업정보와 공개 공고 구분; 기업 계정 역할 추가. |
| [생활관](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities) → [신입생 신청/확인](https://nds.dit.ac.kr/nnds/guest.jsp) | 시설·수칙·공지·자료실·자유게시판, 재학생/신입생 신청·확인 메뉴. `nds` 공개 응답은 비어 있음. | VERIFIED/PARTIAL | 신청/배정/납부/퇴사는 별도 업무 상태. 실제 절차 미확인. |
| [증명서 안내](https://www.dit.ac.kr/kr/index.php?pCode=certificate) → [인터넷 발급](https://dit.webminwon.kr/) / [해외 우편](https://postdit.webminwon.kr/) | 학교가 제3자 운영을 명시하고 종류·수수료·학교내 발급·영문명 등록을 안내. | VERIFIED/PARTIAL | 발급 자격/진본 확인/결제·환불은 제3자 및 학교 승인 필요. 시연 문서에 공식 효력 금지. |
| [YBM 온라인 교양](https://www.ybmuniv.com/) | 대학 메뉴에서 연결. | VERIFIED/UNKNOWN | 이수·성적 전달 규칙 미확인. |
| [교수학습개발센터](https://ctl.dit.ac.kr/) | 대학 메뉴와 [JUMP-UP 공고](https://www.dit.ac.kr/kr/index.php?idx=17786&mode=view&pCode=notice)의 별도 참여 링크 확인. | VERIFIED/PARTIAL | 프로그램 공고→신청→선발 흐름을 기회 센터에서 구분. |
| [입시관리시스템](https://applymng.dit.ac.kr/apply/) | 대학 메뉴 연결만 확인; 공개 페이지 수집 실패. | PARTIAL/UNKNOWN | 담당자 권한/업무 상세 미확인. |
| [DIT AI-ONE](https://www.dit.ac.kr/kr/?pCode=aione) | 교직원·재학생 전용 로그인 폼과 대상 제한 안내. | VERIFIED/UNKNOWN | 기존 AI 서비스의 대화·데이터 범위 미확인. 신규 AI 기능이 학교에 없다고 단정 금지. |
| [디지털 배지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice) | 교과·비교과 이수 후 주관 부서 발급, 등록 이메일 수신, 배지 지갑 생성·수령·공유 절차가 공지됨. | VERIFIED/PARTIAL | 모바일학생증·증명서와 다른 역량 자격증명. 진본/철회/발급 기준은 별도. |
| [Microsoft 365](https://www.dit.ac.kr/kr/index.php?pCode=compusvr), [AI 취업 도구](https://job.dit.ac.kr/page/main/), [웹진](https://webzine.dit.ac.kr/) | 대학 메뉴의 외부 서비스 링크. | VERIFIED/UNKNOWN | 자체 구현 범위/계약/라이선스 결정 필요. |
| [사이버 민원](https://www.dit.ac.kr/kr/index.php?pCode=cybersvccenter), [인권·고충](https://www.dit.ac.kr/kr/index.php?pCode=gendercounsel) | 민원 분류·검색 및 별도 고충 메뉴. | VERIFIED/PARTIAL | 고충 내용의 권한·암호화·보존은 일반 게시판과 분리. |

### 특히 주의할 오인

1. 2026년 LMS 공지의 `ASTRA`는 아레테의 앱/플랫폼 명칭이다. 기존 문서의 ASTRA 언급을 서비스 종료/교체 확정으로 해석하지 않는다.
2. 캠퍼스락의 **전자출결**과 아레테의 **온라인 학습 출석 확인**은 각각 공식 자료에 존재한다. 한 출석 원장인지, 상호 대사·우선순위가 무엇인지는 미확인.
3. 제3자 발급·AI·취업 서비스는 링크 확인으로 해당 기능을 자체 복제하거나 학교 계정과 통합할 권리가 생기지 않는다.
4. 과거 학과 공지는 구 전자출결 앱 사용을 설명하지만 2025년 캠퍼스락 도입 공지가 더 최신이다. [구 학과 공지](https://www.dit.ac.kr/smartfood/?idx=1160&mode=view&pCode=MN0000023&pg=2), [신규 도입](https://www.dit.ac.kr/kr/?idx=16153&mode=view&pCode=notice&pg=11).
