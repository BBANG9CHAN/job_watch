"""웹 대시보드 (FastAPI + Jinja2)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, export, monitor, notifier, tracker
from .crawlers import CRAWLERS
from .scheduler import scheduler

HERE = Path(__file__).parent
PAGE_SIZE = 40
STATUSES = {"", "star", "hidden"}  # 지원 여부는 applications 테이블에서 따로 관리
SITES = {k: {"label": c.label, "color": f"#{c.color:06x}", "home": c.home} for k, c in CRAWLERS.items()}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["SITES"] = SITES
templates.env.globals["STAGES"] = db.STAGES


# --------------------------------------------------------------------------
# 로그인 (APP_PASSWORD 가 설정된 경우에만)
# --------------------------------------------------------------------------
COOKIE = "jw_auth"
COOKIE_DAYS = 30


def _token(expiry: int) -> str:
    msg = f"{expiry}:{config.APP_PASSWORD}".encode()
    return f"{expiry}.{hmac.new(config.secret_key(), msg, hashlib.sha256).hexdigest()}"


def _token_ok(token: str) -> bool:
    try:
        expiry = int(token.split(".", 1)[0])
    except ValueError:
        return False
    return expiry > time.time() and hmac.compare_digest(token, _token(expiry))


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if not config.APP_PASSWORD or path == "/login" or path.startswith("/static/"):
        return await call_next(request)
    if _token_ok(request.cookies.get(COOKIE, "")):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"error": "로그인이 필요합니다"}, status_code=401)
    return RedirectResponse(f"/login?next={quote(str(request.url.path))}", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": error})


@app.post("/login")
async def login(password: str = Form(""), next: str = Form("/")):
    if not config.APP_PASSWORD or not hmac.compare_digest(password, config.APP_PASSWORD):
        await asyncio.sleep(1.5)  # 무작위 대입 지연
        return RedirectResponse(f"/login?error=1&next={quote(next)}", status_code=303)
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    res = RedirectResponse(target, status_code=303)
    expiry = int(time.time()) + COOKIE_DAYS * 86400
    res.set_cookie(COOKIE, _token(expiry), max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax")
    return res


@app.get("/logout")
def logout():
    res = RedirectResponse("/login", status_code=303)
    res.delete_cookie(COOKIE)
    return res


# --------------------------------------------------------------------------
# 홈: 지원 현황 보드 + 새 공고 요약
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "board": tracker.board(),
            "stages": db.STAGES,
            "recent": export.filtered_jobs()[:6],
            "stats": db.stats(),
            "state": monitor.state,
            "nav": "home",
        },
    )


# --------------------------------------------------------------------------
# 공고 목록
# --------------------------------------------------------------------------
@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, watch: int = 0, site: str = "", status: str = "", days: int = 0, q: str = "",
              page: int = 1):
    items = export.filtered_jobs(watch, site, status, days, q)
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = min(max(1, page), pages)
    filters = {"watch": watch, "site": site, "status": status, "days": days, "q": q}

    def page_url(n: int) -> str:
        params = {k: v for k, v in {**filters, "page": n}.items() if v}
        return "/jobs?" + urlencode(params)

    watches = db.list_watches()
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "items": items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE],
            "total": len(items),
            "page": page,
            "pages": pages,
            "page_url": page_url,
            "filters": filters,
            "watches": watches,
            "watch_names": {w["id"]: w["name"] for w in watches},
            "stats": db.stats(),
            "state": monitor.state,
            "nav": "jobs",
        },
    )


@app.post("/api/status")
async def api_status(request: Request):
    body = await request.json()
    keys = [str(k) for k in body.get("keys") or []]
    status = body.get("status", "")
    if status not in STATUSES or not keys:
        return JSONResponse({"error": "잘못된 요청"}, status_code=400)
    db.set_status(keys, status)
    return {"ok": True}


@app.post("/api/crawl")
def api_crawl():
    return {"started": scheduler.trigger(), "state": monitor.state}


# --------------------------------------------------------------------------
# 지원 현황 API
# --------------------------------------------------------------------------
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(body: dict, name: str, limit: int) -> str:
    return str(body.get(name) or "").strip()[:limit]


@app.get("/api/applications/{key}")
def api_application_get(key: str):
    job = db.get_job(key)
    if not job:
        return JSONResponse({"error": "공고를 찾을 수 없습니다"}, status_code=404)
    job["site_label"] = tracker.site_label(job["site"])
    return {"job": job, "application": db.get_application(key), "stages": db.STAGES}


@app.post("/api/applications")
async def api_application_save(request: Request):
    """지원 기록 만들기·고치기. key 가 없으면 회사·제목으로 직접 추가."""
    body = await request.json()
    data = {
        "stage": _text(body, "stage", 20) or "applied",
        "step": _text(body, "step", 60),
        "applied_at": _text(body, "applied_at", 10),
        "next_date": _text(body, "next_date", 10),
        "memo": _text(body, "memo", 2000),
    }
    if data["stage"] not in db.STAGES:
        return JSONResponse({"error": "알 수 없는 단계"}, status_code=400)
    for k in ("applied_at", "next_date"):
        if data[k] and not _DATE_RE.match(data[k]):
            return JSONResponse({"error": "날짜 형식은 YYYY-MM-DD"}, status_code=400)

    company, title, url = _text(body, "company", 100), _text(body, "title", 200), _text(body, "url", 500)
    if url and not re.match(r"^https?://", url):  # javascript: 같은 링크 방지
        return JSONResponse({"error": "링크는 http:// 또는 https:// 로 시작해야 합니다"}, status_code=400)

    key = _text(body, "key", 100)
    if key:
        job = db.get_job(key)
        if not job:
            return JSONResponse({"error": "공고를 찾을 수 없습니다"}, status_code=404)
        if job["site"] == "manual" and (company or title):
            db.update_manual_job(key, company or job["company"], title or job["title"], url)
    else:
        if not company and not title:
            return JSONResponse({"error": "회사명이나 공고 제목을 입력하세요"}, status_code=400)
        key = db.create_manual_job(company, title or "(제목 없음)", url)
    db.save_application(key, data)
    return {"ok": True, "key": key, "stage": data["stage"], "stage_label": db.STAGES[data["stage"]]}


@app.post("/api/applications/{key}/delete")
def api_application_delete(key: str):
    db.delete_application(key)
    return {"ok": True}


@app.post("/api/export-discord")
async def api_export_discord(request: Request):
    """지금 보고 있는 목록(필터 그대로)을 디스코드로 정리해서 보낸다."""
    body = await request.json()
    try:
        filters = {
            "watch": int(body.get("watch") or 0),
            "site": str(body.get("site") or ""),
            "status": str(body.get("status") or ""),
            "days": int(body.get("days") or 0),
            "q": str(body.get("q") or ""),
        }
    except ValueError:
        return JSONResponse({"error": "잘못된 요청"}, status_code=400)
    try:
        count, messages = await asyncio.to_thread(export.send_to_discord, **filters)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"전송 실패: {e}"}, status_code=502)
    return {"ok": True, "count": count, "messages": messages}


@app.get("/api/state")
def api_state():
    return monitor.state


# --------------------------------------------------------------------------
# 모니터링 규칙
# --------------------------------------------------------------------------
def _split_terms(text: str) -> list[str]:
    terms = [t.strip() for t in re.split(r"[,\n]", text or "")]
    return list(dict.fromkeys(t for t in terms if t))


@app.get("/watches", response_class=HTMLResponse)
def watches_page(request: Request, msg: str = ""):
    return templates.TemplateResponse(
        request, "watches.html", {"watches": db.list_watches(), "msg": msg, "nav": "watches"}
    )


@app.post("/watches/save")
async def watch_save(request: Request):
    form = await request.form()
    watch_id = int(form.get("id") or 0) or None
    sites = [s for s in form.getlist("sites") if s in CRAWLERS]
    data = {
        "name": (form.get("name") or "").strip() or "이름 없는 규칙",
        "keywords": _split_terms(form.get("keywords", "")),
        "include_terms": _split_terms(form.get("include_terms", "")),
        "exclude_terms": _split_terms(form.get("exclude_terms", "")),
        "sites": [] if len(sites) == len(CRAWLERS) else sites,
        "match_tags": form.get("match_tags") == "on",
        "notify": form.get("notify") == "on",
        "enabled": form.get("enabled") == "on",
    }
    if not data["keywords"]:
        return RedirectResponse("/watches?msg=" + quote("검색어를 하나 이상 입력하세요"), status_code=303)
    if not sites:
        return RedirectResponse("/watches?msg=" + quote("사이트를 하나 이상 선택하세요"), status_code=303)
    db.save_watch(data, watch_id)
    return RedirectResponse("/watches?msg=" + quote(f"'{data['name']}' 저장했습니다"), status_code=303)


@app.post("/watches/{watch_id}/delete")
def watch_delete(watch_id: int):
    db.delete_watch(watch_id)
    return RedirectResponse("/watches?msg=" + quote("삭제했습니다"), status_code=303)


# --------------------------------------------------------------------------
# 설정 / 상태
# --------------------------------------------------------------------------
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, msg: str = ""):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": db.get_settings(),
            "runs": db.site_runs(),
            "state": monitor.state,
            "msg": msg,
            "password_on": bool(config.APP_PASSWORD),
            "nav": "settings",
        },
    )


@app.post("/settings")
def settings_save(
    discord_webhook_url: str = Form(""),
    interval_minutes: str = Form("60"),
    public_url: str = Form(""),
    quiet_hours: str = Form(""),
):
    webhook = discord_webhook_url.strip()
    if webhook and not re.match(r"^https://(discord|discordapp)\.com/api/webhooks/", webhook):
        return RedirectResponse("/settings?msg=" + quote("디스코드 웹훅 주소 형식이 아닙니다"), status_code=303)
    try:
        minutes = max(10, int(interval_minutes))
    except ValueError:
        minutes = 60
    quiet = quiet_hours.strip().replace(" ", "")
    if quiet and not re.fullmatch(r"\d{1,2}-\d{1,2}", quiet):
        return RedirectResponse("/settings?msg=" + quote("방해금지 시간은 '0-8' 형식으로 입력하세요"), status_code=303)
    db.set_settings({
        "discord_webhook_url": webhook,
        "interval_minutes": str(minutes),
        "public_url": public_url.strip().rstrip("/"),
        "quiet_hours": quiet,
    })
    scheduler.reschedule()
    return RedirectResponse("/settings?msg=" + quote("저장했습니다"), status_code=303)


@app.post("/settings/test-discord")
def settings_test_discord():
    webhook = db.get_settings().get("discord_webhook_url", "")
    if not webhook:
        return RedirectResponse("/settings?msg=" + quote("웹훅 주소를 먼저 저장하세요"), status_code=303)
    try:
        notifier.send_text(webhook, "✅ Job Watch 테스트 메시지입니다. 알림이 정상적으로 연결됐어요!")
        msg = "테스트 메시지를 보냈습니다. 디스코드를 확인하세요"
    except Exception as e:
        msg = f"전송 실패: {e}"
    return RedirectResponse("/settings?msg=" + quote(msg), status_code=303)
