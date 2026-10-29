# SKILL: 데이터베이스 (MariaDB)

> 최신 안전 경계: DB_AUTO_INIT=false, 런타임 DDL/자동 시드 금지. 기존 스키마를 읽기 전용으로 검사하고 부재 시 시작을 거부한다. 운영 migration/시드는 공통 플랫폼 마이그레이션 소유자와 별도 승인 계정의 작업이다. 원격 create_all/reset/중복 학생·세션 원장을 만들지 않는다. 실제 MariaDB 접속/GRANT는 미검증이며 [README](../README.md)의 TASK-F-DB-SAFETY를 따른다.

> 대상 파일: `app/models.py`, `app/db.py`, `app/student_repo.py`, `app/auth.py`, `docker-compose.yml`, `scripts/seed_db.py`

## 1. 무엇이 어디에 있나

| 데이터 | 저장소 | 이유 |
|---|---|---|
| 학생·강의·수강 이력·졸업 기준·로그인 세션 | **MariaDB** | 학생별 조회, 런타임 쓰기(세션), 재시작해도 유지 |
| 교내 시설·건물 (`data/*.json`) | JSON → 메모리 검색 인덱스 | 팀이 직접 편집·검증, 검색은 메모리가 빠름 |

- 위 학생/세션 테이블은 보존된 독립 시연 모델이다. 통합 앱의 공통 사용자·학적 원장을 대체하지 않는다. 학교 학사 시스템과 동기화하지 않는다.
- `data/mock/*.json`은 폐기 가능한 SQLite 메모리 테스트 픽스처다. 원격 운영 DB에 시드하지 않는다.

## 2. 실행

```bash
uv sync --locked --all-extras
uv run --locked --all-extras pytest  # 명시적으로 준비한 SQLite 메모리 픽스처
# 독립 시연 실행은 승인된 기존 스키마와 제한된 DML 계정 구성 후에만 가능하다.
# 팀 제공 MariaDB 외 중복 컨테이너나 DB를 생성하지 않는다.
```

- `.env.example`의 DATABASE_URL은 사용자/암호/호스트 자리표시자와 포트 3307을 제공한다. 실제 비밀값과 내부 주소를 문서/로그에 넣지 않는다.
- 앱 DML과 마이그레이션 계정은 분리한다. 실제 계정 인증·GRANT·스키마 버전 검증은 별도 수행 전까지 NOT_RUN이다.

## 3. 테이블

```
students                    학적 (학번 PK, 이름, 학과, 학년, password_hash, kakao_id UNIQUE)
courses ─< course_sessions  강의, 요일·시간·강의실
enrollments                 수강 이력 (학번, 강의, 학기, 이수구분, 성적) UNIQUE(학번, 강의, 학기)
exams                       시험 일정 (강의, 중간/기말, 날짜, 시간, 강의실) UNIQUE(강의, 종류)
graduation_rules ─< graduation_rule_categories   학과별 졸업 총 학점, 구분별 최소 학점
auth_sessions               로그인 세션 (token_hash PK, 학번, 만료 시각)
question_logs               질문 로그 (질문, 의도, 분류 방법, 성공 여부, 응답 시간) — 학번 없음
```

- **취득 학점은 저장하지 않고** `enrollments`에서 계산합니다 (`student_repo.load_student`).
  - 성적이 있고 `F`가 아니면 취득, 성적이 `NULL`이면 수강 중입니다.
  - 이번 학기는 `.env`의 `CURRENT_SEMESTER`(기본 `2026-2`)입니다.
- 로그인 토큰은 **SHA-256 해시만 저장**합니다. DB가 유출돼도 토큰 원문은 알 수 없습니다.
- 문자셋은 `utf8mb4`(한글·이모지)입니다.

## 4. 코드 규칙

- 엔드포인트는 `DB` 의존성(`Annotated[AsyncSession, Depends(get_db)]`)으로 요청마다 세션을 받습니다.
- 처리기(`personal.py`)는 DB를 모릅니다. `load_student()`가 ORM 행을 `Student`·`StudentData`로 바꿔 넘깁니다.
- 교내 질문에는 학생 데이터를 읽지 않습니다 (`/ask`에서 의도가 campus면 조회 생략).
- PBKDF2 비밀번호 검증은 CPU 작업이라 `asyncio.to_thread`로 돌립니다.
- 런타임은 기존 필수 테이블만 확인한다. 이 검사는 컬럼/제약/버전/실제 최소 GRANT 검증을 대체하지 않는다.
- `init_db`와 reset은 SQLite 메모리 테스트에서만 허용한다. 파일 DB와 MariaDB에서는 연결 전에 거부한다. `seed_db.py --reset`은 지원하지 않는다.
- 운영 스키마 변경은 공통 소유자가 기존 데이터/백업/신원 매핑을 확인한 뒤 별도 리뷰·승인한다. 독립 시연 테이블 전체를 원격으로 생성하는 migration 명령은 제공하지 않는다.

## 5. 테스트

- 테스트와 `scripts/eval.py`는 Docker 없이 **SQLite 메모리 DB**(`sqlite+aiosqlite:///:memory:`)에 같은 테이블을 만들고 픽스처를 시드합니다.
- `tests/conftest.py`의 `db`(세션), `students`(학번 → DB에서 읽은 학생) 픽스처를 쓰세요.
- MariaDB 전용 동작(문자셋, 연결 끊김, 계정 권한)은 실제 접속이 준비된 뒤 별도로 검증한다. SQLite 테스트 성공으로 운영 DB를 검증했다고 표시하지 않는다.
