import re
from .models import Listing
from .textnorm import AdminMap, norm, contains_phrase, core_name, province_aliases, province_conflict, norm_loc, core_loc, mentions_ward, district_conflict

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


LEVEL_ORDER = {"thon": 0, "xa": 1, "xa_moi": 2, "huyen": 3, "near": 4}

NOT_RESIDENTIAL = re.compile(r"(?<![a-z0-9])(can ho|chung cu|condotel|officetel|khach san|nha xuong|kho xuong|nha hang|resort|biet thu nghi duong)(?![a-z0-9])")

def parse_kinds(kind) -> set:
    """kind có thể là một loại ('dat') hoặc nhiều loại cách nhau dấu phẩy ('dat,nha')."""
    return {k.strip() for k in str(kind or "").split(",") if k.strip()}

def kind_ok(l: Listing, kinds: set) -> bool:
    """Chọn loại tài sản thì tin không rõ loại bị loại; khi KHÔNG cần căn hộ thì loại cả tin có chữ căn hộ/chung cư/khách sạn/nhà xưởng... trong tiêu đề."""
    if not kinds:
        return True
    if l.kind not in kinds:
        return False
    if "can_ho" not in kinds and NOT_RESIDENTIAL.search(norm(l.title)):
        return False
    return True

def ward_level(l: Listing, admin: AdminMap, xa: str, hay_loc: str):
    """'exact': tin nhắc đúng phường/xã người dùng nhập (hoặc đơn vị cũ nằm trong nó nếu đó là tên mới);
    'parent': chỉ nhắc phường/xã MỚI chứa phường cũ người dùng nhập (khác phường cũ); None: không nhắc. Luôn cần tiền tố phường/xã."""
    typed = core_loc(xa)
    if mentions_ward(hay_loc, typed):
        return "exact"
    if any(mentions_ward(hay_loc, core_loc(c)) for c in admin.children(xa)):
        return "exact"
    if any(mentions_ward(hay_loc, core_loc(c)) for c in admin.parents(xa)):
        return "parent"
    return None

def classify_location(l: Listing, admin: AdminMap, xa: str, huyen: str, tinh: str, thon: str = "", scope: str = "ward"):
    """Cấp khớp địa danh: 'thon' (cùng thôn/xóm) > 'xa' (cùng xã/phường như đã nhập) > 'xa_moi' (chỉ cùng phường MỚI, khác phường cũ; chỉ để
    tham khảo) > 'huyen' (cùng huyện, khác xã; chỉ khi scope='district') hoặc None (loại).
    Bắt buộc không thuộc tỉnh khác, không thuộc huyện/TP khác; khớp xã/phường cần tiền tố phường/xã (không nhận trùng tên đường hay tên thành phố)."""
    # Địa chỉ + tiêu đề là nơi đáng tin; chỉ dùng mô tả khi tin không có địa chỉ (tin Google/nhập tay)
    hay = norm(l.address + " " + l.title + ("" if l.address else " " + l.description))
    hay_loc = norm_loc(l.address + " " + l.title + ("" if l.address else " " + l.description))
    allowed = province_aliases(admin, tinh)
    if allowed and province_conflict(hay, allowed):
        return None
    def hit(name):
        return any(contains_phrase(hay, a) for a in admin.aliases(name))
    typed_districts = ({core_loc(huyen)} | {core_loc(a) for a in admin.aliases(huyen)}) if huyen.strip() else set()
    if xa.strip():
        lvl = ward_level(l, admin, xa, hay_loc)
        if lvl and not district_conflict(l.raw, hay_loc, typed_districts):
            if lvl == "parent":
                return "xa_moi"
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
        if not kind_ok(l, parse_kinds(kind)):        # có chọn loại tài sản thì tin không rõ loại cũng bị loại (tránh khách sạn, nhà xưởng, căn hộ...)
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

MAX_COORD_KM = 120      # tọa độ cách tâm quá 120 km (vd mặc định ở TP.HCM) coi là sai

def haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Khoảng cách đường chim bay (mét) giữa hai tọa độ."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def _street_key(l: Listing) -> str:
    raw = l.raw if isinstance(l.raw, dict) else {}
    return norm(str(raw.get("street_name") or (l.address or "").split(",")[0] or l.title))[:40]

def suspect_coords(items, min_listings: int = 3, min_streets: int = 3) -> set:
    """Tọa độ 'mặc định' của nguồn (tâm xã/thành phố khi người đăng không ghim): cùng một điểm (làm tròn ~100 m) lặp ở >= 3 tin có >= 3 tên đường khác nhau.
    Cụm tin ở cùng một dự án (cùng đường) KHÔNG bị coi là mặc định."""
    groups = {}
    for l in items:
        raw = l.raw if isinstance(l.raw, dict) else {}
        try:
            lat, lng = float(raw.get("latitude")), float(raw.get("longitude"))
        except (TypeError, ValueError):
            continue
        groups.setdefault((round(lat, 3), round(lng, 3)), []).append(_street_key(l))
    return {k for k, v in groups.items() if len(v) >= min_listings and len(set(v)) >= min_streets}

def listing_coords(l: Listing, bad=None):
    """(lat, lng) thật do nguồn cung cấp (hiện chỉ Chợ Tốt), hoặc None. Không suy đoán tọa độ. `bad`: tập tọa độ mặc định/lặp (suspect_coords) bị bỏ."""
    raw = l.raw if isinstance(l.raw, dict) else {}
    try:
        lat, lng = float(raw.get("latitude")), float(raw.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (8 < lat < 24 and 102 < lng < 110):
        return None
    if bad and (round(lat, 3), round(lng, 3)) in bad:
        return None
    return (lat, lng)

def select_near(items, exclude_urls, admin, tinh, lat, lng, radius_m, area=None, tol=0.5, land_type="", kind="", bad=None):
    """Tin KHÁC xã/phường nhưng có tọa độ thật nằm trong bán kính quanh thửa đất: [(Listing, distance_m)] gần nhất trước.
    Dùng cho cả bảng chính (khi tâm là ghim thật) lẫn Hàng chờ (khi tâm chỉ là ước lượng khu vực)."""
    allowed = province_aliases(admin, tinh)
    out = []
    for l in items:
        if l.url in exclude_urls:
            continue
        c = listing_coords(l, bad)
        if not c:
            continue
        d = haversine_m(lat, lng, c[0], c[1])
        if d > radius_m or d > MAX_COORD_KM * 1000:
            continue
        if allowed and province_conflict(norm(l.address + " " + l.title), allowed):
            continue
        if area and l.area_m2 and not (area * (1 - tol) <= l.area_m2 <= area * (1 + tol)):
            continue
        if not kind_ok(l, parse_kinds(kind)):
            continue
        if land_type and l.land_type and l.land_type != land_type:
            continue
        out.append((l, d))
    return sorted(out, key=lambda t: t[1])


def relevance(l: Listing, lv: str, dist_m, radius_m: float, area, street: str, kinds: set, tier: int):
    """Điểm 'sát thửa' 0-100 minh bạch, kèm từng thành phần: cấp địa danh, cùng đường, diện tích gần, khoảng cách (nếu có tọa độ), ngày đăng, đúng loại."""
    parts = {}
    parts["địa danh"] = {"thon": 30, "xa": 22, "xa_moi": 8, "near": 10, "huyen": 0}.get(lv, 0)
    if street and same_street(l, street):
        parts["cùng đường"] = 18
    if area and l.area_m2:
        parts["diện tích"] = round(15 * max(0.0, 1 - abs(l.area_m2 - area) / area))
    if dist_m is not None and radius_m:
        parts["khoảng cách"] = round(20 * max(0.0, 1 - dist_m / radius_m))
    parts["ngày đăng"] = {0: 8, 1: 4, 2: 1}.get(tier, 0)
    if kinds and l.kind in kinds:
        parts["đúng loại"] = 4
    return min(100, sum(parts.values())), parts
