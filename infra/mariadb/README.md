# DIT NOW — MariaDB 인프라

DIT NOW 통합 플랫폼(FastAPI 백엔드 + RAG 챗봇)이 함께 쓰는 MariaDB 서버를 **팀원 개인 서버의 Ubuntu VM 위에 Docker로** 구성하는 설정과 운영 스크립트입니다.

> 이 디렉터리에는 **실제 비밀번호·서버 주소·백업 데이터가 들어 있지 않습니다.**
> 그런 값은 모두 서버에만 존재하는 `.env`, `secrets/`, `backups/`, `LOCAL_OPS.md`에 저장되며 `.gitignore`로 제외됩니다.

- 테이블·스키마·마이그레이션은 이 디렉터리의 범위가 **아닙니다** (`services/api/`의 마이그레이션이 담당).
- 여기서는 **DB 서버, 논리 DB, 계정·권한, 네트워크 노출, 백업**만 다룹니다.
- 기준 결정: `docs/11_DECISION_LOG.md`의 DEC-016(MariaDB 확정), DEC-019(개인 서버 VM · Tailscale · 3307 · DB/계정 분리).

> **개발자 로컬용이 아닙니다.** 이 Compose 파일은 **DB 서버(인프라 담당자의 VM)에서만** 실행하는 운영 정의입니다.
> DEC-019에 따라 개발자 PC·CI·`services/api`에서 MariaDB 컨테이너를 별도로 띄우지 말고, Tailscale을 통해 공용 DB 서버에 접속하세요.

---

## 목차

