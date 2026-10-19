"""크롤러 공통 부분: 공고 모델, HTTP 세션, 텍스트 유틸."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
TIMEOUT = 20
RETRIES = 2


@dataclass
class Job:
    site: str
    job_id: str
    title: str
    company: str
    url: str
    location: str = ""
    career: str = ""
    deadline: str = ""
    posted: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = clean(self.title)
        self.company = clean(self.company)
        self.posted = to_date(self.posted)
        self.tags = [t for t in (clean(t) for t in self.tags) if t]

    @property
    def key(self) -> str:
        return f"{self.site}:{self.job_id}"


class Crawler:
    """사이트별 크롤러의 베이스.

    search(keyword)는 해당 사이트에서 keyword로 검색한 최신 공고를 돌려준다.
    인스턴스는 수집 주기마다 새로 만들기 때문에 _cache는 한 주기 동안만 유효하다.
    """

    site = ""
    label = ""
    home = ""
    color = 0x5865F2  # 디스코드 embed 색
    delay = 1.0  # 같은 사이트에 연속 요청할 때 간격(초)

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        self._last_request = 0.0
        self._cache: dict[str, requests.Response] = {}

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            cache: bool = False) -> requests.Response:
        cache_key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        if cache and cache_key in self._cache:
            return self._cache[cache_key]
        for attempt in range(1, RETRIES + 2):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                res = self.session.get(url, params=params, headers=headers, timeout=TIMEOUT)
            finally:
                self._last_request = time.monotonic()
            # 요청 과다(429)·일시 오류(5xx)는 잠깐 쉬었다가 재시도
            retryable = res.status_code == 429 or res.status_code >= 500
            if not retryable or attempt > RETRIES:
                break
            retry_after = res.headers.get("Retry-After", "")
            time.sleep(min(float(retry_after) if retry_after.isdigit() else 10.0 * attempt, 60.0))
        res.raise_for_status()
        if cache:
            self._cache[cache_key] = res
        return res

    def search(self, keyword: str) -> list[Job]:
        raise NotImplementedError


# --------------------------------------------------------------------------
# 유틸
# --------------------------------------------------------------------------
_INVISIBLE = dict.fromkeys(map(ord, "﻿​‌‍⁠"))


def clean(text: str | None) -> str:
    """공백 정리 + BOM·제로폭 문자 제거."""
    return " ".join((text or "").translate(_INVISIBLE).split())


def text_of(el) -> str:
    return clean(el.get_text(" ", strip=True)) if el is not None else ""


def to_date(text: str | None) -> str:
    """사이트마다 다른 등록일 표기를 'YYYY-MM-DD'로. 해석이 안 되면 원문 그대로.

    '2026.10.01' / '2026-10-01T09:00' / '수정일 26/10/11' / '(5일전 등록)' / '3시간 전' / '어제'
    """
    t = clean(text)
    if not t:
        return ""
    today = datetime.now(KST).date()
    if m := re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", t):
        y, mo, d = map(int, m.groups())
    elif m := re.search(r"(?<!\d)(\d{2})/(\d{1,2})/(\d{1,2})(?!\d)", t):
        y, mo, d = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := re.search(r"(\d+)\s*일\s*전", t):
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    elif re.search(r"시간\s*전|분\s*전|방금|오늘", t):
        return today.isoformat()
    elif "어제" in t:
        return (today - timedelta(days=1)).isoformat()
    else:
        return t
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return t


_NORM_RE = re.compile(r"[\s/·・,.\-_()\[\]&+]+")


def norm(text: str) -> str:
    """키워드 비교용: 소문자 + 공백/구분 기호 제거. 'UI / UX' → 'uiux'"""
    return _NORM_RE.sub("", text or "").lower()


def next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("__NEXT_DATA__ 를 찾을 수 없음 (페이지 구조 변경?)")
    return json.loads(m.group(1))


def dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    out = []
    for j in jobs:
        if j.key not in seen:
            seen.add(j.key)
            out.append(j)
    return out
