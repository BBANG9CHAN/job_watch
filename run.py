"""job_watch 실행 진입점.

  python run.py                       웹 서버 + 주기 수집 시작 (기본)
  python run.py check [사이트] [검색어]  크롤러 동작 확인 (저장·알림 없음)
  python run.py once                  수집 한 번만 실행 (저장·알림 포함)
"""

from __future__ import annotations

import logging
import sys

from app import config


def _setup_logging() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.DATA_DIR / "job_watch.log", encoding="utf-8"),
        ],
    )


def check(site: str | None, keyword: str) -> int:
    from app.crawlers import CRAWLERS

    sites = [site] if site else list(CRAWLERS)
    failed = 0
    for name in sites:
        if name not in CRAWLERS:
            print(f"알 수 없는 사이트: {name}  (가능: {', '.join(CRAWLERS)})")
            return 2
        crawler = CRAWLERS[name]()
        try:
            jobs = crawler.search(keyword)
        except Exception as e:
            failed += 1
            print(f"✗ {crawler.label:10} 실패: {type(e).__name__}: {e}")
            continue
        mark = "✓" if jobs else "△"
        print(f"{mark} {crawler.label:10} {len(jobs):3}건")
        for j in jobs[:3]:
            extra = " | ".join(x for x in (j.location, j.career, j.deadline) if x)
            print(f"    - {j.title[:50]}  @ {j.company[:20]}  ({extra})")
            print(f"      {j.url}")
    return 1 if failed else 0


def main() -> int:
    if sys.stdout is None or sys.stderr is None:  # pythonw(창 없이 실행)에는 콘솔이 없다
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        console = open(config.DATA_DIR / "console.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or console
        sys.stderr = sys.stderr or console
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"

    if cmd == "check":
        site = args[1] if len(args) > 1 and args[1] != "all" else None
        keyword = args[2] if len(args) > 2 else "UX"
        return check(site, keyword)

    _setup_logging()
    from app import db

    db.init()
    if cmd == "once":
        from app import monitor

        print(monitor.run_cycle(trigger="cli"))
        return 0
    if cmd == "serve":
        import uvicorn

        if config.HOST not in ("127.0.0.1", "localhost") and not config.APP_PASSWORD:
            logging.warning("HOST=%s 로 외부 접속을 허용하는데 APP_PASSWORD 가 비어 있습니다!", config.HOST)
        uvicorn.run("app.web:app", host=config.HOST, port=config.PORT, log_level="warning")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
