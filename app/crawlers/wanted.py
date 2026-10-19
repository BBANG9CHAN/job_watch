from __future__ import annotations

from urllib.parse import quote

from .base import Crawler, Job


class Wanted(Crawler):
    """원티드 통합검색의 포지션 탭이 쓰는 JSON API. 최신순 50건."""

    site = "wanted"
    label = "원티드"
    home = "https://www.wanted.co.kr"
    color = 0x3366FF

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/api/chaos/search/v1/position",
            params={
                "query": keyword,
                "country": "kr",
                "years": -1,
                "sort": "job.latest_order",
                "limit": 50,
                "offset": 0,
            },
            headers={"Referer": f"{self.home}/search?query={quote(keyword)}&tab=position"},
        )
        jobs = []
        for p in res.json().get("data") or []:
            lo, hi = p.get("annual_from"), p.get("annual_to")
            if p.get("is_newbie") or lo == 0:
                career = "신입" if not hi else f"신입~{hi}년"
            elif lo is not None:
                career = f"{lo}년 이상" if not hi or hi >= 100 else f"{lo}~{hi}년"
            else:
                career = ""
            due = p.get("due_time")
            jobs.append(
                Job(
                    site=self.site,
                    job_id=str(p["id"]),
                    title=(p.get("position") or "").strip(),
                    company=(p.get("company") or {}).get("name", ""),
                    url=f"{self.home}/wd/{p['id']}",
                    location=(p.get("address") or {}).get("location", ""),
                    career=career,
                    deadline=due[:10] if due else "상시",
                )
            )
        return jobs
