"""Học bảng ánh xạ đơn vị hành chính cũ -> mới từ chính dữ liệu tin đã thu thập (không dựa vào trí nhớ).
Chợ Tốt trả cả tên cũ lẫn tên mới (ward_name / ward_name_v3, area_name / area_name_v3); Alonhadat ghi địa chỉ mới và địa chỉ cũ."""
import re

UNIT = re.compile(r"^\s*(xã|phường|thị trấn)\b", re.I)

def _first_unit(addr: str):
    for part in str(addr or "").split(","):
        if UNIT.match(part):
            return part.strip()
    return None

def learn_pairs(listings) -> set:
    """-> {(tên cũ, tên mới)} của xã/phường và huyện/thị xã/thành phố."""
    pairs = set()
    for l in listings:
        raw = l.raw if isinstance(l.raw, dict) else {}
        for o, n in (("ward_name", "ward_name_v3"), ("area_name", "area_name_v3")):
            a, b = raw.get(o), raw.get(n)
            if a and b and str(a).strip() != str(b).strip():
                pairs.add((str(a).strip(), str(b).strip()))
        old, new = _first_unit(raw.get("old_address")), _first_unit(raw.get("new_address"))
        if old and new and old != new:
            pairs.add((old, new))
    return pairs
