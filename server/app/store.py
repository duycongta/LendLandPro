"""Lưu tin đã thu thập (lịch sử giá, bằng chứng) vào SQLite."""
import json, sqlite3
from pathlib import Path
from .models import Listing

DB = Path(__file__).resolve().parent.parent / "data" / "khaogia.sqlite"

def _conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS listing(
        id INTEGER PRIMARY KEY, source TEXT, url TEXT, fetched_at TEXT, data TEXT)""")
    return c

def save(listings: list[Listing]):
    uniq = {}
    for l in listings:                       # trong cùng một lô, tin trùng link chỉ giữ một bản
        uniq[l.url or id(l)] = l
    listings = list(uniq.values())
    with _conn() as c:
        c.executemany("DELETE FROM listing WHERE url=? AND url!=''", [(l.url,) for l in listings])
        c.executemany("INSERT INTO listing(source,url,fetched_at,data) VALUES(?,?,?,?)",
                      [(l.source, l.url, l.fetched_at, json.dumps(l.to_dict(), ensure_ascii=False)) for l in listings])

def load_all() -> list[Listing]:
    out = []
    with _conn() as c:
        for (d,) in c.execute("SELECT data FROM listing"):
            d = json.loads(d); d.pop("price_per_m2", None); out.append(Listing(**d))
    return out
