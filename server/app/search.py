from .models import Listing
from .textnorm import AdminMap, norm, contains_phrase

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
