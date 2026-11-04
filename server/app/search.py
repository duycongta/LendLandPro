from .models import Listing
from .textnorm import AdminMap, norm, contains_phrase, core_name, province_aliases, province_conflict

def location_terms(admin: AdminMap, xa: str, huyen: str, tinh: str):
    return [admin.aliases(x) for x in (xa, huyen, tinh) if x.strip()]

def build_keywords(xa: str, huyen: str, tinh: str) -> str:
    return " ".join(x for x in (xa, huyen, tinh) if x.strip())

def street_core(street: str) -> str:
    n = norm(street)
    for p in ("duong", "pho", "dg", "hem", "kiet"):
        if n.startswith(p + " "):
            n = n[len(p) + 1:]
    return n

def same_street(l: Listing, street: str) -> bool:
    c = street_core(street)
    return bool(c) and contains_phrase(norm(l.address + " " + l.title + " " + l.description), c)

def rank(items, street="", area=None):
    """Cùng đường lên trước; sau đó diện tích gần với tài sản cần định giá."""
    def key(l):
        s = 0 if (street and same_street(l, street)) else 1
        d = abs(l.area_m2 - area) / area if (area and l.area_m2) else 9
        return (s, d)
    return sorted(items, key=key)

def matches_location(l: Listing, groups: list[set[str]], need: int) -> bool:
    """Tin phải khớp ít nhất `need` cấp (xã/huyện/tỉnh), mỗi cấp khớp bất kỳ tên cũ hoặc mới."""
    hay = norm(l.address + " " + l.title + " " + l.description)
    hits = sum(any(contains_phrase(hay, a) for a in g) for g in groups)
    return hits >= min(need, len(groups))

def filter_listings(items, groups, need=1, area=None, tol=0.5, land_type="", frontage_min=None, kind=""):
    out = []
    for l in items:
        if groups and not matches_location(l, groups, need):
            continue
        if area and l.area_m2 and not (area * (1 - tol) <= l.area_m2 <= area * (1 + tol)):
            continue
        if kind and l.kind and l.kind != kind:
            continue
        if land_type and l.land_type and l.land_type != land_type:
            continue
        out.append(l)
    # bỏ trùng: cùng giá + diện tích + (url hoặc tiêu đề)
    seen, uniq = set(), []
    for l in out:
        key = (l.price_vnd, l.area_m2, norm(l.title)[:40])
        if key in seen or (l.url and ("u", l.url) in seen):
            continue
        seen.add(key); seen.add(("u", l.url)); uniq.append(l)
    return uniq


LEVEL_ORDER = {"thon": 0, "xa": 1, "huyen": 2, "near": 3}

def classify_location(l: Listing, admin: AdminMap, xa: str, huyen: str, tinh: str, thon: str = "", scope: str = "ward"):
    """Cấp khớp địa danh của tin so với tài sản: 'thon' (cùng thôn/xóm) > 'xa' (cùng xã/phường) > 'huyen' (cùng huyện, khác xã; chỉ khi
    scope='district') hoặc None (loại). Bắt buộc cùng xã/phường (hoặc cùng huyện nếu người dùng không nhập xã) và không thuộc tỉnh khác."""
    # Địa chỉ + tiêu đề là nơi đáng tin; chỉ dùng mô tả khi tin không có địa chỉ (tin Google/nhập tay)
    hay = norm(l.address + " " + l.title + ("" if l.address else " " + l.description))
    allowed = province_aliases(admin, tinh)
    if allowed and province_conflict(hay, allowed):
        return None
    def hit(name):
        return any(contains_phrase(hay, a) for a in admin.aliases(name))
    if xa.strip():
        if hit(xa):
            full = norm(l.address + " " + l.title + " " + l.description)
            t = core_name(thon) if thon.strip() else ""
            return "thon" if (t and contains_phrase(full, t)) else "xa"
        if scope == "district" and huyen.strip() and hit(huyen):
            return "huyen"
        return None
    if huyen.strip():
        return "xa" if hit(huyen) else None
    return "xa"

def select_comps(items, admin, xa, huyen, tinh, thon="", scope="ward", area=None, tol=0.5, land_type="", kind="", street=""):
    """Lọc + xếp hạng tài sản so sánh: [(Listing, level)]. Thứ tự: cấp địa danh (thôn > xã > huyện), cùng đường, diện tích gần nhất."""
    picked = []
    for l in items:
        lvl = classify_location(l, admin, xa, huyen, tinh, thon, scope)
        if lvl is None:
            continue
        if area and l.area_m2 and not (area * (1 - tol) <= l.area_m2 <= area * (1 + tol)):
            continue
        if kind and l.kind != kind:                  # có chọn loại tài sản thì tin không rõ loại cũng bị loại (tránh khách sạn, nhà xưởng...)
            continue
        if land_type and l.land_type and l.land_type != land_type:
            continue
        picked.append((l, lvl))
    seen, uniq = set(), []
    for l, lvl in picked:
        key = (l.price_vnd, l.area_m2, norm(l.title)[:40])
        if key in seen or (l.url and ("u", l.url) in seen):
            continue
        seen.add(key); seen.add(("u", l.url)); uniq.append((l, lvl))
    def key(t):
        l, lvl = t
        st = 0 if (street and same_street(l, street)) else 1
        d = abs(l.area_m2 - area) / area if (area and l.area_m2) else 9
        return (LEVEL_ORDER[lvl], st, d)
    return sorted(uniq, key=key)


import math

def haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Khoảng cách đường chim bay (mét) giữa hai tọa độ."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def listing_coords(l: Listing):
    """(lat, lng) thật do nguồn cung cấp (hiện chỉ Chợ Tốt), hoặc None. Không suy đoán tọa độ."""
    raw = l.raw if isinstance(l.raw, dict) else {}
    try:
        lat, lng = float(raw.get("latitude")), float(raw.get("longitude"))
    except (TypeError, ValueError):
        return None
    return (lat, lng) if (8 < lat < 24 and 102 < lng < 110) else None

def select_near(items, exclude_urls, admin, tinh, lat, lng, radius_m, area=None, tol=0.5, land_type="", kind=""):
    """Tin KHÁC xã/phường nhưng có tọa độ thật nằm trong bán kính quanh thửa đất: [(Listing, distance_m)] gần nhất trước.
    Chỉ để tham khảo (Hàng chờ), không tự đưa vào bảng chính."""
    allowed = province_aliases(admin, tinh)
    out = []
    for l in items:
        if l.url in exclude_urls:
            continue
        c = listing_coords(l)
        if not c:
            continue
        d = haversine_m(lat, lng, c[0], c[1])
        if d > radius_m:
            continue
        if allowed and province_conflict(norm(l.address + " " + l.title), allowed):
            continue
        if area and l.area_m2 and not (area * (1 - tol) <= l.area_m2 <= area * (1 + tol)):
            continue
        if kind and l.kind != kind:
            continue
        if land_type and l.land_type and l.land_type != land_type:
            continue
        out.append((l, d))
    return sorted(out, key=lambda t: t[1])
