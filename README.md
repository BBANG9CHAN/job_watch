# 🔭 Job Watch

여러 채용 사이트를 주기적으로 검색해서, 내가 정한 직무 조건에 맞는 **새 공고**를
디스코드로 알려주고 웹 대시보드로 모아 보여주는 개인용 서비스입니다.

- 사이트 9곳 동시 수집 (1회 약 20초)
- 규칙(검색어 + 포함/제외 단어)을 웹에서 추가·수정
- 처음 수집분은 조용히 저장하고, 이후 **새로 올라온 공고만** 디스코드 알림
- 같은 공고가 여러 사이트에 올라오면 한 번만 알림, 대시보드에서도 하나로 묶어 표시
- 관심(★) / 지원함(✓) / 숨김(✕) 표시, 기간·사이트·검색 필터
- 방해금지 시간, 비밀번호 보호, 휴대폰 화면 대응

## 지원 사이트

| 사이트 | 수집 방식 | 비고 |
|---|---|---|
| 사람인 | 검색 결과 HTML | 본문까지 검색돼 결과가 넓음 → 포함 단어 필수 |
| 잡코리아 | 검색 결과 HTML | |
| 고용24 (구 워크넷) | 상세검색 HTML | 잡코리아 등 연계 공고 포함 (중복은 자동 정리) |
| 인크루트 | 검색 결과 HTML | |
| 원티드 | 검색 JSON API | |
| 링크드인 | 비로그인 검색 | 대한민국·최근 1주. 요청이 잦으면 일시 차단(429)될 수 있음 |
| 자소설닷컴 | 검색 페이지 데이터 | 키워드 검색이 없어 직무 분류에 대응시켜 수집 |
| 그룹바이 | 공고 페이지 데이터 | 키워드 검색이 없어 직무 분류에 대응시켜 수집 |
| 디자이너잡 | 상세검색 HTML | |
| ~~잡플래닛~~ | – | Cloudflare 봇 차단이 걸려 있어 제외. 공고 대부분이 잡코리아 연동이라 잡코리아로 커버됨 |

## 실행

```bat
start.bat
```

처음 실행 시 가상환경(`.venv`)을 만들고 패키지를 설치한 뒤 서버를 띄웁니다.
브라우저에서 <http://127.0.0.1:8000> 으로 접속하세요. 서버가 뜨고 5초 뒤 첫 수집이 시작됩니다.

| 파일 | 용도 |
|---|---|
| `start.bat` | 콘솔 창에서 실행 (창 닫으면 종료) |
| `start_hidden.vbs` | 창 없이 백그라운드 실행 |
| `stop.bat` | 백그라운드 실행 종료 |
| `start.sh` | macOS / Linux 실행 |
| `Dockerfile`, `docker-compose.yml` | 서버·NAS에서 Docker로 실행 |

