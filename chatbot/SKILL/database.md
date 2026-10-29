# SKILL: 데이터베이스 (MariaDB)

> 대상 파일: `app/models.py`, `app/db.py`, `app/student_repo.py`, `app/auth.py`, `docker-compose.yml`, `scripts/seed_db.py`

## 1. 무엇이 어디에 있나

| 데이터 | 저장소 | 이유 |
|---|---|---|
| 학생·강의·수강 이력·졸업 기준·로그인 세션 | **MariaDB** | 학생별 조회, 런타임 쓰기(세션), 재시작해도 유지 |
| 교내 시설·건물 (`data/*.json`) | JSON → 메모리 검색 인덱스 | 팀이 직접 편집·검증, 검색은 메모리가 빠름 |

- 이 DB는 **해커톤용 원본**입니다. 학교 학사 시스템과 동기화하지 않습니다.
- `data/mock/*.json`은 DB의 **초기 데이터(시드)** 입니다. 목업을 고치면 `seed_db.py --reset`으로 다시 넣습니다.

## 2. 실행

```bash
docker compose up -d                 # MariaDB 11.4 (localhost:3306, 외부 미노출)
uvicorn app.main:app --reload        # DB_AUTO_INIT=true면 테이블 생성 + 비어 있으면 시드
python scripts/seed_db.py --reset    # 목업 수정 후 다시 넣기 (로그인 세션도 지워짐)
docker compose down                  # 중지 (데이터는 볼륨에 유지)
docker compose down -v               # 데이터까지 삭제
```

- 접속: `docker exec -it ditnow-mariadb mariadb -uditnow -pditnow ditnow`
- `.env`의 `DATABASE_URL`: `mysql+aiomysql://ditnow:ditnow@localhost:3306/ditnow?charset=utf8mb4`

## 3. 테이블

```
students                    학적 (학번 PK, 이름, 학과, 학년, password_hash, kakao_id UNIQUE)
courses ─< course_sessions  강의, 요일·시간·강의실
enrollments                 수강 이력 (학번, 강의, 학기, 이수구분, 성적) UNIQUE(학번, 강의, 학기)
graduation_rules ─< graduation_rule_categories   학과별 졸업 총 학점, 구분별 최소 학점
auth_sessions               로그인 세션 (token_hash PK, 학번, 만료 시각)
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
- 스키마를 바꾸면 해커톤 단계에서는 `seed_db.py --reset`으로 다시 만듭니다.
  실서비스로 가면 Alembic 마이그레이션을 도입하세요(지금은 없음).

## 5. 테스트

- 테스트와 `scripts/eval.py`는 Docker 없이 **SQLite 메모리 DB**(`sqlite+aiosqlite:///:memory:`)에 같은 테이블을 만들고 픽스처를 시드합니다.
- `tests/conftest.py`의 `db`(세션), `students`(학번 → DB에서 읽은 학생) 픽스처를 쓰세요.
- MariaDB 전용 동작(문자셋, 연결 끊김)은 자동 테스트가 없습니다. 스키마를 바꾸면 `docker compose up -d` 후 서버를 띄워 로그인·개인 질문을 직접 확인합니다.
