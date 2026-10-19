from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Crawler, Job, text_of


class LinkedIn(Crawler):
    """비로그인(guest) 채용 검색 조각 HTML. 대한민국 · 최근 1주 · 최신순 10건.

    링크드인은 요청이 잦으면 429를 돌려주므로 요청 간격을 넉넉히 둔다.
    """

    site = "linkedin"
    label = "링크드인"
    home = "https://www.linkedin.com"
    color = 0x0A66C2
    delay = 5.0

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/jobs-guest/jobs/api/seeMoreJobPostings/search",
            params={
                "keywords": keyword,
                "location": "South Korea",
                "f_TPR": "r604800",
                "sortBy": "DD",
                "start": 0,
            },
        )
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for card in soup.select("div.base-search-card"):
            urn = card.get("data-entity-urn", "")
            job_id = urn.rsplit(":", 1)[-1]
            if not job_id.isdigit():
                continue
            posted = card.select_one("time")
            jobs.append(
                Job(
                    site=self.site,
                    job_id=job_id,
                    title=text_of(card.select_one(".base-search-card__title")),
                    company=text_of(card.select_one(".base-search-card__subtitle")),
                    url=f"{self.home}/jobs/view/{job_id}",
                    location=text_of(card.select_one(".job-search-card__location")),
                    posted=posted.get("datetime", "") if posted else "",
                )
            )
        return jobs
