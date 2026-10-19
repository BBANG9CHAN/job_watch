"""수집 한 주기: 사이트별 검색 → 저장 → 규칙 매칭 → 디스코드 알림."""

from __future__ import annotations

import logging
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import config, db, notifier
from .crawlers import CRAWLERS, Crawler, Job
from .crawlers.base import norm

log = logging.getLogger("job_watch")

_lock = threading.Lock()
state = {"running": False, "last_started": "", "last_finished": "", "last_summary": "", "next_run": ""}


def _hit(term: str, text: str) -> bool:
    """term 이 text 에 들어 있는지. 대소문자·띄어쓰기·기호 무시.

    'UI' 같은 짧은 영문은 영어 단어 한가운데(Rec-ui-ter, B-ui-ld, L-ux-ury)에 묻힌 경우를 빼고 본다.
    'UIUX', 'GUI', 'UI/UX' 처럼 한쪽이라도 단어 경계면 인정.
    """
    t = norm(term)
    if not t:
        return False
    if t.isascii() and t.isalnum() and len(t) <= 3:
        low = text.lower()
        for m in re.finditer(re.escape(t), low):
            before = low[m.start() - 1] if m.start() else " "
            after = low[m.end()] if m.end() < len(low) else " "
            buried = before.isascii() and before.isalpha() and after.isascii() and after.isalpha()
            if not buried:
                return True
        return False
    return t in norm(text)


def matches(job: Job, include: list[str], exclude: list[str], use_tags: bool = False) -> bool:
    """제외 단어가 제목에 있으면 탈락. 포함 단어가 있으면 제목(use_tags면 직무 태그까지)에 하나는 있어야 통과.

    태그는 사이트가 붙인 직무 분류라 범위가 넓다(예: 사람인은 웹디자이너 공고에도 'UI/UX' 태그).
    그래서 기본은 제목만 본다.
    """
    if any(_hit(x, job.title) for x in exclude):
        return False
    if not include:
        return True
    texts = [job.title] + (job.tags if use_tags else [])
    return any(_hit(x, t) for x in include for t in texts)


def _crawl_site(crawler: Crawler, keywords: list[str]) -> tuple[dict[str, list[Job]], list[str]]:
    results: dict[str, list[Job]] = {}
    errors: list[str] = []
    for kw in keywords:
        try:
            results[kw] = crawler.search(kw)
        except Exception as e:  # 한 검색어가 실패해도 나머지는 계속
            errors.append(f"'{kw}': {type(e).__name__}: {e}")
            log.warning("[%s] '%s' 실패\n%s", crawler.site, kw, traceback.format_exc())
    return results, errors


def _in_quiet_hours(spec: str) -> bool:
    try:
        start, end = (int(x) for x in spec.split("-"))
    except ValueError:
        return False
    hour = config.now().hour
    return start <= hour < end if start <= end else (hour >= start or hour < end)


def run_cycle(trigger: str = "schedule") -> str | None:
    """한 주기를 실행하고 요약 문자열을 돌려준다. 이미 실행 중이면 None."""
    if not _lock.acquire(blocking=False):
        return None
    state.update(running=True, last_started=config.now_iso())
    try:
        summary = _run()
        state["last_summary"] = summary
        log.info("수집 완료 (%s): %s", trigger, summary)
        return summary
    except Exception:
        log.exception("수집 주기 오류")
        state["last_summary"] = "오류: 로그를 확인하세요"
        raise
    finally:
        state.update(running=False, last_finished=config.now_iso())
        _lock.release()


