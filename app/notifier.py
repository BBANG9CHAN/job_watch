"""디스코드 웹훅 알림.

- send_jobs   새 공고 알림: 카드 하나에 사이트별로 묶은 목록 (공고당 2줄)
- send_digest 모아둔 공고 정리본: 사이트별 카드, 공고당 1줄
"""

from __future__ import annotations

import re
import time

import requests

from .config import now
from .crawlers import CRAWLERS

MAX_EMBEDS_PER_MESSAGE = 10  # 디스코드 제한
EMBED_DESC_LIMIT = 4000  # 디스코드 제한 4096
MESSAGE_CHAR_LIMIT = 5800  # 메시지 하나의 embed 글자 합 제한 6000
NOTIFY_MAX_JOBS = 50  # 새 공고 알림 한 번에 보여줄 최대 개수 (나머지는 대시보드로)
DIGEST_MAX_ITEMS = 300
BRAND_COLOR = 0x6366F1


class NotifyError(Exception):
    pass


def _post(webhook: str, payload: dict) -> None:
    for _ in range(4):
        res = requests.post(webhook, json=payload, timeout=15)
        if res.status_code == 429:  # rate limit — 디스코드가 알려준 만큼 기다렸다 재시도
            try:
                retry = float(res.json().get("retry_after", 1))
            except ValueError:
                retry = 2.0
            time.sleep(min(retry, 30) + 0.5)
            continue
        if not res.ok:
            raise NotifyError(f"discord {res.status_code}: {res.text[:200]}")
        return
    raise NotifyError("discord rate limit 재시도 초과")


def send_text(webhook: str, text: str) -> None:
    _post(webhook, {"content": text[:1900]})


# --------------------------------------------------------------------------
# 마크다운 정리
# --------------------------------------------------------------------------
def _escape(text: str) -> str:
    """디스코드 마크다운으로 해석될 수 있는 기호만 이스케이프. '~ 11/10' 같은 단독 물결은 그대로 둔다."""
    text = re.sub(r"([*_`\\])", r"\\\1", text)
    return text.replace("~~", r"\~\~").replace("||", r"\|\|")


def _plain(text: str) -> str:
    return _escape(text).replace("[", r"\[").replace("]", r"\]")


def _link(title: str, url: str, max_len: int) -> str:
    """마스크 링크 [제목](url). 짝이 안 맞는 대괄호는 링크가 깨지므로 전각으로 바꾼다."""
    if len(title) > max_len:
        title = title[:max_len - 1] + "…"
    depth, balanced = 0, True
    for ch in title:
        if ch == "[":
            depth += 1
            balanced &= depth == 1
        elif ch == "]":
            depth -= 1
            balanced &= depth == 0
    if not balanced or depth:
        title = title.replace("[", "［").replace("]", "］")
    url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    return f"[{_escape(title)}]({url})"


def _by_site(jobs: list[dict]) -> list[tuple[str, int, list[dict]]]:
    """(사이트 이름, 색, 공고들) — 사이트 등록 순서대로."""
    groups: dict[str, list[dict]] = {}
    for j in jobs:
        groups.setdefault(j["site"], []).append(j)
    order = [s for s in CRAWLERS if s in groups] + [s for s in groups if s not in CRAWLERS]
    out = []
    for site in order:
        crawler = CRAWLERS.get(site)
        out.append((crawler.label if crawler else site, crawler.color if crawler else BRAND_COLOR, groups[site]))
    return out


def _chunk(entries: list[str], limit: int = EMBED_DESC_LIMIT) -> list[str]:
    """줄 묶음(entries)을 embed 설명 길이 제한에 맞춰 나눈다. entry 하나는 쪼개지 않는다."""
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for e in entries:
        if cur and size + len(e) + 1 > limit:
            chunks.append("\n".join(cur).strip())
            cur, size = [], 0
        cur.append(e)
        size += len(e) + 1
    if cur:
        chunks.append("\n".join(cur).strip())
    return chunks


