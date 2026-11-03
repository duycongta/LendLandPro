from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Listing:
    source: str
    url: str
    title: str
    address: str = ""
    description: str = ""
    price_vnd: Optional[float] = None
    area_m2: Optional[float] = None
    frontage_m: Optional[float] = None
    kind: str = ""               # dat / nha / can_ho (loại tài sản)
    land_type: str = ""          # ONT / CLN / LUC / RSX ... hoặc văn bản tự do
    posted_at: str = ""          # ISO
    fetched_at: str = ""         # ISO
    raw: dict = field(default_factory=dict)  # dữ liệu gốc làm chứng cứ

    @property
    def price_per_m2(self):
        if self.price_vnd and self.area_m2 and self.area_m2 > 0:
            return self.price_vnd / self.area_m2
        return None

    def to_dict(self):
        d = asdict(self); d["price_per_m2"] = self.price_per_m2
        return d
