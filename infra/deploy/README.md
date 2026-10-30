# 기존 서버 소유자용 DIT NOW 배포 패키지

TASK-OWNER-DEPLOYMENT-PACKAGE · 2026-10-30. 이 저장소의 새 두 컨테이너만 대상이다. **이 문서는 운영 배포 실행·Tunnel 변경 승인이 아니다. 서버 소유자가 검토 후 직접 실행한다.** Codex는 SSH·운영 Docker·DB·실제 비밀·Tunnel에 접근하지 않는다.

## 확정한 경계와 차단 조건

- 공개 주소: `https://dit.sunghae.xyz`. 기존 Tunnel origin: `http://127.0.0.1:18080`.
- Linux Docker `network_mode: host` 서비스 2개: Nginx `127.0.0.1:18080`, FastAPI `127.0.0.1:18000`, worker 1. `ports:` 매핑·0.0.0.0·새 DB 컨테이너·Tailscale 설치·기존 8개 서비스 변경은 없다.
- **기존 cloudflared가 호스트 프로세스 또는 같은 호스트의 host-network 컨테이너여야 한다.** bridge 컨테이너의 127.0.0.1은 별도 namespace라 이 origin이 연결되지 않는다. 현재 실행 형태 미확인이면 **BLOCKED**. 이 패키지에는 cloudflared·Tunnel 토큰·Tunnel 변경 명령이 없다.
- Docker Engine/Compose는 기존 설치를 사용한다. Compose **2.30 이상** 필요(`env_file.format: raw`로 비밀번호의 `$`·따옴표를 재해석하지 않음). 업그레이드·Docker daemon 재시작은 기존 서비스에 영향이 있으므로 자동 수행하지 않는다. 소유자 사전 확인이 필요하다.
- 호스트 점검 스크립트는 Python 3.10 이상 표준 라이브러리·Git·`ss`가 필요하다. API Python 3.13과 Node 22 빌드는 이미지 안에서 설치한다. 호스트 Python/도구가 없으면 소유자가 기존 관리 절차로 준비하며 이 패키지가 시스템 패키지를 변경하지 않는다.
- 기본은 **DB·개인 P0·LLM 없는 공개 프로필**이다. 기존 승인된 DEMO P0 활성화는 소유자와 root의 별도 승인·비밀 주입·실제 업무 검증을 따른다. public smoke 성공은 운영 P0·외부 HTTPS·실DB·LLM 성공이 아니다.