def _run() -> str:
    settings = db.get_settings()
    watches = db.list_watches(enabled_only=True)
    if not watches:
        return "활성화된 모니터링 규칙이 없습니다"

    # 사이트별로 필요한 검색어를 모은다 (여러 규칙이 같은 검색어를 쓰면 한 번만 요청)
    site_keywords: dict[str, list[str]] = {}
    for w in watches:
        for site in w["sites"] or list(CRAWLERS):
            if site in CRAWLERS:
                bucket = site_keywords.setdefault(site, [])
                bucket += [k for k in w["keywords"] if k not in bucket]

    results: dict[str, dict[str, list[Job]]] = {}
    failed_sites: set[str] = set()  # 모든 검색어 실패
    partial_sites: set[str] = set()  # 일부 검색어 실패
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {site: pool.submit(_crawl_site, CRAWLERS[site](), kws) for site, kws in site_keywords.items()}
        for site, fut in futures.items():
            by_kw, errors = fut.result()
            results[site] = by_kw
            fetched = len({j.key for jobs in by_kw.values() for j in jobs})
            if not by_kw:
                failed_sites.add(site)
            elif errors:
                partial_sites.add(site)
            db.record_site_run(site, ok=bool(by_kw), fetched=fetched, error=" / ".join(errors))

    all_jobs = {j.key: j for by_kw in results.values() for jobs in by_kw.values() for j in jobs}
    db.upsert_jobs(list(all_jobs.values()))

    webhook = settings.get("discord_webhook_url", "").strip()
    quiet = _in_quiet_hours(settings.get("quiet_hours", ""))
    public_url = settings.get("public_url", "").strip()

    total_new = 0
    total_dups = 0
    baseline_msgs = []
    for w in watches:
        done = db.baselined_sites(w["id"])
        first_time = not done  # 이 규칙의 진짜 첫 수집 (사이트 추가·부분 실패 재시도는 제외)
        baseline_count = 0
        for site in w["sites"] or list(CRAWLERS):
            if site not in results or site in failed_sites:
                continue
            jobs = {j.key: j for kw in w["keywords"] for j in results[site].get(kw, [])}
            is_baseline = site not in done
            for job in jobs.values():
                if not matches(job, w["include_terms"], w["exclude_terms"], w["match_tags"]):
                    continue
                silent = is_baseline or not w["notify"] or not webhook
                saved = db.add_match(w["id"], job, notified=2 if silent else 0)
                if saved is None:
                    continue
                if is_baseline:
                    baseline_count += 1
                elif saved == 2 and not silent:
                    total_dups += 1  # 다른 사이트에 이미 있던 같은 공고
                else:
                    total_new += 1
            # 일부 검색어가 실패했다면 다음 주기에 기준선을 다시 잡는다 (실패한 검색어 결과가 알림 폭탄이 되지 않게)
            if is_baseline and site not in partial_sites:
                db.mark_baselined(w["id"], site)
        if baseline_count and first_time:
            baseline_msgs.append(f"'{w['name']}' 기존 공고 {baseline_count}건")

        pending = db.pending_notifications(w["id"])
        if not pending:
            continue
        if not w["notify"]:
            db.set_notified(w["id"], [j["key"] for j in pending], 2)
        elif webhook and not quiet:
            try:
                notifier.send_jobs(webhook, w["name"], pending, public_url)
                db.set_notified(w["id"], [j["key"] for j in pending])
            except Exception as e:
                log.warning("디스코드 전송 실패 (다음 주기에 재시도): %s", e)

    if not webhook:
        db.silence_pending()
    if webhook and baseline_msgs:
        try:
            notifier.send_text(
                webhook,
                "📥 첫 수집 완료 — " + ", ".join(baseline_msgs)
                + "을 저장했어요. 이제부터 새로 올라오는 공고만 알려드릴게요."
                + (f"\n{public_url}" if public_url else ""),
            )
        except Exception as e:
            log.warning("디스코드 전송 실패: %s", e)

    parts = [f"사이트 {len(results) - len(failed_sites)}/{len(results)} 성공", f"공고 {len(all_jobs)}건 확인",
             f"신규 매칭 {total_new}건" + (f" (다른 사이트 중복 {total_dups}건 제외)" if total_dups else "")]
    if baseline_msgs:
        parts.append("첫 수집: " + ", ".join(baseline_msgs))
    if quiet and total_new:
        parts.append("방해금지 시간이라 알림 보류")
    return " · ".join(parts)
