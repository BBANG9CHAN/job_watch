from __future__ import annotations

from .base import Crawler, Job, dedupe, next_data, norm


class GroupBy(Crawler):
    """그룹바이 /positions 페이지의 서버 렌더링 데이터(__NEXT_DATA__) 사용.

    - api.groupby.kr 를 직접 호출하면 '[표시 제한]' 가짜 데이터가 내려오므로 쓰지 않는다.
    - 서버 렌더링은 키워드 검색을 지원하지 않아서, 키워드를 직무 분류(positionTypes)에 대응시켜
      해당 직무의 최신 공고를 받고, 전체 최신 공고에서도 키워드가 들어간 것을 골라 합친다.
    """

    site = "groupby"
    label = "그룹바이"
    home = "https://groupby.kr"
    color = 0x6C47FF

    def _position_types(self) -> list[dict]:
        res = self.get("https://api.groupby.kr/services/base-info", cache=True)
        return (res.json().get("data") or {}).get("positionTypes") or []

    def _positions(self, params: dict) -> list[dict]:
        res = self.get(f"{self.home}/positions", params=params, cache=True)
        fallback = next_data(res.text)["props"]["pageProps"].get("positionFallback") or {}
        items = []
        for api_key, page in fallback.items():
            if "limit=0" in api_key:  # 건수만 세는 요청
                continue
            items.extend(page.get("items") or [])
        return items

    def search(self, keyword: str) -> list[Job]:
        nk = norm(keyword)
        type_ids = [
            str(t["id"])
            for t in self._position_types()
            if t.get("parentId") and not t.get("isDeprecated") and nk and nk in norm(t["name"])
        ]

        items = []
        if type_ids:
            items += self._positions({"positionTypes": ",".join(type_ids)})
        for item in self._positions({}):
            names = [item.get("name", "")] + [t["name"] for t in item.get("positionTypes") or []]
            if any(nk in norm(n) for n in names):
                items.append(item)

        jobs = []
        for item in items:
            startup = item.get("startup") or {}
            exp = item.get("experienceRange") or {}
            lo, hi = exp.get("min"), exp.get("max")
            career = item.get("careerType") or ""
            if career == "경력" and lo is not None:
                career = f"경력 {lo}~{hi}년" if hi else f"경력 {lo}년 이상"
            jobs.append(
                Job(
                    site=self.site,
                    job_id=str(item["id"]),
                    title=(item.get("name") or "").strip(),
                    company=startup.get("name", ""),
                    url=f"{self.home}/positions/{item['id']}",
                    location=item.get("address") or startup.get("location") or "",
                    career=career,
                    posted=(item.get("publishedAt") or "")[:10],
                    tags=[t["name"] for t in item.get("positionTypes") or []],
                )
            )
        return dedupe(jobs)
