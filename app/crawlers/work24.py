from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .base import Crawler, Job, text_of


class Work24(Crawler):
    """고용24(구 워크넷) 채용정보 상세검색 HTML 파싱. 등록일순 50건.

    잡코리아·사람인 등에서 연계된 공고도 함께 나온다(중복은 상위에서 지문으로 걸러짐).
    """

    site = "work24"
    label = "고용24(워크넷)"
    home = "https://www.work24.go.kr"
    color = 0x00A651

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            f"{self.home}/wk/a/b/1200/retriveDtlEmpSrchList.do",
            params={
                "srcKeyword": keyword,
                "sortField": "DATE",
                "sortOrderBy": "DESC",
                "resultCnt": 50,
                "pageIndex": 1,
                "currentPageNo": 1,
                "siteClcd": "all",
                "searchMode": "Y",
            },
        )
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for row in soup.select("tr[id^=list]"):
            link = row.select_one("a[href*=empDetailAuthView]")
            if link is None:
                continue
            href = link["href"]
            auth_no = parse_qs(urlparse(href).query).get("wantedAuthNo", [""])[0]
            if not auth_no:
                continue

            career = " · ".join(text_of(s) for s in row.select("li.member span"))
            location = text_of(row.select_one("li.site"))

            deadline = ""
            script = row.find("script", string=re.compile("closeDt"))
            if script:
                date = re.search(r"var date = '([^']*)'", script.string)
                if date and not date.group(1).startswith("2099"):
                    deadline = date.group(1)
                else:
                    deadline = "채용시까지"

            posted = ""
            reg = row.find("p", string=re.compile("등록일"))
            if reg:
                posted = text_of(reg).replace("등록일 :", "").strip()

            provider = row.select_one(".logo_wrap img[alt]")
            tags = [provider["alt"].replace("정보제공처", "").strip()] if provider else []

            jobs.append(
                Job(
                    site=self.site,
                    job_id=auth_no,
                    title=text_of(link),
                    company=text_of(row.select_one("a.cp_name")),
                    url=f"{self.home}{href}" if href.startswith("/") else href,
                    location=location,
                    career=career,
                    deadline=deadline,
                    posted=posted,
                    tags=tags,
                )
            )
        return jobs
