"""Ước lượng tọa độ cho tin không có tọa độ thật (Alonhadat, Thư Viện Nhà Đất, Google...): tra đường + xã/huyện ghi trong tin.
Kết quả chỉ để xếp hạng/hiển thị khoảng cách ước lượng; KHÔNG bao giờ làm tin đủ điều kiện lên bảng chính."""
import re
from . import store, cancel
from .textnorm import norm
from .search import haversine_m

STREET_RE = re.compile(r"(duong|pho|hem|kiet|ngo|quoc lo|ql|dt|tinh lo|khu pho|thon|xom)\b")

def query_for(l) -> str:
    parts, seen = [], set()
    for p in re.split(r"[,;]", l.address or ""):
        p = p.strip()
        k = norm(p)
        if p and k not in seen:
            seen.add(k); parts.append(p)
    street = next((p for p in parts if STREET_RE.search(norm(p))), "")
    if not street:                       # không có tên đường/hẻm/thôn thì tra ra cả xã là vô nghĩa cho khoảng cách
        return ""
    rest = [p for p in parts if p != street][:2]
    q = ", ".join(x for x in ([street] + rest) if x)
    return q if len(q) >= 6 else ""

def estimate_points(candidates, center, max_dist_m=12000, max_new=8, geocoder=None, sleep=None):
    """candidates: [Listing] đã xếp ưu tiên. Trả {url: (lat, lng)}. Chỉ nhận điểm cách tâm <= max_dist_m (kiểm tra hợp lý)."""
    from . import geo
    geocoder = geocoder or geo.nominatim_search
    sleep = sleep or (lambda s: cancel.sleep(s))
    out, new = {}, 0
    for l in candidates:
        q = query_for(l)
        if not q:
            continue
        key = norm(q)
        found, pt = store.geocache_get(key)
        if not found:
            if new >= max_new:
                continue
            if new:
                sleep(1.1)
            pt = geocoder(q); new += 1
            store.geocache_put(key, pt)
        if pt and haversine_m(center[0], center[1], pt[0], pt[1]) <= max_dist_m:
            out[l.url] = pt
    return out
