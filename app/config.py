"""실행 환경 설정. 프로젝트 루트의 .env 파일 → 환경변수 순으로 읽는다.

웹에서 바꿀 수 있는 값(디스코드 웹훅, 수집 주기 등)은 DB settings 테이블에 저장되고,
여기 값은 그 초기값으로만 쓰인다.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KST = timezone(timedelta(hours=9))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
# 설정하면 웹페이지 접속 시 비밀번호를 묻는다. 외부에서 접속하게 열어둘 거라면 반드시 설정.
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "jobs.db")))

DEFAULT_SETTINGS = {
    "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
    "interval_minutes": os.getenv("CRAWL_INTERVAL_MINUTES", "60"),
    # 디스코드 메시지에 붙일 대시보드 주소 (외부 접속 주소가 있으면 그걸로)
    "public_url": os.getenv("PUBLIC_URL", ""),
    # 이 시간대(시)에는 디스코드 알림을 보류했다가 다음 수집 때 보낸다. 예: "0-8" → 0시~7시59분
    "quiet_hours": os.getenv("QUIET_HOURS", ""),
}


def now() -> datetime:
    return datetime.now(KST)


def now_iso() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def secret_key() -> bytes:
    """로그인 쿠키 서명용 키. 처음 실행 시 data/secret.key 로 생성."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()
