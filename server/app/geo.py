"""Đọc tọa độ từ link Google Maps; mở link rút gọn an toàn (chỉ tên miền Google, chặn địa chỉ nội bộ)."""
import re, urllib.parse
import requests

ALLOWED_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co", "maps.google.com", "www.google.com", "google.com", "www.google.com.vn", "google.com.vn")
SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co")

def in_vietnam(lat, lng):
    return 8 <= lat <= 24 and 102 <= lng <= 110.5

def host_ok(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    h = (u.hostname or "").lower()
    if u.scheme != "https" or u.port not in (None, 443) or u.username:
        return False
    if h in ALLOWED_HOSTS:
        return True
    return bool(re.fullmatch(r"(www\.)?google\.[a-z]{2,3}(\.[a-z]{2})?", h))

def parse_maps_url(url: str):
    """-> (lat, lng, loai) hoặc None. Ưu tiên ghim !3d!4d, rồi q=/ll=, cuối cùng @ (tâm màn hình)."""
    t = urllib.parse.unquote(url)
    m = list(re.finditer(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", t))
    if m:
        return float(m[-1].group(1)), float(m[-1].group(2)), "pin"
    m = re.search(r"[?&](?:q|ll|query|center|destination)=(?:loc:)?(-?\d+\.\d+)[,+ ]\s*(-?\d+\.\d+)", t)
    if m:
        return float(m.group(1)), float(m.group(2)), "query"
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", t)
    if m:
        return float(m.group(1)), float(m.group(2)), "center"
    return None

def resolve_short_url(url: str, max_hops: int = 5, session=None):
    """Theo dõi chuyển hướng từng bước (mỗi bước đều phải là tên miền Google, https). -> (final_url, loi hoặc None)."""
    s = session or requests
    cur = url
    for _ in range(max_hops + 1):
        if not host_ok(cur):
            return cur, "Link không thuộc tên miền Google Maps nên không mở."
        if parse_maps_url(cur):
            return cur, None
        r = s.get(cur, allow_redirects=False, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.close()
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            cur = urllib.parse.urljoin(cur, r.headers["Location"])
            continue
        return cur, None if parse_maps_url(cur) else "Link không chứa tọa độ."
    return cur, "Link chuyển hướng quá nhiều lần."
