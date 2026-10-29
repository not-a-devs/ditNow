# SKILL: 학생 개인 질문 & 로그인

> 대상 파일: `app/intents.py`, `app/personal.py`, `app/auth.py`, `data/mock/*.json`

## 1. 흐름

```
질문 + (선택) Authorization: Bearer <token>
  → classify(question)            # app/intents.py
     ├─ campus            → 기존 검색 RAG
     └─ next_class 등 개인 → 로그인 안 했으면 need_login=true (LLM 호출 없음)
                            → HANDLERS[intent]가 코드로 사실 계산 → <context> 블록
  → 같은 프롬프트로 LLM이 문장만 작성 → [근거: id] 파싱
```

- **계산은 코드, 문장은 LLM.** 학점 뺄셈·다음 수업 찾기는 `personal.py`에서 끝내고 결과 숫자만 넘깁니다.
- 처리기는 `[id]`로 시작하는 블록을 돌려줍니다. 강의는 `course_id`, 그 밖에는 `my_timetable`·`my_credits`.

## 2. 지원 의도

| intent | 예시 질문 | 처리기 |
|---|---|---|
| `next_class` | 내 다음 수업 어디서 들어? | 지금 이후 첫 수업 (일주일 뒤 같은 요일까지) |
| `today_classes` | 오늘 수업 뭐 있어? / 내 시간표 | 오늘 요일 수업 전체 |
| `remaining_credits` | 졸업학점 몇 학점 남았어? | 졸업 기준 − 취득 학점, 구분별·수강 중 반영 |

- 시각은 KST(UTC+9) 기준입니다. 한국은 서머타임이 없어 고정 오프셋을 씁니다.

## 3. 새 개인 질문 추가하기

1. `intents.py`의 `INTENT_KEYWORDS`에 의도와 표현(띄어쓰기 제거)을 추가합니다.
   - `"수업+몇시"`처럼 `+`로 이으면 **두 단어가 모두 들어 있을 때** 일치합니다("이따 수업 몇 시야?").
   - 정확한 표현이 `+` 조합보다 먼저 검사되고, 같은 종류끼리는 위에 있는 의도가 우선합니다
     ("오늘 수업 몇시에 끝나" → `오늘수업`이 `수업+몇시`를 이김).
   - 교내 질문과 겹치는 표현은 피하세요. `졸업`만 넣으면 "졸업증명서 어디서 뽑아"가 개인 질문이 됩니다.
2. `personal.py`에 처리기를 쓰고 `HANDLERS`에 등록합니다.
3. 필요하면 `data/mock/`과 `Student` 모델에 필드를 추가합니다.
4. `tests/test_personal.py`에 분류·계산 테스트를, `tests/eval_personal.json`에 평가 질문을 추가합니다.
   `test_eval_questions_stay_campus`가 기존 교내 질문의 오분류를 잡아 줍니다.

## 4. 로그인 (현재: 더미)

- `POST /auth/login` `{ "student_id": 학번, "password": 초기 비밀번호(주민등록번호 뒷자리) }` → `{ token, student_id, name }`
- 이후 요청에 `Authorization: Bearer <token>`. 로그아웃은 `POST /auth/logout`.
- `/docs`에서 테스트할 때: `/auth/login` 실행 → 응답의 `token` 복사 → 오른쪽 위 **Authorize** 버튼에 토큰만 붙여넣기(`Bearer ` 없이).
- 토큰은 반드시 `HTTPBearer` 보안 스킴(`main.py`의 `Credentials`)으로 받습니다. `Header()`로 받으면 Swagger가 `Authorization` 헤더를 보내지 않습니다.
- 토큰은 서버 메모리에 12시간 보관합니다. **서버를 재시작하면 모두 로그아웃됩니다**(단일 워커 전제).

### 시연용 목업 계정 (`data/mock/students.json`)

| 학번 | 비밀번호 | 이름 | 상황 |
|---|---|---|---|
| 20231001 | 3000001 | 김동의 | 컴소과 2학년, 4과목 수강 중 |
| 20241002 | 4000002 | 이과학 | 간호학과 1학년, 3과목 수강 중 |
| 20221003 | 3000003 | 박졸업 | 컴소과, 졸업 학점 모두 충족·수강 없음 |

- 비밀번호는 실제 주민번호와 겹칠 수 없는 가짜 값이며, JSON에는 **PBKDF2 해시만** 저장합니다.
- 새 계정 해시 만들기: `python -c "from app.auth import hash_password; print(hash_password('비밀번호'))"`

### 카카오 로그인 (예정)

- `Student.kakao_id`가 준비되어 있습니다. 카카오 OAuth로 받은 사용자 id로 학생을 찾고 `SessionStore.issue()`로 같은 토큰을 발급하면 됩니다.
- 처음 연동할 때는 학번 로그인 상태에서 카카오 id를 연결하는 절차가 필요합니다.

## 5. 보안 규칙

- **학생 식별은 토큰으로만** 합니다. 질문에 적힌 학번은 절대 믿지 않습니다.
- **개인 질문 답변은 캐시하지 않습니다.** 질문 캐시는 학생과 무관한 교내 정보 답변만 담습니다.
- 개인 데이터와 비밀번호는 로그에 남기지 않습니다.
- 개인 데이터는 LLM 공급자에게 전송됩니다. 실제 학적 데이터를 쓸 때는 학교 자체 LLM(`openai_compatible`)이나 개인정보 처리 동의 여부를 먼저 검토하세요.
- 로그인 실패 응답은 학번 존재 여부를 드러내지 않습니다(메시지·응답 시간 동일).
