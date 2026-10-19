"""대시보드 목록 조회(필터·중복 묶기)와 디스코드 정리본 내보내기. 웹과 CLI가 같이 쓴다."""

from __future__ import annotations

from datetime import timedelta

from . import config, db, notifier
from .crawlers import CRAWLERS

DAY_LABELS = {1: "오늘", 3: "최근 3일", 7: "최근 7일", 30: "최근 30일"}
STATUS_LABELS = {"star": "관심", "applied": "지원함", "hidden": "숨긴 공고", "all": "숨김 포함"}


def group_duplicates(rows: list[dict]) -> list[dict]:
    """같은 지문의 다른 사이트 공고는 하나로 묶고 나머지는 others 로.
    같은 사이트의 동명 공고는 별개 공고로 둔다."""
    groups: dict[str, dict] = {}
    items: list[dict] = []
    for r in rows:
        r["others"] = []
        head = groups.get(r["fingerprint"]) if r["fingerprint"] else None
        if head and r["site"] not in {head["site"], *(o["site"] for o in head["others"])}:
            head["others"].append(r)
            continue
        groups.setdefault(r["fingerprint"], r)
        items.append(r)
    # 묶인 공고 중 하나라도 지원 기록이 있으면 카드에 그 단계를 보여준다
    for it in items:
        holder = next((x for x in (it, *it["others"]) if x.get("app_stage")), None)
        it["app_key"] = holder["key"] if holder else it["key"]
        if holder:
            it["app_stage"], it["app_step"] = holder["app_stage"], holder["app_step"]
    return items


def filtered_jobs(watch: int = 0, site: str = "", status: str = "", days: int = 0, q: str = "") -> list[dict]:
    since = (config.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") if days else ""
    if days == 1:  # '오늘' = 오늘 0시부터
        since = config.now().strftime("%Y-%m-%d 00:00:00")
    rows = db.query_jobs(watch_id=watch or None, site=site, status=status, since=since, text=q.strip())
    return group_duplicates(rows)


def heading(watch: int = 0, site: str = "", status: str = "", days: int = 0, q: str = "") -> str:
    parts = []
    if watch:
        w = db.get_watch(watch)
        parts.append(w["name"] if w else "삭제된 규칙")
    if site in CRAWLERS:
        parts.append(CRAWLERS[site].label)
    if days in DAY_LABELS:
        parts.append(DAY_LABELS[days])
    if status in STATUS_LABELS:
        parts.append(STATUS_LABELS[status])
    if q.strip():
        parts.append(f"'{q.strip()}' 검색")
    date = config.now().strftime("%m/%d %H:%M")
    return f"채용공고 정리 ({date})" + (f" · {' · '.join(parts)}" if parts else "")


def send_to_discord(watch: int = 0, site: str = "", status: str = "", days: int = 0, q: str = "") -> tuple[int, int]:
    """필터에 맞는 공고를 디스코드로 정리해 보낸다. (공고 수, 보낸 메시지 수)"""
    settings = db.get_settings()
    webhook = settings.get("discord_webhook_url", "").strip()
    if not webhook:
        raise ValueError("디스코드 웹훅 주소가 없습니다. 설정 화면에서 먼저 저장하세요.")
    jobs = filtered_jobs(watch, site, status, days, q)
    if not jobs:
        raise ValueError("보낼 공고가 없습니다.")
    sent = notifier.send_digest(webhook, heading(watch, site, status, days, q), jobs,
                                settings.get("public_url", "").strip())
    return len(jobs), sent
