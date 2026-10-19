from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Crawler, Job, clean, text_of


class Saramin(Crawler):
    """검색 결과 HTML (div.item_recruit) 파싱. 등록일순 50건."""

    site = "saramin"
    label = "사람인"
    home = "https://www.saramin.co.kr"
    color = 0x4876EF

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/zf_user/search/recruit",
            params={
                "searchword": keyword,
                "searchType": "search",
                "recruitSort": "reg_dt",
                "recruitPageCount": 50,
                "recruitPage": 1,
            },
        )
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for item in soup.select("div.item_recruit"):
            rec_idx = item.get("value")
            link = item.select_one("h2.job_tit a")
            if not rec_idx or link is None:
                continue
            cond = [text_of(s) for s in item.select(".job_condition > span")]
            jobs.append(
                Job(
                    site=self.site,
                    job_id=rec_idx,
                    title=clean(link.get("title")) or text_of(link),
                    company=text_of(item.select_one(".corp_name")),
                    url=f"{self.home}/zf_user/jobs/relay/view?rec_idx={rec_idx}",
                    location=cond[0] if cond else "",
                    career=cond[1] if len(cond) > 1 else "",
                    deadline=text_of(item.select_one(".job_date .date")),
                    posted=text_of(item.select_one(".job_sector .job_day")),
                    tags=[text_of(a) for a in item.select(".job_sector a")],
                )
            )
        return jobs
