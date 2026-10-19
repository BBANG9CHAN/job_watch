"""SQLite 저장소.

테이블
  watches       모니터링 규칙 (검색어 / 포함·제외 단어 / 대상 사이트)
  jobs          수집한 공고 (사이트:공고ID 단위). status = '' | star | hidden
                직접 추가한 지원 건은 site='manual' 로 들어간다
  matches       규칙 ↔ 공고 매칭. notified = 0 알림대기, 1 전송됨, 2 조용히 저장(기준선·중복·알림꺼짐)
  baselines     규칙×사이트별 첫 수집 완료 여부 (첫 수집분은 알림 없이 저장만)
  site_runs     사이트별 마지막 수집 결과
  settings      웹에서 바꾸는 설정값
  applications  지원 현황. stage = applied(접수) | progress(진행중) | offer(합격) | rejected(불합격)
  app_events    지원 단계가 바뀐 기록 (타임라인)
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config
from .crawlers import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    keywords      TEXT NOT NULL DEFAULT '[]',
    include_terms TEXT NOT NULL DEFAULT '[]',
    exclude_terms TEXT NOT NULL DEFAULT '[]',
    sites         TEXT NOT NULL DEFAULT '[]',
    match_tags    INTEGER NOT NULL DEFAULT 0,
    notify        INTEGER NOT NULL DEFAULT 1,
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    key         TEXT PRIMARY KEY,
    site        TEXT NOT NULL,
    job_id      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    career      TEXT NOT NULL DEFAULT '',
    deadline    TEXT NOT NULL DEFAULT '',
    posted      TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    fingerprint TEXT NOT NULL DEFAULT '',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE TABLE IF NOT EXISTS matches (
    watch_id   INTEGER NOT NULL,
    job_key    TEXT NOT NULL,
    matched_at TEXT NOT NULL,
    notified   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (watch_id, job_key)
);
CREATE INDEX IF NOT EXISTS idx_matches_pending ON matches(notified);
CREATE TABLE IF NOT EXISTS baselines (
    watch_id INTEGER NOT NULL,
    site     TEXT NOT NULL,
    PRIMARY KEY (watch_id, site)
);
CREATE TABLE IF NOT EXISTS site_runs (
    site        TEXT PRIMARY KEY,
    finished_at TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    fetched     INTEGER NOT NULL DEFAULT 0,
    error       TEXT NOT NULL DEFAULT '',
    last_ok_at  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    job_key    TEXT PRIMARY KEY,
    stage      TEXT NOT NULL DEFAULT 'applied',
    step       TEXT NOT NULL DEFAULT '',
    applied_at TEXT NOT NULL DEFAULT '',
    next_date  TEXT NOT NULL DEFAULT '',
    memo       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL,
    at      TEXT NOT NULL,
    stage   TEXT NOT NULL,
    step    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_app_events_key ON app_events(job_key);
"""

STAGES = {"applied": "접수", "progress": "진행중", "offer": "합격", "rejected": "불합격"}

DEFAULT_WATCH = {
    "name": "UX/UI 디자인",
    "keywords": ["UX", "UI 디자이너", "프로덕트 디자이너", "UX/UI"],
    "include_terms": ["UX", "UI", "프로덕트 디자", "Product Design", "사용자 경험"],
    "exclude_terms": ["개발자", "엔지니어", "Engineer", "Developer", "퍼블리셔"],
    "sites": [],
}

# 기존 DB에 나중에 추가된 컬럼: (테이블, 컬럼, 정의)
MIGRATIONS = [
    ("watches", "match_tags", "INTEGER NOT NULL DEFAULT 0"),
]


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        for table, column, ddl in MIGRATIONS:
            cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        for key, value in config.DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        # 예전 버전의 '✓ 지원함' 표시(jobs.status='applied')를 지원 현황으로 옮긴다
        ts = config.now_iso()
        for row in c.execute("SELECT key FROM jobs WHERE status = 'applied'").fetchall():
            if c.execute("INSERT OR IGNORE INTO applications(job_key, stage, applied_at, created_at, updated_at)"
                         " VALUES (?, 'applied', ?, ?, ?)", (row["key"], ts[:10], ts, ts)).rowcount:
                c.execute("INSERT INTO app_events(job_key, at, stage) VALUES (?, ?, 'applied')", (row["key"], ts))
        c.execute("UPDATE jobs SET status = '' WHERE status = 'applied'")
        if c.execute("SELECT COUNT(*) FROM watches").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO watches(name, keywords, include_terms, exclude_terms, sites, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    DEFAULT_WATCH["name"],
                    _dump(DEFAULT_WATCH["keywords"]),
                    _dump(DEFAULT_WATCH["include_terms"]),
                    _dump(DEFAULT_WATCH["exclude_terms"]),
                    _dump(DEFAULT_WATCH["sites"]),
                    config.now_iso(),
                ),
            )


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------
def get_settings() -> dict[str, str]:
    with connect() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}


