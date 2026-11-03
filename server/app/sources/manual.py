"""Nhập tay / dán nội dung tin (kể cả tin Facebook): app trích xuất giá, diện tích, loại đất."""
import datetime as dt
from ..models import Listing
from ..parse import parse_price, parse_area, parse_frontage, guess_land_type

def parse_manual_text(text: str, url: str = "", address: str = "", source: str = "thu cong") -> Listing:
    return Listing(source=source, url=url, title=text.strip().splitlines()[0][:120] if text.strip() else "",
                   address=address, description=text,
                   price_vnd=parse_price(text), area_m2=parse_area(text),
                   frontage_m=parse_frontage(text), land_type=guess_land_type(text),
                   fetched_at=dt.datetime.now().isoformat(timespec="seconds"),
                   raw={"pasted_text": text})
