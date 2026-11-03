"""Nguồn Chợ Tốt / Nhà Tốt qua API công khai dùng bởi chính website.

Đã kiểm chứng bằng tools/probe_chotot*.py: cg=1040 là "Đất"; lọc khu vực bằng region_v2 / area_v2
(không dùng từ khoá q vì q chỉ khớp chữ trong tiêu đề/nội dung nên bỏ sót nhiều tin).
Tuân thủ điều khoản sử dụng của nguồn; hạn chế tần suất gọi.
"""
import datetime as dt, time
import requests
from .base import Source
from ..models import Listing
from ..parse import parse_frontage, guess_land_type, guess_kind
from ..textnorm import norm

API = "https://gateway.chotot.com/v1/public/ad-listing"
CATEGORY_LAND = 1000      # 1000 = toàn bộ BĐS (1040 đất, 1020 nhà ở, 1010 căn hộ)
HEADERS = {"User-Agent": "Mozilla/5.0 (khaogia-tham-dinh)", "Accept": "application/json"}

def _to_listing(a: dict, source: str, now: str) -> Listing:
    # Địa chỉ gồm cả tên cũ và tên mới (v3) sau sáp nhập để khớp bất kể người dùng nhập tên nào
    addr = ", ".join(dict.fromkeys(x for x in (
        a.get("street_name"), a.get("ward_name"), a.get("ward_name_v3"), a.get("area_name"),
        a.get("region_name"), a.get("region_name_v3")) if x))
    text = (a.get("subject", "") or "") + " " + (a.get("body", "") or "")
    posted = ""
    if a.get("list_time"):
        posted = dt.datetime.fromtimestamp(a["list_time"] / 1000).isoformat(timespec="seconds")
    return Listing(
        source=source, url=f"https://www.nhatot.com/{a.get('list_id')}.htm",
        title=a.get("subject", ""), address=addr, description=a.get("body", "") or "",
        price_vnd=a.get("price"), area_m2=a.get("size") or a.get("land_area"),
        frontage_m=parse_frontage(text), land_type=guess_land_type(text),
        kind={1040: "dat", 1020: "nha", 1010: "can_ho"}.get(a.get("category")) or guess_kind("", a.get("subject", "") or ""),
        posted_at=posted, fetched_at=now, raw=a)

class Chotot(Source):
    name = "chotot"

    def _page(self, **params):
        p = {"cg": CATEGORY_LAND, "limit": 20, "st": "s", **params}   # st=s: tin bán
        r = requests.get(API, params=p, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.json().get("ads", [])

    def _paged(self, limit, max_age_days, **filters) -> list[Listing]:
        """Phân trang lùi theo thời gian (API trả tin mới nhất trước) tới khi đủ `limit`,
        hết tin, hoặc gặp tin cũ hơn `max_age_days`."""
        out, offset, stop = [], 0, False
        cutoff = (dt.datetime.now() - dt.timedelta(days=max_age_days)).timestamp() * 1000 if max_age_days else None
        while len(out) < limit and not stop:
            ads = self._page(o=offset, **filters)
            if not ads:
                break
            now = dt.datetime.now().isoformat(timespec="seconds")
            for a in ads:
                if cutoff and a.get("list_time") and a["list_time"] < cutoff:
                    stop = True
                    break
                out.append(_to_listing(a, self.name, now))
            offset += len(ads)
            time.sleep(1.5)   # lịch sự với máy chủ nguồn
        return out[:limit]

    def search(self, keywords: str, limit: int = 50, max_age_days: int | None = None) -> list[Listing]:
        return self._paged(limit, max_age_days, q=keywords)

    def discover_regions(self, names: list[str]) -> dict[int, str]:
        """Từ tên địa danh người dùng nhập, tìm mã tỉnh (region_v2) Chợ Tốt dùng:
        tìm theo từ khoá rồi lấy mã tỉnh của các tin mà tên cũ/mới của tỉnh/huyện/phường khớp địa danh đó."""
        found: dict[int, str] = {}
        for name in names:
            n = norm(name)
            if not n:
                continue
            for a in self._page(q=name):
                fields = (a.get("region_name"), a.get("region_name_v3"), a.get("area_name"),
                          a.get("area_name_v3"), a.get("ward_name"), a.get("ward_name_v3"))
                if any(n in norm(f or "") for f in fields) and a.get("region_v2"):
                    found[a["region_v2"]] = a.get("region_name") or str(a["region_v2"])
            time.sleep(1.0)
        return found

    def search_region(self, region_v2: int, limit: int, max_age_days: int | None = None) -> list[Listing]:
        return self._paged(limit, max_age_days, region_v2=region_v2)
