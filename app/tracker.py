"""지원 현황 보드 데이터: 단계별 열, 다가오는 일정, 건수."""

from __future__ import annotations

from datetime import date

from . import config, db
from .crawlers import CRAWLERS

UPCOMING_DAYS = 14  # 이 기간 안의 일정을 '다가오는 일정'에 보여준다


def _to_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def site_label(site: str) -> str:
    if site == "manual":
        return "직접 추가"
    crawler = CRAWLERS.get(site)
    return crawler.label if crawler else site


def board() -> dict:
    today = config.now().date()
    apps = db.list_applications()
    for a in apps:
        applied = _to_date(a["applied_at"])
        nxt = _to_date(a["next_date"])
        a["days_since"] = (today - applied).days if applied else None
        a["d_day"] = (nxt - today).days if nxt else None
        a["site_label"] = site_label(a["site"])
        a["stage_label"] = db.STAGES.get(a["stage"], a["stage"])

    far = 10 ** 6
    columns = {stage: [a for a in apps if a["stage"] == stage] for stage in db.STAGES}
    # 접수: 최근 지원 먼저 / 진행중: 일정 가까운 것 먼저 / 결과: 최근 변경 먼저 (list_applications 기본 순서)
    columns["applied"].sort(key=lambda a: a["applied_at"], reverse=True)
    columns["progress"].sort(key=lambda a: a["d_day"] if a["d_day"] is not None and a["d_day"] >= 0 else far)

    upcoming = sorted(
        (a for a in apps
         if a["stage"] in ("applied", "progress") and a["d_day"] is not None and 0 <= a["d_day"] <= UPCOMING_DAYS),
        key=lambda a: a["d_day"],
    )

    return {
        "columns": columns,
        "upcoming": upcoming,
        "counts": {stage: len(items) for stage, items in columns.items()},
        "total": len(apps),
    }
