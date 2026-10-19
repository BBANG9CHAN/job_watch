from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Crawler, Job, text_of


class DesignerJob(Crawler):
    """디자이너잡 채용정보 상세검색 HTML (tr.in_recruit_list). 수정일순 50건."""

    site = "designerjob"
    label = "디자이너잡"
    home = "https://www.designerjob.co.kr"
    color = 0xFF5A5F

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/recruit/lists",
            params={
                "sf": "upd_date",
                "sm": "DESC",
                "ctg": "search",
                "search_mode": "search",
                "keyword": keyword,
                "page_record": 50,
            },
        )
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for row in soup.select("tr.in_recruit_list"):
            link = row.select_one("a.in_title")
            if link is None:
                continue
            m = re.search(r"rec_idx(?:%5D|\])=(\d+)", link.get("href", ""))
            if not m:
                continue
            rec_idx = m.group(1)
            job_type = row.select_one("p.j_type")
            tags = [t.strip() for t in job_type.get_text("|").split("|") if t.strip()] if job_type else []
            jobs.append(
                Job(
                    site=self.site,
                    job_id=rec_idx,
                    title=text_of(link),
                    company=text_of(row.select_one(".com_nm")),
                    url=f"{self.home}/recruit/view?param%5Brec_idx%5D={rec_idx}",
                    location=text_of(row.select_one(".c_area")),
                    career=" · ".join(text_of(p) for p in row.select("td.ji_ja p")),
                    deadline=text_of(row.select_one("td.day_eddt")),
                    posted=text_of(row.select_one("td.day_modi")),
                    tags=tags,
                )
            )
        return jobs
