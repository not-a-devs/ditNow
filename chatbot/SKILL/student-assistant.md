# SKILL: 학생 개인 질문 & 로그인

> 대상 파일: `app/intents.py`, `app/personal.py`, `app/auth.py`, `app/student_repo.py`, `data/mock/*.json`
> 학생 데이터는 MariaDB에 있습니다. 테이블·시드는 `SKILL/database.md`.

> 아래 로그인과 students 모델은 보존된 독립 시연 계약이다. 통합 앱은 services/api의 공통 신원·학적 원장과 세션을 사용하며 이 로그인·테이블을 별도로 provisioning하지 않는다. 실제 DB 연결·기존 스키마 검증은 미완료다. 런타임 자동 초기화·원격 reset/시드는 금지한다.

## 1. 흐름

```
질문 + (선택) Authorization: Bearer <token> + (선택) history
  → history가 있으면 condense()로 완전한 질문으로 재작성   # app/conversation.py
  → route(question)                     # app/intents.py
     ├─ RULES(키워드 규칙, 단어 끝 조사 제거 후 비교)에 맞으면 그 의도   (classified_by=keyword)
     ├─ 규칙에 없고, 1인칭('내','나','제'…)이거나 교내 검색 결과가 없으면
     │    LLM이 {"intent", "day"} JSON으로 분류      (classified_by=llm)
     └─ 그 밖에는 campus
  + 조건값: 요일(day) — 키워드는 정규식, LLM은 JSON의 day
  → campus면 기존 검색 RAG
    개인 의도면 로그인 확인(없으면 need_login=true, LLM 호출 없음)
    → HANDLERS[intent](학생, 데이터, 교내, PersonalQuery(질문, 지금, day)) → <context> 블록
  → 같은 프롬프트로 LLM이 문장만 작성 → [근거: id] 파싱, 본문의 내부 id 제거
```

- **계산은 코드, 문장은 LLM.** 학점·평점·D-day·다음 수업 찾기는 `personal.py`에서 끝내고 결과만 넘깁니다.
- 처리기는 `[id]`로 시작하는 블록을 돌려줍니다. 강의는 `course_id`, 그 밖에는 `my_timetable`·`my_credits`·`my_grades`·`my_exams`·`my_courses`.
- **LLM 분류 결과는 허용 목록(의도·요일) 안에서만 씁니다.** 학번은 언제나 토큰에서만 가져옵니다.
- LLM 분류가 실패하거나 JSON이 아니면 campus로 갑니다.

## 2. 지원 의도

| intent | 예시 질문 | 처리기 |
|---|---|---|
| `next_class` | 내 다음 수업 어디서 들어? / 자료구조 강의실 어디야 | 지금 이후 첫 수업. 과목을 말하면 그 과목만 |
| `day_classes` | 오늘 수업 뭐야 / 목요일 수업 / 내일 수업 있어? / 이번 주 시간표 | 그날 수업(기본 오늘). 과목만 말하면 그 과목의 일주일 |
| `my_courses` | 이번 학기 듣는 과목 뭐야 / 웹프로그래밍 교수님 누구야 | 수강 과목·이수 구분·학점·교수·강의실 |
| `grades` | 내 평점 몇이야 / 지난 학기 성적 / 알고리즘 성적 | 전체·학기별 평점(4.5 만점, F 포함), 최근 학기 또는 질문한 과목 성적 |
| `exams` | 기말고사 언제야 / 데이터베이스 시험 어디서 봐 | 남은 시험과 D-day. '중간'·'기말'을 말하면 지난 시험 포함 |
| `remaining_credits` | 졸업학점 몇 남았어 / 내 학점 몇학점이야 | 졸업 기준 − 취득 학점, 구분별·수강 중 반영 |

- 시각은 KST(UTC+9) 기준입니다. 한국은 서머타임이 없어 고정 오프셋을 씁니다.
- 과목명은 처리기가 그 학생의 과목 목록과 맞춰 봅니다(`match_courses`). 과목명 일부만 써도 됩니다("진로 수업").

## 3. 새 개인 질문 추가하기