다른 PC나 서버에서 돌리려면 아래 [다른 컴퓨터·서버로 옮기기](#다른-컴퓨터서버로-옮기기)를 보세요.

**윈도우 켤 때 자동 실행:** `Win + R` → `shell:startup` → 열린 폴더에 `start_hidden.vbs` 바로가기를 넣으면 됩니다.

> PC가 절전 모드에 들어가면 수집도 멈춥니다. 계속 받으려면 *설정 → 시스템 → 전원* 에서 절전 시간을 '안 함'으로 두세요.

## 디스코드 알림 연결

1. 디스코드 채널 설정(⚙) → **연동** → **웹후크** → **새 웹후크** → **웹후크 URL 복사**
2. 대시보드 **설정** 화면에 붙여넣고 저장 → **테스트 메시지 보내기**

알림은 공고별 카드(제목·회사·지역·경력·마감·사이트)로 오고, 제목을 누르면 공고 원문으로 이동합니다.

## 모니터링 규칙

**모니터링** 화면에서 규칙을 여러 개 만들 수 있습니다 (예: 'UX/UI 디자인', 'BX 디자인').

| 항목 | 설명 |
|---|---|
| 검색어 | 각 사이트 검색창에 넣는 단어. 여러 개면 각각 검색해 합침 |
| 포함 단어 | **제목**에 이 중 하나라도 있어야 통과 (비우면 검색 결과 전부) |
| 제외 단어 | 제목에 하나라도 있으면 버림 |
| 직무 태그에서도 찾기 | 켜면 사이트가 붙인 직무 분류 태그까지 검사 (더 많이 잡히지만 노이즈 증가) |
| 사이트 | 이 규칙을 적용할 사이트 |

- 비교할 때 대소문자·띄어쓰기·기호는 무시합니다. `프로덕트 디자` 는 `프로덕트디자이너` 에도 걸립니다.
- `UI` 같은 짧은 영문은 영어 단어 속(Rec**ui**ter, B**ui**lding)에 묻힌 경우는 무시합니다.
- 검색어를 바꾸면 그 규칙은 다시 '첫 수집'으로 취급돼서 알림 폭탄이 오지 않습니다.

## 다른 인터넷망(휴대폰 LTE 등)에서 접속하기

디스코드 알림은 어디서든 오고, 알림의 링크는 각 채용 사이트로 바로 가기 때문에 대시보드 접속 없이도 쓸 수 있습니다.
대시보드까지 밖에서 보고 싶다면 아래 중 하나를 고르세요.

### 방법 1. Tailscale (추천 — 내 기기에서만 접속, 가장 안전)

인터넷에 공개하지 않고, 같은 Tailscale 계정에 로그인한 내 기기끼리만 연결하는 무료 VPN입니다.

1. PC와 휴대폰에 [Tailscale](https://tailscale.com/download) 설치 후 같은 계정으로 로그인
2. PC의 PowerShell에서: `tailscale serve --bg 8000`
   (처음이면 HTTPS 인증서 사용을 허용하라는 링크가 나옵니다 — 열어서 허용 후 다시 실행)
3. 출력되는 `https://<PC이름>.<tailnet>.ts.net` 주소로 휴대폰에서 접속
4. 그 주소를 대시보드 **설정 → 대시보드 외부 주소**에 넣으면 디스코드 메시지에도 링크가 붙습니다

`.env` 의 `HOST=127.0.0.1` 그대로 두면 됩니다.

### 방법 2. Cloudflare Tunnel (공개 URL — 앱 설치 없이 아무 브라우저에서)

1. **먼저 `.env` 에 `APP_PASSWORD=원하는비밀번호` 설정 후 서버 재시작** (공개 주소라 필수)
2. [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 설치
3. `cloudflared tunnel --url http://localhost:8000` → `https://xxxx.trycloudflare.com` 주소 발급

빠른 터널 주소는 cloudflared를 다시 켤 때마다 바뀝니다. 고정 주소가 필요하면 Cloudflare에 도메인을 연결하고
이름 있는 터널(named tunnel)을 만드세요.

> 공유기 포트포워딩으로 직접 여는 방법은 권하지 않습니다 (집 IP 노출, 보안 위험).

## 다른 컴퓨터·서버로 옮기기

코드는 윈도우·맥·리눅스 어디서나 동작합니다 (Python 3.10 이상). 시간은 항상 한국 시간으로 처리하니 서버 시간대는 상관없습니다.

### 옮길 것

| 항목 | 필요 여부 |
|---|---|
| 프로젝트 폴더 (`.venv` 제외) | 필수. `.venv` 는 기기마다 새로 만들어지니 복사하지 마세요 |
| `.env` | 비밀번호 등을 설정했다면 |
| `data/` 폴더 | 지금까지 모은 공고·관심 표시·디스코드 웹훅 설정을 유지하려면. 빼고 옮기면 새로 시작(첫 수집부터) |

**옛 PC에서는 꼭 종료하세요.** 두 곳에서 동시에 돌면 같은 알림이 두 번 옵니다.

### 실행

- **윈도우 PC:** [Python](https://www.python.org/downloads/) 설치 (설치 화면에서 *Add python.exe to PATH* 체크) → `start.bat`
- **맥 / 리눅스:** `bash start.sh`
- **Docker (NAS·서버):** `cp .env.example .env` → `docker compose up -d --build` → 로그는 `docker compose logs -f`

### 리눅스 서버에서 상시 실행 (systemd)

`bash start.sh` 를 한 번 실행해 설치가 끝나면 `Ctrl+C` 로 끄고, 아래 내용을 `/etc/systemd/system/job-watch.service` 로 저장합니다
(`ubuntu` 와 경로는 본인 환경에 맞게).

```ini
[Unit]
Description=Job Watch
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/job_watch
ExecStart=/home/ubuntu/job_watch/.venv/bin/python run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now job-watch     # 시작 + 부팅 시 자동 실행
sudo systemctl status job-watch
```

### 어디서 돌리면 좋을까

메모리 200MB 정도면 충분해서 작은 기기로도 됩니다.

| 장소 | 장점 | 주의 |
|---|---|---|
| 집의 남는 PC·노트북·라즈베리파이·NAS | 한국 가정용 IP라 사이트 차단 걱정이 거의 없음 | 전기·절전 설정 |
| Oracle Cloud 무료 서버 (홈 리전을 **서울·춘천**으로) | 무료, 24시간 | 가입 시 고른 홈 리전은 못 바꿈. 무료 서버 재고가 없을 때가 있음 |
| AWS Lightsail 등 **서울 리전** 유료 서버 | 안정적 | 월 몇 달러 |

> **해외 리전·데이터센터 IP는 일부 사이트(특히 링크드인, 공공기관 사이트)가 막을 수 있습니다.**
> 옮긴 뒤에는 먼저 `python run.py check` 로 9개 사이트가 모두 ✓ 인지 확인하세요.

서버에서도 외부 접속은 **Tailscale**(서버에 설치 → `tailscale serve --bg 8000`)이 가장 간단하고 안전합니다.
서버의 8000 포트를 인터넷에 그대로 열면 비밀번호가 암호화 없이 오가므로 권하지 않습니다.

## 문제 해결

**설정** 화면의 *사이트별 수집 상태*에서 실패한 사이트를 확인할 수 있습니다. 사이트 구조가 바뀌면 해당 크롤러만 고치면 됩니다.

```bat
.venv\Scripts\python.exe run.py check                  :: 전체 사이트, 검색어 "UX"
.venv\Scripts\python.exe run.py check saramin "UI 디자이너"
.venv\Scripts\python.exe run.py once                   :: 수집 한 번 실행 (저장·알림 포함)
```

(맥·리눅스에서는 `.venv/bin/python run.py check`)

로그: `data\job_watch.log`

## 구조

```
run.py                 진입점 (serve / check / once)
app/
  config.py            .env 로딩, 경로, 기본 설정
  db.py                SQLite (규칙, 공고, 매칭, 사이트 상태, 설정)
  monitor.py           수집 한 주기: 검색 → 저장 → 매칭 → 알림
  scheduler.py         백그라운드 주기 실행
  notifier.py          디스코드 웹훅
  web.py               FastAPI 대시보드
  crawlers/            사이트별 크롤러 (Crawler.search(keyword) → [Job])
  templates/ static/   화면
data/                  DB·로그 (자동 생성, git 제외)
```

**새 사이트 추가:** `app/crawlers/` 에 `Crawler` 를 상속한 클래스를 만들고 `search()` 를 구현한 뒤
`app/crawlers/__init__.py` 의 `CRAWLERS` 에 넣으면 됩니다.

## 주의

개인적인 구직 용도로, 사이트에 부담을 주지 않는 선에서 쓰세요. 기본 수집 주기는 60분, 최소 10분이며
같은 사이트에 연속으로 요청할 때는 1~5초 간격을 둡니다. 각 사이트의 이용약관상 자동 수집이 제한될 수 있습니다.