공식 근거(2026-10-30 확인): [Docker host network](https://docs.docker.com/engine/network/drivers/host/), [Compose 서비스·raw env·bind](https://docs.docker.com/reference/compose-file/services/), [Cloudflare origin routing](https://developers.cloudflare.com/tunnel/concepts/routing/). host 모드는 호스트 네트워크 namespace를 공유하므로 컨테이너의 실제 bind 주소가 중요하다. 이 선택은 기존 loopback origin을 유지하기 위한 승인 범위다.

## 1. 고정 release·외부 설정 준비 — 소유자만

서버 소유자가 별도 checkout을 준비하고 전달받은 **병합된 최종 40자리 SHA**에 고정한다. `main` 이동 이름이나 태그만 믿지 않는다. 기존 서버 작업 디렉터리/컨테이너를 덮어쓰지 않는다. 아래 변수는 비밀이 아닌 로컬 파일 경로와 SHA이며 실제 경로는 소유자가 지정한다.

```sh
# 저장소 루트에서. 실제 승인된 release SHA로 바꾸며 placeholder로 실행하지 않는다.
RELEASE_SHA=REPLACE_WITH_APPROVED_40_CHARACTER_SHA
git fetch origin
git switch --detach "$RELEASE_SHA"
git status --short

# 모두 checkout 바깥의 절대 경로. 실제 값을 공개 PR·로그·채팅에 붙이지 않는다.
API_ENV_FILE=/absolute/private/ditnow-api.env
DEPLOY_ENV_FILE=/absolute/private/ditnow-deploy.env
CA_FILE=/absolute/approved/mariadb-ca.pem
SNAPSHOT_FILE=/absolute/private/ditnow-before-release.json
```

외부 파일 생성은 아래 **실패 즉시 중단 함수**로만 한다. 독립된 `test ! -e` 줄 다음에 `cp`/`printf`를 따로 실행하면 대화형 shell은 검사 실패 후에도 다음 줄을 계속 실행하여 기존 runtime env를 덮어쓸 수 있으므로 그 형태를 쓰지 않는다. 함수는 subshell `( … )`에서 `set -eu`·`set -o noclobber`·`umask 077`을 켜므로 소유자 shell 옵션을 바꾸지 않는다. `ditnow_bootstrap || …`처럼 errexit가 꺼지는 문맥에서도 각 단계가 명시적으로 `fail`한다.

```sh
# BEGIN-DITNOW-BOOTSTRAP
ditnow_bootstrap() (
  set -eu
  set -o noclobber
  umask 077
  fail() { printf 'DITNOW_BOOTSTRAP_BLOCKED %s\n' "$1" >&2; exit 1; }
  template=infra/deploy/api.env.example
  case "${RELEASE_SHA:-}" in
    ''|*[!0-9a-f]*) fail RELEASE_SHA_INVALID ;;
  esac
  [ "${#RELEASE_SHA}" -eq 40 ] || fail RELEASE_SHA_INVALID
  for path in "${API_ENV_FILE:-}" "${DEPLOY_ENV_FILE:-}" "${CA_FILE:-}"; do
    case "$path" in
      /*) ;;
      *) fail PATH_NOT_ABSOLUTE ;;
    esac
    case "$path" in
      *[!A-Za-z0-9_./-]*) fail PATH_CHARACTERS_UNSAFE ;;
    esac
  done
  [ "$API_ENV_FILE" != "$DEPLOY_ENV_FILE" ] && [ "$API_ENV_FILE" != "$CA_FILE" ] \
    && [ "$DEPLOY_ENV_FILE" != "$CA_FILE" ] || fail PATHS_NOT_DISTINCT
  for target in "$API_ENV_FILE" "$DEPLOY_ENV_FILE"; do
    if [ -e "$target" ] || [ -L "$target" ]; then fail TARGET_EXISTS; fi
    [ -d "$(dirname "$target")" ] || fail TARGET_DIRECTORY_MISSING
  done
  { [ -f "$template" ] && [ ! -L "$template" ]; } || fail TEMPLATE_MISSING
  { cat "$template" > "$API_ENV_FILE"; } 2>/dev/null || fail API_ENV_CREATE_FAILED
  { printf 'DITNOW_RELEASE_SHA=%s\nDITNOW_API_ENV_FILE=%s\nDITNOW_DB_CA_FILE=%s\n' \
    "$RELEASE_SHA" "$API_ENV_FILE" "$CA_FILE" > "$DEPLOY_ENV_FILE"; } 2>/dev/null || fail DEPLOY_ENV_CREATE_FAILED
  chmod 600 "$API_ENV_FILE" "$DEPLOY_ENV_FILE" 2>/dev/null || fail PERMISSION_FAILED
  printf 'DITNOW_BOOTSTRAP_CREATED\n'
)
# END-DITNOW-BOOTSTRAP
ditnow_bootstrap
```

모든 경로 검사(40자리 소문자 hex SHA, 절대 경로, 안전 문자 `A-Za-z0-9_./-`만, 세 경로 서로 다름, 대상 두 개와 dangling symlink 미존재, 상위 디렉터리 존재, 일반 파일 template)가 끝난 후에만 쓴다. 생성은 `cp`가 아니라 noclobber 리다이렉션으로 하므로 검사 후 경쟁적으로 생긴 파일도 덮어쓰지 않고 실패한다. CA 파일은 이 함수가 만들거나 쓰지 않으며 대상 경로와 같으면 차단한다. 새 파일은 umask 077과 `chmod 600`으로 비공개다. 출력은 고정 코드만이며 경로·template·파일 내용을 출력하지 않는다. pointer 단계에서 실패하면 template 복사본(비밀 없음)만 남을 수 있으므로 소유자가 확인 후 직접 정리한다.

기존 파일이 있으면 덮어쓰지 말고 소유자가 검토한다. API env는 **shell source하지 않는다**. raw 형식은 `KEY=value`의 값에 따옴표까지 포함시키므로 UUID 목록 같은 JSON은 추가 shell quote 없이 그대로 쓴다. 비밀번호는 편집기/기존 보호된 비밀 주입으로만 제공하며 명령 인자·Docker build arg·이미지·VITE 변수·이 저장소에 넣지 않는다.

CA는 승인된 공개 CA PEM 파일이며 이미지에는 복사하지 않고 단일 파일을 read-only mount한다. 컨테이너 UID10001이 읽을 수 있는 공개 인증서 파일 권한(예: 0644)이 필요하다. CA의 지문·SAN·만료·GRANT·공통 원장 승인 검증은 별도다. 기본 공개 프로필에서는 이 파일을 mount만 하고 DB 설정·CA 로딩·연결을 하지 않는다. **CA가 없으면 실제 경로를 만들 때까지 차단**하며 빈 파일을 실제 신뢰 인증서로 사용하지 않는다. CI의 비신뢰 fixture 파일은 공개 프로필 전용이고 TLS 검증 증거가 아니다.

앱 DB는 기존 `DIT_API_DB_*`·`ditnow_app`만 쓴다. P0 활성화 시 기존 승인 감사 UUID/flag·앱 비밀번호·`DIT_API_DB_TLS_CA_FILE=/run/certs/mariadb-ca.pem`를 보호된 env에 주입한다. migrator·DATABASE_URL·DB 초기화·자동 시드·교직원/admin 생성·LLM 활성화는 이 패키지에 없다. Compose는 production/docs=false/CORS=[]를 고정한다. 설정 일부만 주입하면 앱이 실패하거나503으로 닫히며 임의로 검증을 완화하지 않는다.

## 2. 읽기 전용 사전 검사와 기존 8개 snapshot

소유자가 기존 cloudflared network를 **값만** 확인한다. 컨테이너라면 아래 명령은 network mode 하나만 출력하며 Env/Args/token을 출력하지 않는다. 호스트 서비스라면 소유자가 서비스의 실제 호스트 namespace를 확인한다. 전체 `docker inspect`, 프로세스 명령줄, 설정 dump를 공유하지 않는다.

```sh
docker inspect --format '{{.HostConfig.NetworkMode}}' EXISTING_CLOUDFLARED_CONTAINER
```

확인되지 않거나 bridge면 중단한다. Tunnel 설정을 자동으로 바꾸지 않는다. host namespace 확인이 끝난 후에만 다음 확인 flag를 사용한다.

```sh
python3 infra/deploy/scripts/check_owner.py --deploy-env "$DEPLOY_ENV_FILE" --snapshot "$SNAPSHOT_FILE" --tunnel-host-network-confirmed
```

검사: 정확한 clean Git SHA, Linux/local Unix Docker socket, Compose 버전, 18080/18000 포트 미사용, 이 프로젝트 외 **기존 컨테이너 8개**의 ID/이름/image/state, env/CA 외부 파일과 권한, **`docker compose config -q`만**. `ditnow-campus` label의 선행 컨테이너가 하나라도 있으면 별도 검토 전 BLOCKED이며 임의로 본인 자원으로 채택하지 않는다. API env·CA 내용은 Python이 읽지 않으며 Docker의 quiet config 검증도 해석된 값을 출력하지 않는다. snapshot은 외부 경로에 mode0600으로 **새로만** 쓰며 기존 파일을 덮어쓰지 않는다. 재검사는 새 snapshot 이름을 사용한다.

PASS여도 실제 DB·외부 HTTPS·운영 권한·Tunnel 연결이 검증된 것은 아니다. 명시된 `DOCKER_CONTEXT`는 `DOCKER_HOST`보다 우선하므로 값이 있으면 Docker 명령 전에 BLOCKED한다. 이를 임의로 해제하여 다른 daemon을 선택하지 말고 소유자가 별도로 검토한다. 기본 context의 endpoint도 daemon metadata 조회 전에 Unix socket인지 검사한다. 포트 충돌/기존 컨테이너 수 변경/원격 Docker context/dirty source도 BLOCKED다. 타 컨테이너를 중지해 통과시키지 않는다. 업그레이드의 선행 프로젝트 자원 재사용·제거는 소유자가 따로 검토해야 하며 이 최초 배포 사전 검사는 이를 자동 승인하지 않는다.

## 3. 이 프로젝트만 build/up

고정된 같은 checkout에서 소유자가 아래 shell 함수를 정의한다. 항상 동일 프로젝트·파일·외부 pointer env를 쓴다. **값이 펼쳐진 `docker compose config`를 출력하지 않는다.**

```sh
ditnow_compose() {
  python3 infra/deploy/scripts/check_owner.py --deploy-env "$DEPLOY_ENV_FILE" --source-only > /dev/null || return
  env -u DITNOW_RELEASE_SHA -u DITNOW_API_ENV_FILE -u DITNOW_DB_CA_FILE docker compose --project-name ditnow-campus --env-file "$DEPLOY_ENV_FILE" -f infra/deploy/compose.yaml "$@"
}
ditnow_compose config -q
ditnow_compose build api web
ditnow_compose up -d --no-build --pull never api web
ditnow_compose ps
```

이미지는 `ditnow-api:<SHA>` / `ditnow-web:<SHA>`와 OCI revision label로 식별한다. base image 태그는 가변이므로 소유자가 실제 build image ID/RepoDigest와 최종 source SHA를 보호된 실행 기록에 남긴다. 의존성은 기존 npm lock·uv lock을 사용한다. API의 기존 chatbot 패키지를 wheel로 재사용하며 사전 `mvp/`는 build context에서 제외한다. 컨테이너 자동 재시작 정책은 현재 `no`이며 운영 서비스 관리자는 소유자가 결정한다.

FastAPI는 `--no-proxy-headers`를 유지한다. Nginx는 외부 forwarded IP 헤더를 신뢰하지 않으며 이 proxy를 거친 모든 방문자는 기존 **공유 IP당20회/분** 제한을 함께 쓸 수 있다. 한도를 임의로 높이거나 끄지 않는다. 심사 pacing·정확한 proxy 신뢰/사용자별 남용 방어 검토가 남는다. 이 상태를 대규모 운영·개별 사용자 quota 검증이라고 주장하지 않는다.

## 4. 소유자만 실제 공개 프로필 smoke

```sh
python3 infra/deploy/scripts/smoke.py --wait-seconds 30 --snapshot "$SNAPSHOT_FILE"
ss -H -ltn
```

smoke 목적지는 고정 loopback뿐이며 환경 proxy·redirect·비밀번호·토큰을 사용하지 않는다. 실제 두 listener가 각각 **127.0.0.1**인지, Nginx→API health, `/app/login` 등 SPA 직접 진입과 index no-store, 실제 hashed asset, SPA·asset·API health 응답의 `X-Content-Type-Options: nosniff`, 없는 asset404, API JSON404, 기본 미설정 로그인503/P0업무404, 기존8개 metadata 불변을 검사한다. 실제 로그인/P0를 승인해 켠 뒤에는 public smoke의503/404 기대가 맞지 않으므로 그 결과를 억지로 PASS로 바꾸지 말고 별도 승인된 업무 E2E를 따른다.

보호된 실행 기록에는 release SHA·image ID·단계·결과·기존8개 보존만 남긴다. 응답 원문·비밀번호·감사 UUID·토큰을 저장소에 올리지 않는다. 공개 URL은 서버 소유자와 root가 별도 승인 후 `https://dit.sunghae.xyz`에서 검증한다. localhost CI 성공이 실제 Cloudflare·TLS·CORS·브라우저/P0 성공을 뜻하지 않는다.

## 5. 로그·중지·롤백 — 다른 프로젝트 제외

```sh
# 로컬 보호 터미널에서만 확인. 그대로 공개 채팅/PR에 붙이지 않는다.
ditnow_compose logs --tail 100 api web
ditnow_compose stop api web
# 이 프로젝트만 제거. DB는 이 Compose에 없고 volume/image 삭제 옵션도 쓰지 않는다.
ditnow_compose down
```

`docker system prune`, `docker container prune`, 전체 `docker stop`, 기존 MariaDB/Tunnel/8개 서비스의 down·삭제·daemon 재시작은 금지한다. 이 프로젝트 이름도 기존 사용 중이면 충돌 검토 전 실행하지 않는다. 롤백은 이전 승인 SHA/이미지 쌍과 외부 env를 소유자가 재확인하여 이 두 서비스만 교체한다. DB DROP·복원·seed·migration 재적용은 없다.

## 검증 범위

- 새 workflow는 Linux GitHub runner에서 **실제 Docker build + hostnetwork loopback public probe**를 실행한다. secret/Tailscale/DB/seed/LLM/운영 Tunnel 없음. CI 자체 프로젝트만 마지막에 정리한다.
- 1단계 bootstrap 함수는 README 표본 그대로 Linux unittest가 bash subprocess로 격리 임시 디렉터리·합성 값만 사용해 검사한다(기존 파일·CA·dangling symlink·errexit 비활성 문맥·원래 덮어쓰기 반례). Docker·실제 비밀 없음.
- 로컬 Docker daemon은 사용 불가로 local image build **NOT_RUN**. Windows Docker Desktop 설정/서비스를 변경하지 않았다. 단위 검증은 표준 라이브러리 mock으로 Docker/네트워크 동작 없이 실행한다.
- 현재 패키지 CI·독립 리뷰·최종 HEAD는 PR에 기록한다. 운영 배포·서버 소유자의 명령 실행·최종 외부 HTTPS·실DB/P0/LLM은 **NOT_RUN**이다. Root README/NAV·공통 App/API는 별도 소유자가 유지한다.

추가 공식 근거: [Nginx proxy URI 보존](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass), [Compose up pull 정책](https://docs.docker.com/reference/cli/docker/compose/up/). 문서·패키지 작성은 기존 서버를 변경하는 행위와 구분한다.