def set_settings(values: dict[str, str]) -> None:
    with connect() as c:
        c.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(values.items()),
        )


# --------------------------------------------------------------------------
# watches
# --------------------------------------------------------------------------
def _watch(row: sqlite3.Row) -> dict:
    w = dict(row)
    for k in ("keywords", "include_terms", "exclude_terms", "sites"):
        w[k] = json.loads(w[k])
    for k in ("match_tags", "notify", "enabled"):
        w[k] = bool(w[k])
    return w


def list_watches(enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM watches" + (" WHERE enabled = 1" if enabled_only else "") + " ORDER BY id"
    with connect() as c:
        return [_watch(r) for r in c.execute(sql)]


def get_watch(watch_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
    return _watch(row) if row else None


def save_watch(data: dict, watch_id: int | None = None) -> int:
    fields = (
        data["name"],
        _dump(data["keywords"]),
        _dump(data["include_terms"]),
        _dump(data["exclude_terms"]),
        _dump(data["sites"]),
        int(data["match_tags"]),
        int(data["notify"]),
        int(data["enabled"]),
    )
    with connect() as c:
        if watch_id is None:
            cur = c.execute(
                "INSERT INTO watches(name, keywords, include_terms, exclude_terms, sites, match_tags, notify, enabled,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*fields, config.now_iso()),
            )
            return cur.lastrowid
        old = c.execute("SELECT keywords FROM watches WHERE id = ?", (watch_id,)).fetchone()
        c.execute(
            "UPDATE watches SET name=?, keywords=?, include_terms=?, exclude_terms=?, sites=?, match_tags=?, notify=?,"
            " enabled=? WHERE id = ?",
            (*fields, watch_id),
        )
        # 검색어가 바뀌면 새 검색 결과가 한꺼번에 알림으로 가지 않게 기준선을 다시 잡는다.
        if old and json.loads(old["keywords"]) != data["keywords"]:
            c.execute("DELETE FROM baselines WHERE watch_id = ?", (watch_id,))
        return watch_id


def delete_watch(watch_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
        c.execute("DELETE FROM matches WHERE watch_id = ?", (watch_id,))
        c.execute("DELETE FROM baselines WHERE watch_id = ?", (watch_id,))


def baselined_sites(watch_id: int) -> set[str]:
    with connect() as c:
        return {r["site"] for r in c.execute("SELECT site FROM baselines WHERE watch_id = ?", (watch_id,))}


def mark_baselined(watch_id: int, site: str) -> None:
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO baselines(watch_id, site) VALUES (?, ?)", (watch_id, site))


# --------------------------------------------------------------------------
# jobs / matches
# --------------------------------------------------------------------------
_COMPANY_NOISE = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사|\(재\)|재단법인|\s+")
_TITLE_NOISE = re.compile(r"[\s\[\](){}<>/·・,.\-_~!|:]+")


def fingerprint(job: Job) -> str:
    """사이트가 달라도 같은 공고인지 판단하는 지문: 정규화한 회사명 + 제목."""
    company = _COMPANY_NOISE.sub("", job.company).lower()
    title = _TITLE_NOISE.sub("", job.title).lower()
    return f"{company}|{title}"


def upsert_jobs(jobs: list[Job]) -> None:
    ts = config.now_iso()
    with connect() as c:
        for j in jobs:
            c.execute(
                """
                INSERT INTO jobs(key, site, job_id, title, company, url, location, career, deadline, posted,
                                 tags, fingerprint, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    title=excluded.title, company=excluded.company, url=excluded.url,
                    location=excluded.location, career=excluded.career, deadline=excluded.deadline,
                    posted=excluded.posted, tags=excluded.tags, last_seen=excluded.last_seen
                """,
                (j.key, j.site, j.job_id, j.title, j.company, j.url, j.location, j.career, j.deadline,
                 j.posted, _dump(j.tags), fingerprint(j), ts, ts),
            )


def add_match(watch_id: int, job: Job, notified: int) -> int | None:
    """매칭을 기록하고 실제로 저장한 notified 값을 돌려준다. 이미 있던 매칭이면 None.

    알림 대기(0)로 넣으려는데 같은 규칙에 같은 지문의 '다른 사이트' 공고가 이미 있으면
    중복으로 보고 조용히(2) 저장한다. (같은 사이트 안의 동명 공고는 팀이 다른 별개 공고일 수 있다)
    """
    with connect() as c:
        if c.execute("SELECT 1 FROM matches WHERE watch_id = ? AND job_key = ?", (watch_id, job.key)).fetchone():
            return None
        if notified == 0:
            dup = c.execute(
                "SELECT 1 FROM matches m JOIN jobs j ON j.key = m.job_key"
                " WHERE m.watch_id = ? AND j.fingerprint = ? AND j.site <> ?",
                (watch_id, fingerprint(job), job.site),
            ).fetchone()
            if dup:
                notified = 2
        c.execute(
            "INSERT INTO matches(watch_id, job_key, matched_at, notified) VALUES (?, ?, ?, ?)",
            (watch_id, job.key, config.now_iso(), notified),
        )
        return notified


def pending_notifications(watch_id: int) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT j.* FROM matches m JOIN jobs j ON j.key = m.job_key"
            " WHERE m.watch_id = ? AND m.notified = 0 ORDER BY m.matched_at, j.site",
            (watch_id,),
        ).fetchall()
    return [_job(r) for r in rows]


def set_notified(watch_id: int, keys: list[str], value: int = 1) -> None:
    with connect() as c:
        c.executemany(
            "UPDATE matches SET notified = ? WHERE watch_id = ? AND job_key = ?",
            [(value, watch_id, k) for k in keys],
        )


def silence_pending() -> None:
    """웹훅이 없을 때 쌓인 알림 대기를 비운다 (나중에 웹훅을 넣었을 때 폭탄 알림 방지)."""
    with connect() as c:
        c.execute("UPDATE matches SET notified = 2 WHERE notified = 0")


def set_status(keys: list[str], status: str) -> None:
    with connect() as c:
        c.executemany("UPDATE jobs SET status = ? WHERE key = ?", [(status, k) for k in keys])


def _job(row: sqlite3.Row) -> dict:
    j = dict(row)
    j["tags"] = json.loads(j.get("tags") or "[]")
    return j


def query_jobs(*, watch_id: int | None = None, site: str = "", status: str = "", since: str = "",
               text: str = "") -> list[dict]:
    """공고 목록용. 매칭된 공고를 최신순으로. status='' 이면 숨김 제외 전체, 'applied' 는 지원 기록이 있는 것."""
    where = ["1=1"]
    args: list = []
    if watch_id:
        where.append("m.watch_id = ?")
        args.append(watch_id)
    if site:
        where.append("j.site = ?")
        args.append(site)
    if status == "all":
        pass
    elif status == "applied":
        where.append("a.job_key IS NOT NULL")
    elif status:
        where.append("j.status = ?")
        args.append(status)
    else:
        where.append("j.status <> 'hidden'")
    if since:
        where.append("j.first_seen >= ?")
        args.append(since)
    if text:
        where.append("(j.title LIKE ? OR j.company LIKE ? OR j.tags LIKE ?)")
        args += [f"%{text}%"] * 3
    sql = f"""
        SELECT j.*, GROUP_CONCAT(DISTINCT m.watch_id) AS watch_ids, a.stage AS app_stage, a.step AS app_step
        FROM jobs j JOIN matches m ON m.job_key = j.key
        LEFT JOIN applications a ON a.job_key = j.key
        WHERE {' AND '.join(where)}
        GROUP BY j.key
        ORDER BY j.first_seen DESC,
                 CASE WHEN j.posted GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN j.posted ELSE '' END DESC,
                 j.site
    """
    with connect() as c:
        return [_job(r) for r in c.execute(sql, args)]


def stats() -> dict:
    today = config.now().strftime("%Y-%m-%d")
    with connect() as c:
        row = c.execute(
            """
            SELECT COUNT(DISTINCT j.key) AS total,
                   COUNT(DISTINCT CASE WHEN j.first_seen >= ? THEN j.key END) AS today,
                   COUNT(DISTINCT CASE WHEN j.status = 'star' THEN j.key END) AS starred,
                   (SELECT COUNT(*) FROM applications) AS applied
            FROM jobs j JOIN matches m ON m.job_key = j.key
            """,
            (today,),
        ).fetchone()
    return dict(row)


# --------------------------------------------------------------------------
# 지원 현황
# --------------------------------------------------------------------------
def get_job(key: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE key = ?", (key,)).fetchone()
    return _job(row) if row else None


def create_manual_job(company: str, title: str, url: str) -> str:
    """수집하지 않은 공고에 지원했을 때 직접 추가. 새 job key 를 돌려준다."""
    job_id = secrets.token_hex(6)
    key = f"manual:{job_id}"
    ts = config.now_iso()
    with connect() as c:
        c.execute(
            "INSERT INTO jobs(key, site, job_id, title, company, url, first_seen, last_seen)"
            " VALUES (?, 'manual', ?, ?, ?, ?, ?, ?)",
            (key, job_id, title, company, url, ts, ts),
        )
    return key


def update_manual_job(key: str, company: str, title: str, url: str) -> None:
    with connect() as c:
        c.execute("UPDATE jobs SET company = ?, title = ?, url = ? WHERE key = ? AND site = 'manual'",
                  (company, title, url, key))


def get_application(key: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM applications WHERE job_key = ?", (key,)).fetchone()
        if not row:
            return None
        app = dict(row)
        app["events"] = [dict(r) for r in c.execute(
            "SELECT at, stage, step FROM app_events WHERE job_key = ? ORDER BY id", (key,))]
    return app


def save_application(key: str, data: dict) -> None:
    """지원 기록을 만들거나 고친다. 단계(stage/step)가 바뀌면 타임라인에 남긴다."""
    ts = config.now_iso()
    with connect() as c:
        old = c.execute("SELECT stage, step FROM applications WHERE job_key = ?", (key,)).fetchone()
        if old is None:
            c.execute(
                "INSERT INTO applications(job_key, stage, step, applied_at, next_date, memo, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, data["stage"], data["step"], data["applied_at"] or ts[:10], data["next_date"], data["memo"],
                 ts, ts),
            )
        else:
            c.execute(
                "UPDATE applications SET stage=?, step=?, applied_at=?, next_date=?, memo=?, updated_at=?"
                " WHERE job_key = ?",
                (data["stage"], data["step"], data["applied_at"], data["next_date"], data["memo"], ts, key),
            )
        if old is None or (old["stage"], old["step"]) != (data["stage"], data["step"]):
            c.execute("INSERT INTO app_events(job_key, at, stage, step) VALUES (?, ?, ?, ?)",
                      (key, ts, data["stage"], data["step"]))


def delete_application(key: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM applications WHERE job_key = ?", (key,))
        c.execute("DELETE FROM app_events WHERE job_key = ?", (key,))
        c.execute("DELETE FROM jobs WHERE key = ? AND site = 'manual'", (key,))


def list_applications() -> list[dict]:
    """지원 현황 보드용."""
    with connect() as c:
        rows = c.execute(
            """
            SELECT a.*, j.title, j.company, j.url, j.site, j.deadline
            FROM applications a JOIN jobs j ON j.key = a.job_key
            ORDER BY a.updated_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# site runs
# --------------------------------------------------------------------------
def record_site_run(site: str, ok: bool, fetched: int, error: str = "") -> None:
    ts = config.now_iso()
    with connect() as c:
        c.execute(
            """
            INSERT INTO site_runs(site, finished_at, ok, fetched, error, last_ok_at) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(site) DO UPDATE SET finished_at=excluded.finished_at, ok=excluded.ok,
                fetched=excluded.fetched, error=excluded.error,
                last_ok_at=CASE WHEN excluded.ok = 1 THEN excluded.finished_at ELSE site_runs.last_ok_at END
            """,
            (site, ts, int(ok), fetched, error[:500], ts if ok else ""),
        )


def site_runs() -> dict[str, dict]:
    with connect() as c:
        return {r["site"]: dict(r) for r in c.execute("SELECT * FROM site_runs")}
