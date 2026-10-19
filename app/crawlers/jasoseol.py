from __future__ import annotations

from .base import Crawler, Job, dedupe, next_data, norm


class Jasoseol(Crawler):
    """자소설닷컴 /search 페이지의 서버 렌더링 데이터(__NEXT_DATA__) 사용.

    공채 위주라 한 공고 안에 여러 모집 분야(employments)가 들어 있다.
    키워드 검색은 서버에서 무시되므로, 키워드를 직무 분류(dutyGroupIds)에 대응시켜 받고
    전체 최신 공고에서도 제목·모집분야에 키워드가 있는 것을 골라 합친다.
    """

    site = "jasoseol"
    label = "자소설닷컴"
    home = "https://jasoseol.com"
    color = 0x00C389

    def _search_page(self, params: dict) -> tuple[list[dict], list[dict]]:
        res = self.get(f"{self.home}/search", params={**params, "excludeClosed": "true"}, cache=True)
        props = next_data(res.text)["props"]["pageProps"]
        query = props["dehydratedState"]["queries"][0]["state"]["data"]
        return query.get("data") or [], props.get("duties") or []

    def search(self, keyword: str) -> list[Job]:
        nk = norm(keyword)
        latest, duties = self._search_page({})
        duty_names = {d["id"]: d["name"] for d in duties}
        matched_duties = {d["id"] for d in duties if nk and nk in norm(d["name"])}

        postings = []
        if matched_duties:
            by_duty, _ = self._search_page({"dutyGroupIds": ",".join(map(str, sorted(matched_duties)))})
            postings += by_duty
        for p in latest:
            texts = [p.get("title", "")] + [e.get("field") or "" for e in p.get("employments") or []]
            if any(nk in norm(t) for t in texts):
                postings.append(p)

        jobs = []
        for p in postings:
            # 공채 제목("2026년 신입사원 채용")만으로는 직무를 알 수 없어서,
            # 키워드에 해당하는 모집분야를 제목 뒤에 붙인다. 포함/제외 단어도 이걸 기준으로 걸린다.
            fields: list[str] = []
            duty_tags: list[str] = []
            for e in p.get("employments") or []:
                field = (e.get("field") or "").strip()
                hit_duties = [duty_names[i] for i in e.get("duty_group_ids") or [] if i in matched_duties]
                if field and (hit_duties or nk in norm(field)):
                    fields.append(field)
                    duty_tags += hit_duties
            title = (p.get("title") or "").strip()
            fields = [f for f in dict.fromkeys(fields) if norm(f) not in norm(title)]
            if fields:
                extra = ", ".join(fields[:2]) + (f" 외 {len(fields) - 2}" if len(fields) > 2 else "")
                title = f"{title} — {extra}"
            jobs.append(
                Job(
                    site=self.site,
                    job_id=str(p["id"]),
                    title=title[:200],
                    company=p.get("name") or "",
                    url=f"{self.home}/recruit/{p['id']}",
                    deadline=(p.get("end_time") or "")[:10],
                    posted=(p.get("start_time") or "")[:10],
                    tags=list(dict.fromkeys(duty_tags)),
                )
            )
        return dedupe(jobs)
