"""사이트별 크롤러 등록소. 새 사이트를 추가하려면 Crawler를 상속해 search()를 구현하고 여기에 넣으면 된다."""

from .base import Crawler, Job
from .designerjob import DesignerJob
from .groupby import GroupBy
from .incruit import Incruit
from .jasoseol import Jasoseol
from .jobkorea import JobKorea
from .linkedin import LinkedIn
from .saramin import Saramin
from .wanted import Wanted
from .work24 import Work24

CRAWLERS: dict[str, type[Crawler]] = {
    c.site: c
    for c in (Saramin, JobKorea, Work24, Incruit, Wanted, LinkedIn, Jasoseol, GroupBy, DesignerJob)
}

__all__ = ["CRAWLERS", "Crawler", "Job"]
