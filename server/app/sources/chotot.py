"""Nguồn Chợ Tốt / Nhà Tốt qua API công khai dùng bởi chính website.

Đã kiểm chứng bằng tools/probe_chotot*.py: cg=1040 là "Đất"; lọc khu vực bằng region_v2 / area_v2
(không dùng từ khoá q vì q chỉ khớp chữ trong tiêu đề/nội dung nên bỏ sót nhiều tin).
Tuân thủ điều khoản sử dụng của nguồn; hạn chế tần suất gọi.
"""
import datetime as dt, time
import requests
from .. import cancel
from .base import Source
from ..models import Listing
from ..parse import parse_frontage, guess_land_type, guess_kind
from ..textnorm import norm, contains_phrase

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

    known_urls: set = frozenset()       # link đã lưu (máy chủ gán trước mỗi lần thu thập); dùng cho cào tăng dần
    STOP_AFTER_KNOWN = 8                # gặp liên tiếp ngần này tin đã lưu thì dừng (API trả tin mới nhất trước)

    def _paged(self, limit, max_age_days, incremental=False, **filters) -> list[Listing]:
        """Phân trang lùi theo thời gian (API trả tin mới nhất trước) tới khi đủ `limit`, hết tin, gặp tin cũ hơn `max_age_days`,
        hoặc (incremental) gặp liên tiếp nhiều tin ĐÃ LƯU: khi đó các tin cũ hơn gần như chắc đã có, khỏi tải lại."""
        out, offset, stop, consec = [], 0, False, 0
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
                if incremental and f"https://www.nhatot.com/{a.get('list_id')}.htm" in self.known_urls:
                    consec += 1
                    if consec >= self.STOP_AFTER_KNOWN:
                        stop = True
                        break
                    continue
                consec = 0
                out.append(_to_listing(a, self.name, now))
            offset += len(ads)
            cancel.sleep(1.5)   # lịch sự với máy chủ nguồn
        return out[:limit]

    def search(self, keywords: str, limit: int = 50, max_age_days: int | None = None, incremental: bool = False) -> list[Listing]:
        return self._paged(limit, max_age_days, incremental, q=keywords)

    def discover_regions(self, names: list[str], allowed: set | None = None) -> dict[int, str]:
        """Từ tên địa danh người dùng nhập, tìm mã tỉnh (region_v2) Chợ Tốt dùng: tìm theo từ khoá rồi lấy mã tỉnh của các tin mà tên
        cũ/mới của tỉnh/huyện/phường khớp địa danh đó. `allowed`: tên các tỉnh hợp lệ (đã chuẩn hoá); tỉnh khác bị bỏ
        (tránh lấy nhầm cả tỉnh khác chỉ vì có xã trùng tên)."""
        found: dict[int, str] = {}
        for name in names:
            n = norm(name)
            if not n:
                continue
            for a in self._page(q=name):
                fields = (a.get("region_name"), a.get("region_name_v3"), a.get("area_name"),
                          a.get("area_name_v3"), a.get("ward_name"), a.get("ward_name_v3"))
                if not (any(n in norm(f or "") for f in fields) and a.get("region_v2")):
                    continue
                if allowed:
                    rn = norm((a.get("region_name") or "") + " " + (a.get("region_name_v3") or ""))
                    if not any(contains_phrase(rn, x) for x in allowed):
                        continue
                found[a["region_v2"]] = a.get("region_name") or str(a["region_v2"])
            cancel.sleep(1.0)
        return found

    def discover_codes(self, region_v2: int, ward_aliases: set, district_aliases: set):
        """Tìm mã huyện (area_v2) và phường/xã (ward) của Chợ Tốt từ các tin có tên khớp. -> ({(area_v2, ward)}, {area_v2})"""
        wards, areas = set(), set()
        for name in sorted(ward_aliases | district_aliases):
            for a in self._page(q=name, region_v2=region_v2):
                wn = norm((a.get("ward_name") or "") + " | " + (a.get("ward_name_v3") or ""))
                an = norm((a.get("area_name") or "") + " | " + (a.get("area_name_v3") or ""))
                if ward_aliases and any(contains_phrase(wn, w) for w in ward_aliases) and a.get("area_v2") and a.get("ward"):
                    wards.add((a["area_v2"], a["ward"]))
                if district_aliases and any(contains_phrase(an, d) for d in district_aliases) and a.get("area_v2"):
                    areas.add(a["area_v2"])
            cancel.sleep(1.0)
        # Xã/phường trùng tên nhiều nơi: nếu đã xác định được huyện, chỉ giữ phường thuộc huyện đó
        if areas:
            wards = {(a, w) for a, w in wards if a in areas}
        # quét thêm tin của chính huyện đã tìm thấy để lấy đúng mã phường trong huyện đó
        if ward_aliases and areas:
            for area_c in sorted(areas):
                for offset in (0, 20, 40):
                    ads = self._page(region_v2=region_v2, area_v2=area_c, o=offset)
                    for a in ads:
                        wn = norm((a.get("ward_name") or "") + " | " + (a.get("ward_name_v3") or ""))
                        if a.get("ward") and any(contains_phrase(wn, w) for w in ward_aliases):
                            wards.add((area_c, a["ward"]))
                    if len(ads) < 20:
                        break
                    cancel.sleep(1.0)
        return wards, areas

    def search_codes(self, region_v2: int, area_v2=None, ward=None, limit: int = 100, max_age_days: int | None = None, incremental: bool = False):
        f = {"region_v2": region_v2}
        if area_v2:
            f["area_v2"] = area_v2
        if ward:
            f["ward"] = ward
        return self._paged(limit, max_age_days, incremental, **f)

    def search_region(self, region_v2: int, limit: int, max_age_days: int | None = None, incremental: bool = False) -> list[Listing]:
        return self._paged(limit, max_age_days, incremental, region_v2=region_v2)