def _send_embeds(webhook: str, content: str, embeds: list[dict]) -> int:
    """embed 들을 메시지 단위로 묶어 보낸다 (메시지당 10개·글자 합 6000 제한). 보낸 메시지 수."""
    messages: list[list[dict]] = [[]]
    size = 0
    for e in embeds:
        e_size = sum(len(e.get(k, "")) for k in ("title", "description")) + len((e.get("footer") or {}).get("text", ""))
        if messages[-1] and (len(messages[-1]) >= MAX_EMBEDS_PER_MESSAGE or size + e_size > MESSAGE_CHAR_LIMIT):
            messages.append([])
            size = 0
        messages[-1].append(e)
        size += e_size
    for i, chunk in enumerate(messages):
        payload: dict = {"embeds": chunk}
        if i == 0:
            payload["content"] = content
        if i:
            time.sleep(0.4)  # 웹훅 속도 제한 여유
        _post(webhook, payload)
    return len(messages)


def _tail(rest: int, public_url: str) -> str:
    lines = []
    if rest > 0:
        lines.append(f"…외 {rest}건은 대시보드에서 확인하세요.")
    if public_url:
        lines.append(f"[📋 대시보드 열기]({public_url})")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 새 공고 알림
# --------------------------------------------------------------------------
def _job_entry(job: dict) -> str:
    """[제목](링크)
    └ 회사 · 지역 · 경력 · ⏰ 마감"""
    details = [job.get(k) or "" for k in ("company", "location", "career")]
    details = [_plain(d) for d in details if d]
    if job.get("deadline"):
        details.append(f"⏰ {_plain(job['deadline'])}")
    line = _link(job["title"] or "(제목 없음)", job["url"], 90)
    return line + (f"\n└ {' · '.join(details)}" if details else "")


def send_jobs(webhook: str, watch_name: str, jobs: list[dict], public_url: str = "") -> None:
    if not jobs:
        return
    shown = jobs[:NOTIFY_MAX_JOBS]
    entries: list[str] = []
    for label, _color, group in _by_site(shown):
        for i, job in enumerate(group):
            entry = _job_entry(job)
            if i == 0:  # 사이트 머리글은 첫 공고에 붙여서 머리글만 따로 떨어지지 않게
                entry = f"\n**{label}** · {len(group)}건\n{entry}"
            entries.append(entry)
    tail = _tail(len(jobs) - len(shown), public_url)
    if tail:
        entries.append("\n" + tail)

    chunks = _chunk(entries)
    embeds = [{"description": c, "color": BRAND_COLOR} for c in chunks]
    embeds[-1]["footer"] = {"text": f"Job Watch · {watch_name} · {now().strftime('%m/%d %H:%M')}"}
    _send_embeds(webhook, f"🔔 **{watch_name}** 새 공고 {len(jobs)}건", embeds)


# --------------------------------------------------------------------------
# 정리본 내보내기: 사이트별 카드, 한 줄씩
# --------------------------------------------------------------------------
def _digest_line(job: dict) -> str:
    parts = [_plain(job["company"][:25])] if job.get("company") else []
    if re.search(r"\d", job.get("deadline") or ""):
        parts.append(f"⏰ {_plain(job['deadline'])}")
    star = "⭐ " if job.get("status") == "star" else ""
    return f"{star}{_link(job['title'], job['url'], 70)}" + (" — " + " · ".join(parts) if parts else "")


def send_digest(webhook: str, heading: str, jobs: list[dict], public_url: str = "") -> int:
    """공고 목록을 사이트별 embed 로 정리해서 보낸다. 보낸 메시지 수를 돌려준다."""
    if not jobs:
        return 0
    shown = jobs[:DIGEST_MAX_ITEMS]
    embeds: list[dict] = []
    for label, color, group in _by_site(shown):
        chunks = _chunk([_digest_line(j) for j in group])
        for n, desc in enumerate(chunks, 1):
            title = f"{label} · {len(group)}건" + (f" ({n})" if n > 1 else "")
            embeds.append({"title": title, "description": desc, "color": color})
    tail = _tail(len(jobs) - len(shown), public_url)
    if tail:
        embeds.append({"description": tail, "color": BRAND_COLOR})
    return _send_embeds(webhook, f"📋 **{heading}** — {len(jobs)}건", embeds)
