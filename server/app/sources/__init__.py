from .base import Source
from .chotot import Chotot
from .manual import parse_manual_text
from .googlesearch import GoogleSearch
from .webscrape import Alonhadat, Batdongsan, Thuviennhadat, Raobannhadat

SOURCES: dict[str, Source] = {s.name: s for s in (Chotot(), Alonhadat(), Batdongsan(), Thuviennhadat(), Raobannhadat(), GoogleSearch())}
