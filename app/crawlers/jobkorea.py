from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Crawler, Job, text_of


class JobKorea(Crawler):
    """Next.js 서버 렌더링 HTML의 CardJob 컴포넌트 파싱. 등록일순 1페이지(약 25건).

    클래스명은 Tailwind라 자주 바뀌므로 data-sentry-component 속성과 GI_Read 링크를 기준으로 잡는다.
    """

    site = "jobkorea"
    label = "잡코리아"
    home = "https://www.jobkorea.co.kr"
    color = 0x0F6FFF

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/Search/",
            params={"stext": keyword, "tabType": "recruit", "Ord": "RegDtDesc", "Page_No": 1},
        )
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for card in soup.select("[data-sentry-component=CardJob]"):
            title_link = card.select_one("a[data-sentry-component=Title]")
            if title_link is None:
                continue
            m = re.search(r"GI_Read/(\d+)", title_link.get("href", ""))
            if not m:
                continue
            gno = m.group(1)
            title = text_of(title_link)

            # 같은 GI_Read 링크가 로고 / 제목 / 회사명 세 군데에 걸려 있다. 남는 하나가 회사명.
            company = ""
            for a in card.select(f'a[href*="GI_Read/{gno}"]'):
                if a is title_link or a.get("data-sentry-component") == "CompanyLogo":
                    continue
                first = a.find("span")
                company = text_of(first) if first else text_of(a)
                if company:
                    break
            if not company:
                img = card.select_one("img[alt]")
                company = (img["alt"].removesuffix(" 로고") if img else "").strip()

            chips = [text_of(c.select_one("span.truncate") or c)
                     for c in card.select("[data-sentry-component=GrayChip]")]
            career = ""
            for span in card.select("span"):
                t = text_of(span)
                if re.search(r"(신입|경력|년↑|년 이상)", t) and len(t) < 30 and t != title:
                    career = t
                    break

            jobs.append(
                Job(
                    site=self.site,
                    job_id=gno,
                    title=title,
                    company=company,
                    url=f"{self.home}/Recruit/GI_Read/{gno}",
                    location=chips[0] if chips else "",
                    career=career,
                    tags=chips[1:],
                )
            )
        return jobs
