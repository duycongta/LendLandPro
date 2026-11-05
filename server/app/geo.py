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


# ---- Đường/hẻm gần vị trí (OpenStreetMap Overpass) ----
import math

ALLEY_HIGHWAY = {"service", "living_street", "track", "path", "footway", "pedestrian"}
ALLEY_PREFIX = ("hem", "kiet", "ngo", "ngach")

def _dist_point_polyline_m(lat, lng, geom):
    """Khoảng cách (m) từ điểm tới đường gấp khúc [{lat,lon},...], tính trên mặt phẳng cục bộ (đủ chính xác trong vài chục mét)."""
    k = 111320.0
    cx = math.cos(math.radians(lat))
    pts = [((g["lon"] - lng) * k * cx, (g["lat"] - lat) * k) for g in geom]
    if not pts:
        return None
    if len(pts) == 1:
        return math.hypot(*pts[0])
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / L2))
        best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
    return best

def roads_from_overpass(elements, lat, lng, limit=4):
    """-> [{name, distance_m, highway, alley}] gần nhất trước, mỗi tên đường một dòng. alley=True khi tên bắt đầu bằng Hẻm/Kiệt/Ngõ hoặc loại đường là lối nhỏ."""
    from .textnorm import norm
    best = {}
    for e in elements or []:
        tags = e.get("tags") or {}
        name = (tags.get("name") or "").strip()
        d = _dist_point_polyline_m(lat, lng, e.get("geometry") or [])
        if not name or d is None:
            continue
        if name not in best or d < best[name]["distance_m"]:
            n = norm(name)
            best[name] = {"name": name, "distance_m": round(d), "highway": tags.get("highway", ""),
                          "alley": tags.get("highway", "") in ALLEY_HIGHWAY or any(n.startswith(p + " ") for p in ALLEY_PREFIX)}
    return sorted(best.values(), key=lambda r: r["distance_m"])[:limit]

OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")

def fetch_overpass_roads(lat, lng, radius_m=60, session=None):
    import requests
    s = session or requests
    q = f'[out:json][timeout:15];way(around:{int(radius_m)},{lat},{lng})["highway"]["name"];out geom;'
    last = None
    for url in OVERPASS_URLS:
        try:
            r = s.post(url, data={"data": q}, timeout=20, headers={"User-Agent": "LendLandPro/1.0 (cong cu khao sat gia BDS)"})
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:
            last = e
    raise last


# ---- Tra địa danh từ tọa độ: chuỗi dự phòng Nominatim -> Photon -> Overpass (chạy từ máy chủ) ----
UA = {"User-Agent": "LendLandPro/1.0 (cong cu khao sat gia BDS)"}

def parse_nominatim(a: dict) -> dict:
    return {"ward": a.get("suburb") or a.get("village") or a.get("quarter") or a.get("neighbourhood") or a.get("hamlet") or "",
            "district": a.get("county") or a.get("city_district") or a.get("town") or a.get("city") or "",
            "province": a.get("state") or a.get("province") or ""}

def parse_photon(j: dict) -> dict:
    """Photon (dữ liệu OpenStreetMap): tên phường/xã nằm ở locality hoặc district; huyện ở county hoặc city; tỉnh ở state. Cách gán này chưa kiểm chứng
    trên dữ liệu thật của Việt Nam nên kết quả được ghi chú là cần đối chiếu."""
    feats = (j or {}).get("features") or []
    p = (feats[0].get("properties") if feats else None) or {}
    return {"ward": p.get("locality") or p.get("district") or "", "district": p.get("county") or p.get("city") or "", "province": p.get("state") or ""}

def parse_overpass_areas(elements) -> dict:
    """Ranh giới hành chính chứa điểm: admin_level 8 = xã/phường, 6 = huyện/thị xã/thành phố, 4 = tỉnh (quy ước OpenStreetMap Việt Nam)."""
    lv = {}
    for e in elements or []:
        t = e.get("tags") or {}
        if t.get("admin_level") in ("4", "6", "8") and t.get("name"):
            lv.setdefault(t["admin_level"], t["name"])
    return {"ward": lv.get("8", ""), "district": lv.get("6", ""), "province": lv.get("4", "")}

def _complete(r: dict) -> bool:
    return bool((r.get("ward") or r.get("district")) and r.get("province"))

def reverse_chain(lat, lng, session=None, providers=None):
    """Thử lần lượt các nguồn, lấy kết quả đầu tiên có (xã/phường hoặc huyện) và tỉnh. -> {ok, ward, district, province, source, tried[]}"""
    import requests
    s = session or requests
    def nominatim():
        r = s.get("https://nominatim.openstreetmap.org/reverse", timeout=12, headers=UA,
                  params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1, "accept-language": "vi"})
        r.raise_for_status(); return parse_nominatim(r.json().get("address") or {})
    def photon():
        r = s.get("https://photon.komoot.io/reverse", timeout=12, headers=UA, params={"lat": lat, "lon": lng})
        r.raise_for_status(); return parse_photon(r.json())
    def overpass():
        q = f'[out:json][timeout:15];is_in({lat},{lng})->.a;area.a[boundary=administrative][admin_level~"^(4|6|8)$"];out tags;'
        last = None
        for url in OVERPASS_URLS:
            try:
                r = s.post(url, data={"data": q}, timeout=20, headers=UA); r.raise_for_status()
                return parse_overpass_areas(r.json().get("elements", []))
            except Exception as e:
                last = e
        raise last
    chain = providers or [("OpenStreetMap Nominatim", nominatim), ("Photon (OpenStreetMap)", photon), ("Overpass (ranh giới hành chính OpenStreetMap)", overpass)]
    tried = []
    for name, fn in chain:
        try:
            r = fn()
        except Exception as e:
            tried.append(f"{name}: {type(e).__name__}"); continue
        if _complete(r):
            return {"ok": True, **r, "source": name, "tried": tried}
        tried.append(f"{name}: kết quả thiếu xã/phường hoặc tỉnh")
    return {"ok": False, "error": "Các nguồn đều không trả đủ địa danh (" + "; ".join(tried) + ")", "tried": tried}