1. `intents.py`의 `RULES`에 `(표현, 의도)`를 추가합니다. **위에서부터 처음 맞는 규칙**을 씁니다.
   - 표현은 띄어쓰기를 뺀 형태입니다. `"수업+몇시"`처럼 `+`로 이으면 두 단어가 모두 있을 때 일치합니다.
   - 개인 키워드와 겹치는 교내 질문은 맨 위에 `(표현, CAMPUS)`로 고정합니다(예: `증명서` → "성적증명서").
   - 단독 단어(`졸업`, `중간`)는 교내 질문과 겹치기 쉬우니 피하세요.
2. `prompt.py`의 `CLASSIFY_PROMPT` 의도 목록에 한 줄 설명을 추가합니다(LLM 분류용).
3. `personal.py`에 처리기를 쓰고 `HANDLERS`에 등록합니다. `test_every_intent_has_handler`가 빠진 것을 잡습니다.
4. 새 데이터는 공통 플랫폼 원장/신원 매핑과 마이그레이션 소유자에게 먼저 요청한다. 테스트 전용 픽스처는 SQLite 메모리에서만 명시적으로 준비하며 원격 `seed_db.py --reset`은 사용하지 않는다.
5. `tests/test_personal.py`에 분류·계산 테스트를, `tests/eval_personal.json`에 평가 질문을 추가합니다.
   키워드로 못 잡는 표현은 `"needs_llm": true`로 표시합니다.
6. 운영 중에는 `GET /admin/questions`로 답을 못 찾은 질문을 보고 규칙·평가 세트에 반영합니다.

## 4. 로그인 (현재: 더미)

- `POST /auth/login` `{ "student_id": 학번, "password": 초기 비밀번호(주민등록번호 뒷자리) }` → `{ token, student_id, name }`
- 이후 요청에 `Authorization: Bearer <token>`. 로그아웃은 `POST /auth/logout`.
- `/docs`에서 테스트할 때: `/auth/login` 실행 → 응답의 `token` 복사 → 오른쪽 위 **Authorize** 버튼에 토큰만 붙여넣기(`Bearer ` 없이).
- 토큰은 반드시 `HTTPBearer` 보안 스킴(`main.py`의 `Credentials`)으로 받습니다. `Header()`로 받으면 Swagger가 `Authorization` 헤더를 보내지 않습니다.
- 토큰은 DB `auth_sessions`에 해시로 12시간 보관합니다. 서버를 재시작해도 로그인이 유지됩니다.

### 시연용 목업 계정 (`data/mock/students.json` → DB)

| 학번 | 비밀번호 | 이름 | 상황 |
|---|---|---|---|
| 20231001 | 3000001 | 김동의 | 컴소과 2학년, 4과목 수강 중, 취득 42학점(F 1과목 제외) |
| 20241002 | 4000002 | 이과학 | 간호학과 1학년, 3과목 수강 중 |
| 20221003 | 3000003 | 박졸업 | 컴소과, 졸업 학점 모두 충족·수강 없음 |

- 비밀번호는 실제 주민번호와 겹칠 수 없는 가짜 값이며, JSON·DB에는 **PBKDF2 해시만** 저장합니다.
- 새 계정 해시 만들기: `python -c "from app.auth import hash_password; print(hash_password('비밀번호'))"`

### 카카오 로그인 (예정)

- `students.kakao_id`(UNIQUE) 컬럼이 준비되어 있습니다. 카카오 OAuth로 받은 사용자 id로 학생을 찾고 `issue_token()`으로 같은 토큰을 발급하면 됩니다.
- 처음 연동할 때는 학번 로그인 상태에서 카카오 id를 연결하는 절차가 필요합니다.

## 5. 보안 규칙

- **학생 식별은 토큰으로만** 합니다. 질문에 적힌 학번은 절대 믿지 않습니다.
- **개인 질문 답변은 캐시하지 않습니다.** 질문 캐시는 학생과 무관한 교내 정보 답변만 담습니다.
- 개인 데이터와 비밀번호는 로그에 남기지 않습니다.
- 개인 데이터는 LLM 공급자에게 전송됩니다. 실제 학적 데이터를 쓸 때는 학교 자체 LLM(`openai_compatible`)이나 개인정보 처리 동의 여부를 먼저 검토하세요.
- 로그인 실패 응답은 학번 존재 여부를 드러내지 않습니다(메시지·응답 시간 동일).
