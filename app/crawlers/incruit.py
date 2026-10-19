from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Crawler, Job, text_of


class Incruit(Crawler):
    """검색 결과 HTML (ul.c_row) 파싱. EUC-KR 페이지. 등록일순 30건."""

    site = "incruit"
    label = "인크루트"
    home = "https://www.incruit.com"
    color = 0x1E50D2

    def search(self, keyword: str) -> list[Job]:
        res = self.get(
            "https://search.incruit.com/list/search.asp",
            params={"col": "job", "kw": keyword, "sortfield": "reg", "startno": 0},
        )
        res.encoding = "cp949"
        soup = BeautifulSoup(res.text, "lxml")
        jobs = []
        for row in soup.select("ul.c_row"):
            job_no = row.get("jobno")
            link = row.select_one(".cell_mid .cl_top a")
            if not job_no or link is None:
                continue
            info = [text_of(s) for s in row.select(".cell_mid .cl_md span")]
            tags = [text_of(s).rstrip(",") for s in row.select(".cell_mid .cl_btm span")]
            last = [text_of(s) for s in row.select(".cell_last .cl_btm span")]
            jobs.append(
                Job(
                    site=self.site,
                    job_id=job_no,
                    title=text_of(link),
                    company=text_of(row.select_one("a.cpname")),
                    url=f"https://job.incruit.com/jobdb_info/jobpost.asp?job={job_no}",
                    location=info[0] if info else "",
                    career=info[1] if len(info) > 1 else "",
                    deadline=last[0] if last else "",
                    posted=last[1].strip("()") if len(last) > 1 else "",
                    tags=[t for t in tags if t],
                )
            )
        return jobs
