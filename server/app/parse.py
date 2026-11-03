"""Trích xuất giá, diện tích, mặt tiền, loại đất từ văn bản rao bán tự do."""
import re
from .textnorm import norm

NUM = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"

def _f(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):   # 1.200.000
        return float(re.sub(r"[.,]", "", s))
    return float(s.replace(",", "."))

def parse_price(text: str):
    t = norm(text, keep_num=True)
    m = re.search(NUM + r"\s*(ty|ti)\s*(?:" + NUM + r"\s*(?:tr|trieu)?)?", t)
    if m:
        v = _f(m.group(1)) * 1e9
        if m.group(3):
            tail = _f(m.group(3))
            v += tail * 1e6 if tail < 1000 else 0
        return v
    m = re.search(NUM + r"\s*(trieu|tr)\b(?!\s*/?\s*m)", t)
    if m:
        return _f(m.group(1)) * 1e6
    return None

def parse_area(text: str):
    t = norm(text, keep_num=True)
    m = re.search(NUM + r"\s*(ha|hecta)\b", t)
    if m:
        return _f(m.group(1)) * 10000
    m = re.search(NUM + r"\s*(m2|m 2|met vuong|mv)\b", t)
    if m:
        return _f(m.group(1))
    m = re.search(r"dien tich[: ]*" + NUM, t)
    if m:
        return _f(m.group(1))
    return None

def parse_frontage(text: str):
    t = norm(text, keep_num=True)
    m = re.search(r"(?:mat tien|ngang|mt)[: ]*" + NUM + r"\s*m\b", t)
    return _f(m.group(1)) if m else None

LAND_TYPES = [
    ("ONT", ["dat o", "tho cu", "ont", "dat tho cu"]),
    ("ODT", ["odt", "dat o do thi"]),
    ("CLN", ["cay lau nam", "cln", "dat vuon", "dat trong cay"]),
    ("BHK", ["cay hang nam", "bhk", "dat mau", "dat trong lua", "luc"]),
    ("RSX", ["dat rung", "rung san xuat", "rsx", "rung keo", "rung"]),
    ("NTS", ["nuoi trong thuy san", "nts", "dat ao"]),
    ("NN", ["dat nong nghiep", "dat nn"]),
]

def guess_land_type(text: str) -> str:
    t = " " + norm(text, keep_num=True) + " "
    for code, kws in LAND_TYPES:
        for k in kws:
            if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", t):
                return code
    return ""


KIND_LABEL = {"dat": "Đất", "nha": "Nhà", "can_ho": "Căn hộ"}

def guess_kind(url: str = "", title: str = "") -> str:
    """Phân loại tài sản theo đường dẫn (ưu tiên) rồi tiêu đề: can_ho / nha / dat / '' (không rõ)."""
    path = norm(url.split("//")[-1].split("/", 1)[-1].replace("-", " ").replace("/", " "))
    t = norm(title)
    for text in (path, t):
        if re.search(r"\b(can ho|chung cu|condotel|penthouse|duplex)\b", text) or re.search(r"\b\d+\s*(pn|phong ngu)\b", text):
            return "can_ho"
        if re.search(r"\b(nha rieng|nha mat|nha pho|nha cap|nha tro|biet thu|shophouse|lien ke|nha hem|nha \d|ban nha)\b", text):
            return "nha"
        if re.search(r"\b(ban dat|lo dat|dat nen|dat tho cu|dat o|dat vuon|dat rung|dat nong|dat trong)\b", text):
            return "dat"
    return ""