1. [구성 개요](#1-구성-개요)
2. [디렉터리 구조](#2-디렉터리-구조)
3. [보안 원칙](#3-보안-원칙)
4. [사전 준비 (서버/VM)](#4-사전-준비-서버vm)
5. [설치 절차](#5-설치-절차)
6. [설치 검증](#6-설치-검증)
7. [원격 접속 (FastAPI가 다른 머신에 있을 때)](#7-원격-접속-fastapi가-다른-머신에-있을-때)
8. [애플리케이션 연결 정보](#8-애플리케이션-연결-정보)
9. [백업과 복원](#9-백업과-복원)
10. [일상 운영](#10-일상-운영)
11. [비밀번호 교체](#11-비밀번호-교체)
12. [장애 대응](#12-장애-대응)
13. [커밋 전 체크리스트](#13-커밋-전-체크리스트)

---

## 1. 구성 개요

```
 [FastAPI / 챗봇 / 개발자 PC]
          │  Tailscale(사설 VPN) 또는 SSH 터널        ← 인터넷에 DB 포트 공개 없음
          ▼
 ┌──────────────── Ubuntu VM (개인 서버) ────────────────┐
 │  tailscale serve :3307 ─┐                              │
 │                         ▼                              │
 │            127.0.0.1:3307  (호스트 로컬 바인딩)          │
 │                         │ docker-proxy                 │
 │   ┌──── docker network ditnow_db (172.31.250.0/24) ──┐ │
 │   │  container ditnow-db  (mariadb:11.4, :3306)      │ │
 │   │  volume   ditnow_db_data → /var/lib/mysql        │ │
 │   └──────────────────────────────────────────────────┘ │
 └────────────────────────────────────────────────────────┘
```

| 항목 | 값 |
|---|---|
| DB 엔진 | MariaDB **11.4** (기존 챗봇 개발환경과 동일 메이저) |
| 실행 방식 | Docker Compose 단일 서비스, `restart: unless-stopped` |
| 문자셋 | `utf8mb4` / `utf8mb4_unicode_ci` |
| 시간대 | 컨테이너 `TZ=Asia/Seoul`, 시계는 호스트 NTP 사용 |
| 데이터 | 이름 있는 Docker 볼륨 `ditnow_db_data` (컨테이너 삭제·재생성에도 유지) |
| 노출 | 호스트 `127.0.0.1:3307`에만 바인딩. 원격은 Tailscale/SSH 터널 경유 |

### 논리 DB

| DB | 용도 |
|---|---|
| `ditnow` | 공통 플랫폼 DB. **사용자 신원·권한의 단일 원장** |
| `ditnow_chatbot` | 챗봇 전용 데이터 영역 (대화 기록, 인덱스 메타데이터 등) |

### 계정과 권한

| 계정 | 접속 허용 위치 | 권한 | 동시 접속 |
|---|---|---|---|
| `root` | 컨테이너 내부 localhost만 | 관리자 | – |
| `ditnow_migrator` | `DB_USER_HOST` (Docker 네트워크) | `ditnow`, `ditnow_chatbot` 전체 (GRANT 불가) | 5 |
| `ditnow_app` | 〃 | `ditnow` SELECT/INSERT/UPDATE/DELETE, `ditnow_chatbot` SELECT | 50 |
| `ditnow_chatbot` | 〃 | `ditnow_chatbot` SELECT/INSERT/UPDATE/DELETE, `ditnow` SELECT | 20 |
| `ditnow_backup` | 컨테이너 내부 localhost만 | 전역 SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT | – |

- 애플리케이션(`ditnow_app`)은 **DDL(CREATE/ALTER/DROP) 불가**. 스키마 변경은 `ditnow_migrator`로만.
- 챗봇은 사용자/권한을 **읽기만** 하고, 자체 데이터는 `ditnow_chatbot`에만 씀 → 신원 원장은 `ditnow` 하나로 유지.
- 외부 트래픽은 모두 Docker 네트워크 게이트웨이를 거쳐 들어오므로 서비스 계정의 호스트는 `DB_USER_HOST`(기본 `172.31.250.%`)로 제한됩니다. 실제 접근 통제는 **포트 바인딩 + Tailscale ACL/SSH 키**가 담당합니다.

---

## 2. 디렉터리 구조

```
.
├── README.md               이 문서 (공개)
├── compose.yaml            Docker Compose 정의 (값은 .env에서 주입)
├── conf/ditnow.cnf         MariaDB 서버 설정 (utf8mb4, 버퍼 등)
├── .env.example            환경 변수 템플릿 (비밀번호는 CHANGE_ME)
├── .gitignore              비밀/데이터 파일 제외 규칙
└── scripts/
    ├── _common.sh          공통 헬퍼 (직접 실행하지 않음)
    ├── gen-env.sh          .env 생성 + 무작위 비밀번호
    ├── provision.sh        DB·계정·권한 생성/재적용 (멱등)
    ├── db-root.sh          root 클라이언트 (비밀번호 비노출)
    ├── db-client.sh        서비스 계정으로 TCP 접속 테스트
    ├── backup.sh           논리 백업 (gzip, 600, 보관기간 자동 정리)
    ├── restore-test.sh     백업을 테스트 DB로 복원 검증
    └── export-role-env.sh  역할별 연결 정보 파일 생성 (secrets/)

# 서버에만 존재 (git 제외)
.env                        실제 설정과 비밀번호 (600)
secrets/*.env               역할별 연결 정보 (600)
backups/*.sql.gz            백업 파일 (600)
LOCAL_OPS.md                서버 고유 운영 메모 (IP, tailnet 등)
```

---

## 3. 보안 원칙

1. **DB 포트를 인터넷에 열지 않는다.** `DB_BIND_ADDR`는 항상 `127.0.0.1`. `0.0.0.0`으로 바꾸지 말 것.
   - 주의: Docker가 공개한 포트는 **ufw 규칙을 우회**합니다. 그래서 바인딩 주소 자체로 막습니다.
2. **원격 접속은 사설 경로만**: Tailscale(권장) 또는 SSH 터널(키 인증).
3. **애플리케이션에 root를 주지 않는다.** root는 컨테이너 내부 소켓 접속만 허용.
4. **비밀번호·개인키를 Git, 이슈, PR, 채팅에 올리지 않는다.** 전달은 팀이 승인한 비밀 저장소(예: 1Password/Bitwarden 공유 볼트, 클라우드 Secret Manager, CI Secret)로만.
5. **스크립트는 비밀번호를 명령줄 인자로 넘기지 않는다** (`ps`/셸 히스토리 노출 방지). stdin 또는 600 권한 임시 파일 사용.
6. **VM 스냅샷은 DB 백업이 아니다.** 논리 백업 + 서버 외부 사본을 유지.
7. 서버 고유 정보(공인/VPN IP, 호스트명, tailnet 이름, 같은 서버의 다른 서비스)는 `LOCAL_OPS.md`에만 기록.

---

## 4. 사전 준비 (서버/VM)

### 4.1 권장 VM 사양 (해커톤 기준)

| 항목 | 권장 |
|---|---|
| OS | Ubuntu Server 22.04/24.04 LTS |
| vCPU / RAM | 2 / 4GB (DB 컨테이너 상한 1.5GB) |
| 디스크 | 30GB 이상 |
| 네트워크 | 고정 사설 IP 또는 DHCP 예약 |
| 하이퍼바이저 | VM 자동 시작(Proxmox: *Start at boot*) 활성화 |

### 4.2 기본 패키지 / Docker

```sh
sudo apt update && sudo apt -y upgrade
sudo apt -y install ca-certificates curl gzip openssl
# Docker Engine + Compose plugin (공식 문서: https://docs.docker.com/engine/install/ubuntu/)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"     # 재로그인 후 sudo 없이 docker 사용 가능
docker compose version              # v2 이상 확인
```

> 스크립트는 `docker`가 권한 없이 동작하지 않으면 자동으로 `sudo docker`를 사용합니다.

### 4.3 시간 동기화

```sh
timedatectl                         # "System clock synchronized: yes" 확인
sudo timedatectl set-ntp true       # 꺼져 있으면 켜기
sudo timedatectl set-timezone Asia/Seoul
```

### 4.4 SSH 보안 (키 인증만)

`/etc/ssh/sshd_config` (또는 `/etc/ssh/sshd_config.d/*.conf`):

```
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password   # 가능하면 no
```

```sh
sudo sshd -t && sudo systemctl reload ssh
```

> **반드시 현재 SSH 세션을 유지한 채 새 터미널에서 접속이 되는지 확인한 뒤** 기존 세션을 닫으세요.

### 4.5 방화벽 (ufw)

원격 접속이 끊기지 않도록 **SSH 허용을 먼저** 넣고, 5분 뒤 자동 해제되는 안전장치를 건 상태에서 켭니다.

```sh
# 안전장치: 5분 후 ufw 자동 비활성화 (접속이 끊겨도 복구됨)
sudo systemd-run --on-active=300 --unit=ufw-failsafe /usr/sbin/ufw disable

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
# 같은 서버에서 외부 공개가 필요한 다른 서비스가 있다면 여기서 개별 허용
sudo ufw --force enable
sudo ufw status verbose

# 새 터미널로 SSH 재접속 성공을 확인한 뒤 안전장치 해제
sudo systemctl stop ufw-failsafe.timer
```

DB 포트(3306/3307)는 ufw에 **허용 규칙을 추가하지 않습니다.**

---

## 5. 설치 절차

### 5.1 파일 배치

저장소를 서버에 받고 이 디렉터리로 이동합니다.

```sh
git clone https://github.com/not-a-devs/ditNow.git
cd ditNow/infra/mariadb
chmod 700 .                         # 같은 서버의 다른 사용자가 .env를 못 보게
```

### 5.2 `.env` 생성

```sh
scripts/gen-env.sh                  # .env.example → .env, 비밀번호 5개 무작위(32자) 생성, 권한 600
```

`.env`를 열어 **비밀번호가 아닌 설정**만 필요 시 조정합니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DB_IMAGE` | `mariadb:11.4` | 11.4 LTS 라인 유지 (패치 버전 자동 반영) |
| `DB_CONTAINER_NAME` | `ditnow-db` | 컨테이너 이름 |
| `DB_BIND_ADDR` | `127.0.0.1` | **변경 금지** |
| `DB_HOST_PORT` | `3307` | 호스트 포트. 같은 서버에 다른 MariaDB가 3306을 쓰는 경우 대비 |
| `DB_SUBNET` | `172.31.250.0/24` | 이 스택 전용 Docker 네트워크. `docker network inspect`로 다른 네트워크와 겹치지 않는지 확인 |
| `DB_USER_HOST` | `172.31.250.%` | 서비스 계정 접속 허용 호스트. `DB_SUBNET`과 일치시킬 것 |
| `DB_MEM_LIMIT` | `1536m` | 컨테이너 메모리 상한. `conf/ditnow.cnf`의 `innodb_buffer_pool_size`(512M)보다 충분히 크게 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `BACKUP_RETENTION_DAYS` | `14` | 로컬 백업 보관 일수 |

> `.env`는 **생성 직후 팀 비밀 저장소에 백업**해 두세요. 분실하면 계정 비밀번호를 재설정해야 합니다.

### 5.3 기동

```sh
docker compose up -d
docker compose ps                   # STATUS가 "healthy"가 될 때까지 대기(약 10~30초)
```

### 5.4 DB와 계정 생성

```sh
scripts/provision.sh                # "provisioned" 출력. 여러 번 실행해도 안전
```

### 5.5 설정 확인

```sh
scripts/db-root.sh -e "SELECT version(), @@character_set_server, @@collation_server, now();
                       SHOW DATABASES LIKE 'ditnow%';
                       SELECT user, host, max_user_connections FROM mysql.user WHERE user LIKE 'ditnow%';"
```

기대값: `11.4.x-MariaDB`, `utf8mb4`, `utf8mb4_unicode_ci`, DB `ditnow`, `ditnow_chatbot`, 계정 4개.

---

## 6. 설치 검증

아래는 최초 구축 시 한 번 수행하는 검증 절차입니다. 검증용 테이블은 **`ditnow`가 아닌 별도 DB**에 만듭니다
(공통 DB에 남으면 마이그레이션 도구의 autogenerate가 이를 삭제 대상으로 잡을 수 있음).

### 6.1 CRUD

```sh
scripts/db-root.sh <<'SQL'
CREATE DATABASE IF NOT EXISTS ditnow_infra_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS ditnow_infra_test.persist_check (
  id INT AUTO_INCREMENT PRIMARY KEY, note VARCHAR(100), created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
INSERT INTO ditnow_infra_test.persist_check(note) VALUES ('hello'), ('한글 utf8mb4 ✅'), ('to-delete');
UPDATE ditnow_infra_test.persist_check SET note='updated' WHERE note='hello';
DELETE FROM ditnow_infra_test.persist_check WHERE note='to-delete';
SELECT * FROM ditnow_infra_test.persist_check;
SQL
```

### 6.2 권한 분리 (TCP, 애플리케이션과 같은 경로)

```sh
scripts/db-client.sh app      ditnow -e "SELECT current_user();"          # 성공
scripts/db-client.sh app      ditnow -e "CREATE TABLE x(i INT);"          # ERROR 1142 (거부되어야 정상)
scripts/db-client.sh app      mysql  -e "SELECT 1;"                       # ERROR 1044 (거부)
scripts/db-client.sh chatbot  ditnow -e "SELECT 1;"                       # 성공 (읽기)
scripts/db-client.sh migrator ditnow -e "CREATE TABLE _t(i INT); DROP TABLE _t;"   # 성공
docker run --rm --network host mariadb:11.4 \
  mariadb -h127.0.0.1 -P3307 -uroot -pwrong -e "SELECT 1"                 # ERROR 1045 (root 원격 거부)
```

### 6.3 외부 노출 차단

```sh
sudo ss -tlnp | grep 3307           # 127.0.0.1:3307 (및 Tailscale 사용 시 100.x 주소)만 보여야 함
```

인터넷 쪽 PC(VPN 미접속)에서:

```sh
nc -zv <서버 공인 IP> 3307           # Linux/macOS — "refused" 또는 timeout이 정상
Test-NetConnection <서버 공인 IP> -Port 3307    # Windows — TcpTestSucceeded : False 가 정상
```

### 6.4 재시작 후 데이터 유지

```sh
docker compose restart                              # ① MariaDB 재시작
docker compose down && docker compose up -d         # ② 컨테이너 재생성 (볼륨 유지)  ※ -v 절대 금지
sudo reboot                                         # ③ VM 재부팅 (같은 서버의 다른 서비스도 재시작됨 — 팀과 조율)
# 각 단계 후
docker compose ps
scripts/db-root.sh -e "SELECT * FROM ditnow_infra_test.persist_check;"
```

### 6.5 백업·복원

```sh
scripts/backup.sh                   # backups/ditnow_<시각>.sql.gz 생성
scripts/restore-test.sh             # 최신 백업 → ditnow_restore_test* 복원, 테이블 수 출력 후 정리
ls -l backups/                      # -rw------- 인지 확인
```

검증이 끝나면 테스트 DB를 지워도 됩니다: `scripts/db-root.sh -e "DROP DATABASE ditnow_infra_test;"`

---

## 7. 원격 접속 (FastAPI가 다른 머신에 있을 때)

DB 포트를 공개하는 대신 아래 두 방법 중 하나를 사용합니다.

### 7.1 Tailscale (상시 운영 권장)

**DB 서버에서**

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                                         # 출력된 URL로 팀 tailnet에 로그인
sudo tailscale serve --bg --tcp 3307 tcp://127.0.0.1:3307 # tailnet 내부에만 3307 노출
tailscale serve status                                    # "(tailnet only)" 확인
tailscale ip -4                                           # → 클라이언트의 DB_HOST 값
```

**FastAPI 서버 / 개발 PC에서**

1. Tailscale 설치 후 **같은 tailnet**에 로그인
   - Linux: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
   - macOS/Windows: https://tailscale.com/download
2. 연결 확인
   ```sh
   nc -zv <DB 서버 Tailscale IP> 3307                      # Linux/macOS
   Test-NetConnection <DB 서버 Tailscale IP> -Port 3307     # Windows PowerShell
   ```
3. `DB_HOST=<DB 서버 Tailscale IP 또는 MagicDNS 이름>`, `DB_PORT=3307`

**접근 제한 (권장)**: Tailscale 관리 콘솔 → Access controls에서 DB 서버에 태그(예: `tag:ditnow-db`)를 붙이고,
FastAPI 노드만 `tag:ditnow-db:3307`에 접근하도록 정책을 작성합니다. 테스트용으로 추가한 기기는 테스트 후 tailnet에서 제거합니다.

서버에서 원격 경로를 직접 테스트할 수도 있습니다.

```sh
DB_CLIENT_HOST=<Tailscale IP> scripts/db-client.sh app ditnow -e "SELECT 'ok';"
```

### 7.2 SSH 터널 (개발/DB 툴, 임시 접속)

DB 서버에 SSH 키로 접속 가능한 사람만 사용할 수 있습니다.

```sh
ssh -N -L 3307:127.0.0.1:3307 <user>@<DB 서버 주소>
# 터널이 열려 있는 동안: host 127.0.0.1, port 3307
```

DBeaver/HeidiSQL 등은 연결 설정의 "SSH 터널" 탭에 같은 정보를 넣어도 됩니다.

---

## 8. 애플리케이션 연결 정보

### 8.1 연결 값

| 항목 | 값 | 비고 |
|---|---|---|
| 호스트 | DB 서버의 Tailscale IP 또는 MagicDNS 이름 | DB와 같은 VM에서 실행할 때만 `127.0.0.1` |
| 포트 | `3307` | |
| DB | `ditnow` | 챗봇 전용 자료는 `ditnow_chatbot` |
| 계정 | `services/api` 런타임 → `ditnow_app` | 마이그레이션 명령 → `ditnow_migrator`, 챗봇 전용 자료 → `ditnow_chatbot` |
| 비밀번호 | *(팀 비밀 저장소)* | 저장소·로그·OpenAPI에 포함 금지 |
| 문자셋 | `utf8mb4` | |
| SQLAlchemy URL 형식 | `mysql+aiomysql://<user>:<pw>@<host>:3307/<db>?charset=utf8mb4` | 기존 챗봇은 async SQLAlchemy + aiomysql |

- `services/api`는 `DIT_API_` 접두사 설정 정책을 따릅니다. **실제 설정 필드 이름은 `services/api` 담당자가 정하며**, 이 디렉터리는 애플리케이션 코드·설정을 수정하지 않습니다.
- `ditnow_migrator` 비밀번호는 어떤 런타임(앱·챗봇·브라우저)에도 주입하지 않고, 승인된 마이그레이션 실행 환경에만 둡니다.
- `scripts/export-role-env.sh`가 만드는 파일은 범용 이름(`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DATABASE_URL`)을 씁니다. 비밀 저장소에 등록할 때 `services/api`의 `DIT_API_` 필드 이름으로 옮겨 적으세요.

### 8.1.1 전송 암호화 (TLS)

- 원격 구간은 **Tailscale(WireGuard)로 암호화**됩니다.
- MariaDB 11.4는 기동 시 **자체 서명 인증서로 TLS를 자동 활성화**합니다(TLSv1.2/1.3, 확인 시 TLSv1.3 사용). 클라이언트에서 `SHOW STATUS LIKE 'Ssl_version'`으로 확인할 수 있습니다.
- 다만 이 인증서는 CA가 발급한 것이 아니어서 **클라이언트의 인증서 검증(verify)은 아직 설정되지 않았습니다.** CA 검증이 필요하면 팀 CA로 서버 인증서를 발급해 `conf/`에 `ssl_cert`/`ssl_key`/`ssl_ca`를 추가하고 클라이언트에 CA를 배포합니다(OPEN-002 후속). 검증 실패를 이유로 검증을 끄는 방식으로 우회하지 않습니다.

### 8.2 역할별 연결 파일 만들기 (서버에서)

```sh
scripts/export-role-env.sh <DB_HOST> 3307
# → secrets/fastapi.env, secrets/migrator.env, secrets/chatbot.env  (권한 600)
```

이 파일의 내용을 **팀 비밀 저장소**에 등록하고, 각 실행 환경(클라우드 Secret, 로컬 `.env` 등 git 제외 위치)에 주입합니다.
Git·메신저·이슈에는 절대 붙여넣지 않습니다.

### 8.3 연결 권장 옵션

- 문자셋 `utf8mb4` 명시 (`?charset=utf8mb4`)
- 커넥션 풀: `pool_pre_ping=True`, `pool_recycle=1800` (MariaDB `wait_timeout` 대비)
- 풀 크기 합계가 계정별 동시 접속 한도(app 50, chatbot 20)를 넘지 않게

---

## 9. 백업과 복원

### 9.1 정기 백업 (cron)

```sh
crontab -e
# 매일 03:30 백업 (경로는 실제 위치로)
30 3 * * * /path/to/this/dir/scripts/backup.sh >> /path/to/this/dir/backups/backup.log 2>&1
```

- 대상: `ditnow`, `ditnow_chatbot` (`--single-transaction`으로 서비스 중단 없이)
- 결과: `backups/ditnow_YYYYmmdd_HHMMSS.sql.gz` (600), `BACKUP_RETENTION_DAYS`일 지난 파일 자동 삭제
- sudo가 필요한 환경이라면 cron 사용자에게 NOPASSWD docker 권한 또는 docker 그룹이 있어야 합니다.

### 9.2 서버 외부 사본 (필수 권장)

개인 서버 장애에 대비해 백업을 **서버 밖**에 보관합니다. 팀이 승인한 위치를 사용하세요. 예:

```sh
# 다른 머신으로 (SSH 키 기반)
rsync -a --chmod=F600 backups/ <user>@<backup-host>:/secure/ditnow-db/
# 또는 rclone으로 클라우드 스토리지 (암호화 remote 권장)
rclone copy backups/ <encrypted-remote>:ditnow-db/
```

### 9.3 복원

```sh
# 검증용 (운영 DB 안전): 이름을 바꿔 ditnow_restore_test* 로 복원
scripts/restore-test.sh backups/ditnow_XXXX.sql.gz --keep

# 운영 복원 (데이터를 덮어씀!) — 직전 상태를 먼저 백업
scripts/backup.sh
zcat backups/ditnow_XXXX.sql.gz | scripts/db-root.sh
```

---

## 10. 일상 운영

```sh
docker compose up -d                # 시작
docker compose stop                 # 중지 (데이터 유지)
docker compose restart              # 재시작
docker compose ps                   # 상태 (healthy)
docker compose logs --tail 100 db   # 로그
scripts/db-root.sh -e "status"      # 서버 상태
docker system df -v | grep ditnow   # 볼륨 사용량
```

### 이미지 업데이트 (11.4 패치)

```sh
scripts/backup.sh
docker compose pull && docker compose up -d     # MARIADB_AUTO_UPGRADE=1 로 시스템 테이블 자동 업그레이드
docker compose ps && scripts/db-root.sh -e "SELECT version();"
```

메이저 버전 변경(예: 11.4 → 11.8)은 챗봇·API 호환성 확인 후 팀 합의로 진행합니다.

### 절대 하지 말 것

- `docker compose down -v`, `docker volume rm ditnow_db_data` → **모든 데이터 삭제**
- `DB_BIND_ADDR=0.0.0.0` 또는 ufw/라우터에서 3306·3307 개방
- `.env`, `secrets/`, `backups/`를 git에 추가 (`git add -f` 금지)

---

## 11. 비밀번호 교체

```sh
# 1) .env에서 해당 *_PASSWORD 값 교체 (예: openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32)
# 2) 계정에 반영
scripts/provision.sh
# 3) 연결 파일 재생성 → 비밀 저장소 갱신 → 애플리케이션 재배포
scripts/export-role-env.sh <DB_HOST> 3307
```

root 비밀번호 교체는 컨테이너 환경 변수와 실제 계정을 함께 바꿔야 합니다.

```sh
scripts/db-root.sh -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '<새 비밀번호>';"   # 실행 후 셸 히스토리 정리
# .env의 DB_ROOT_PASSWORD 갱신 후
docker compose up -d                # 컨테이너 재생성(데이터 유지)으로 새 값 반영
```

---

## 12. 장애 대응

| 증상 | 확인 | 조치 |
|---|---|---|
| `docker compose ps`가 unhealthy/재시작 반복 | `docker compose logs --tail 200 db` | 디스크(`df -h`), 메모리(`free -h`) 확인 후 `docker compose restart` |
| `ERROR 1045 Access denied` | 비밀번호/사용자명, `DB_USER_HOST` | `scripts/provision.sh` 재실행으로 비밀번호·권한 재적용 |
| `ERROR 1142 ... command denied` | 계정 권한표(1장) | 정상 동작일 수 있음. DDL은 `ditnow_migrator`로 |
| `Too many connections` / `max_user_connections` | 애플리케이션 풀 크기 | 풀 크기 축소 또는 `provision.sh`의 한도 조정 |
| 원격에서 접속 불가 | `tailscale status`, `tailscale serve status`, 클라이언트 tailnet 로그인 | `sudo tailscale serve --bg --tcp 3307 tcp://127.0.0.1:3307` 재적용 |
| `.env not found` | 현재 디렉터리 | 스크립트는 어디서 실행해도 이 디렉터리 기준. `.env` 존재 확인 |
| 포트 충돌(3307 사용 중) | `sudo ss -tlnp \| grep 3307` | `.env`의 `DB_HOST_PORT` 변경 후 `docker compose up -d` |
| 서브넷 충돌 | `docker network inspect $(docker network ls -q) \| grep Subnet` | `DB_SUBNET`, `DB_USER_HOST` 함께 변경 → `up -d` → `provision.sh` |

---

## 13. 커밋 전 체크리스트

```sh
git status --ignored                # .env, secrets/, backups/, LOCAL_OPS.md 가 "Ignored"에 있어야 함
git diff --cached | grep -nE 'PASSWORD=[^C]|BEGIN .*PRIVATE KEY|[0-9]{1,3}(\.[0-9]{1,3}){3}' \
  | grep -vE '127\.0\.0\.1|172\.31\.250\.' || echo "OK: 비밀/주소 패턴 없음"
```

- [ ] 실제 비밀번호, 개인키, 토큰이 없다
- [ ] 서버 공인 IP, Tailscale IP, tailnet 이름, 호스트명이 없다
- [ ] 같은 서버의 다른 서비스 정보가 없다
- [ ] `.env.example`의 비밀번호는 모두 `CHANGE_ME`
