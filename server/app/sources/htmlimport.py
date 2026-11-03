"""Đọc trang kết quả tìm kiếm đã lưu từ trình duyệt (Ctrl+S, "Trang web, chỉ HTML").

Cách này không gửi yêu cầu tự động tới các trang web nên không vướng chặn bot; người dùng tự mở trang.
Hỗ trợ: alonhadat.com.vn, batdongsan.com.vn. Nhận diện nguồn theo cấu trúc HTML.
"""
import datetime as dt, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from ..models import Listing
from ..parse import parse_price, parse_area, parse_frontage, guess_land_type, guess_kind
from ..textnorm import norm

NOT_LAND = re.compile(r"(^|-)(nha|can-ho|chung-cu|biet-thu|villa|shophouse|nha-rieng|van-phong|cho-thue)(-|$)")

def _txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""

def _num(s: str):
    """'87,5 m²' -> 87.5 ; '1.200' -> 1200"""
    m = re.search(r"\d[\d.,]*", s or "")
    if not m:
        return None
    t = m.group(0).rstrip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        return float(t.replace(".", ""))
    return float(t.replace(",", "."))

def _is_land(slug_or_url: str, title: str, strict: bool = False) -> bool:
    """strict: chỉ tin cậy danh mục trong đường dẫn (không đoán theo tiêu đề)."""
    if re.search(r"\b\d+\s*(pn|phong ngu)\b", norm(title)):   # có số phòng ngủ -> căn hộ/nhà, dù đăng sai mục
        return False
    slug = slug_or_url.rsplit("/", 1)[-1] if slug_or_url else ""
    path = slug_or_url.split("//")[-1].split("/", 1)[-1] if slug_or_url else ""
    if re.search(r"(^|/|-)ban-dat(-|/|$)", path) or re.search(r"(^|-)(lo-dat|dat-nen|dat-tho-cu|dat-o|dat-vuon|dat-rung)(-|$)", slug):
        return True
    if strict:
        return False
    t = norm(title)
    return bool(re.search(r"\bdat\b", t)) and not re.search(r"\b(can ho|chung cu|biet thu|nha pho|nha cap|nha \d|nha mat)\b", t) \
        and not NOT_LAND.search(slug)

def detect(html: str) -> str:
    if 'class="property-item"' in html or "property-item" in html and "itemprop=\"datePosted\"" in html:
        return "alonhadat"
    if "js__card" in html and "re__card" in html:
        return "batdongsan"
    if "KinhDoanhNhaDat-index-post-title" in html:
        return "thuviennhadat"
    if 'class="listing-card' in html and "listing-card__title" in html:
        return "raobannhadat"
    return ""

def parse_alonhadat(html: str, only_land=False) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    now = dt.datetime.now().isoformat(timespec="seconds")
    out = []
    for it in soup.select("article.property-item"):
        a = it.select_one("a.link[href]") or it.select_one("a[href]")
        if not a:
            continue
        url = a["href"]
        title = _txt(it.select_one(".property-title"))
        if only_land and not _is_land(url, title):
            continue
        price_el = it.select_one('[itemprop="price"]')
        price = float(price_el["content"]) if price_el is not None and price_el.get("content", "").replace(".", "").isdigit() else parse_price(_txt(price_el))
        area_el = it.select_one('[itemprop="floorSize"] [itemprop="value"]')
        area = _num(_txt(area_el)) if area_el else None
        new_addr = _txt(it.select_one("p.new-address"))
        old_addr = _txt(it.select_one("p.old-address")).replace("(cũ)", "").strip()
        brief = _txt(it.select_one(".brief")).replace("<< Xem chi tiết >>", "").strip()
        dp = it.select_one('[itemprop="datePosted"]')
        out.append(Listing(
            source="alonhadat", url=url, title=title,
            address=", ".join(x for x in (old_addr, new_addr) if x), description=brief,
            price_vnd=price, area_m2=area, frontage_m=parse_frontage(title + " " + brief),
            land_type=guess_land_type(title + " " + brief + " " + url.replace("-", " ")),
            posted_at=dp.get("datetime", "") if dp is not None else "", fetched_at=now,
            raw={"title": title, "price_text": _txt(price_el), "area_text": _txt(area_el), "old_address": old_addr, "new_address": new_addr}))
    return out

def _bds_posted(txt: str, today: dt.date) -> str:
    t = norm(txt)
    if "hom nay" in t:
        return today.isoformat()
    if "hom qua" in t:
        return (today - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*(gio|phut|ngay|tuan|thang|nam)", t)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return (today - dt.timedelta(days={"gio": 0, "phut": 0, "ngay": 1, "tuan": 7, "thang": 30, "nam": 365}[u] * n)).isoformat()
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", txt)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""

def parse_batdongsan(html: str, base="https://batdongsan.com.vn", only_land=False) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    now = dt.datetime.now(); today = now.date(); now_s = now.isoformat(timespec="seconds")
    out = []
    for c in soup.select("div.js__card"):
        a = c.select_one("a.js__product-link-for-product-id[href]") or c.select_one("a[href*='-pr']")
        if not a:
            continue
        url = urljoin(base, a["href"])
        title = _txt(c.select_one(".re__card-title")) or a.get("title", "")
        if only_land and not _is_land(url, title):
            continue
        price_txt = _txt(c.select_one(".re__card-config-price"))
        area_txt = _txt(c.select_one(".re__card-config-area"))
        price = parse_price(price_txt) if "thoa thuan" not in norm(price_txt) else None
        price = round(price) if price else None
        loc = _txt(c.select_one(".re__card-location"))
        desc = _txt(c.select_one(".re__card-description"))
        out.append(Listing(
            source="batdongsan", url=url, title=title, address=loc, description=desc,
            price_vnd=price, area_m2=_num(area_txt), frontage_m=parse_frontage(title + " " + desc),
            land_type=guess_land_type(title + " " + desc + " " + url.rsplit("/", 1)[-1].replace("-", " ")),
            posted_at=_bds_posted(_txt(c.select_one(".re__card-published-info-published-at")), today), fetched_at=now_s,
            raw={"title": title, "price_text": price_txt, "area_text": area_txt, "location": loc,
                 "price_per_m2_text": _txt(c.select_one(".re__card-config-price_per_m2"))}))
    return out

def _slug_words(url: str, level: int | None = None) -> str:
    """Địa danh ẩn trong đường dẫn, vd .../ban-dat-xa-phuoc-thuan-huyen-tuy-phuoc-binh-dinh-... -> chữ thường không dấu."""
    path = url.split("//")[-1].split("/", 1)[-1].replace("chi-tiet-tin/", "")
    parts = path.split("/")
    return " ".join(p.replace("-", " ") for p in (parts if level is None else parts[:level]))

def parse_thuviennhadat(html: str, base="https://thuviennhadat.vn", only_land=False) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    now = dt.datetime.now(); today = now.date(); now_s = now.isoformat(timespec="seconds")
    out = []
    for tt in soup.select(".KinhDoanhNhaDat-index-post-title"):
        a = tt.find_parent("a")
        wrap = a.parent if a else None
        if not a or not a.get("href") or wrap is None:
            continue
        url = urljoin(base, a["href"])
        title = a.get("title") or _txt(tt)
        if only_land and not _is_land(url, title, strict=True):
            continue
        hl = [_txt(x) for x in wrap.select(".highlight")]
        price_txt = hl[0] if hl else ""
        area_txt = hl[1] if len(hl) > 1 else ""
        price = parse_price(price_txt) if "thoa thuan" not in norm(price_txt) else None
        loc = _txt(wrap.select_one(".KinhDoanhNhaDat-index-post-address"))
        out.append(Listing(
            source="thuviennhadat", url=url, title=title,
            address=", ".join(x for x in (loc, _slug_words(url, 1)) if x),   # đoạn đầu đường dẫn chứa phường/xã
            price_vnd=round(price) if price else None, area_m2=_num(area_txt) if "m" in area_txt else None,
            frontage_m=parse_frontage(title), land_type=guess_land_type(title + " " + _slug_words(url)),
            posted_at=_bds_posted(_txt(wrap.select_one(".post-date")), today), fetched_at=now_s,
            raw={"title": title, "price_text": price_txt, "area_text": area_txt, "location": loc}))
    return out

def parse_raobannhadat(html: str, base="https://raobannhadat.vn", only_land=False) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    now = dt.datetime.now(); today = now.date(); now_s = now.isoformat(timespec="seconds")
    out = []
    for c in soup.select("article.listing-card"):
        a = c.select_one(".listing-card__title a[href]")
        if not a:
            continue
        url = urljoin(base, a["href"])
        title = _txt(a)
        if only_land and not _is_land(url, title, strict=True):
            continue
        price_txt = _txt(c.select_one(".price")); area_txt = _txt(c.select_one(".area"))
        price = parse_price(price_txt) if "thoa thuan" not in norm(price_txt) else None
        loc = _txt(c.select_one(".listing-card__addr"))
        out.append(Listing(
            source="raobannhadat", url=url, title=title,
            address=", ".join(x for x in (loc, _slug_words(url)) if x),   # địa chỉ trên thẻ chỉ có tỉnh; đường dẫn có xã/huyện
            price_vnd=round(price) if price else None, area_m2=_num(area_txt),
            frontage_m=parse_frontage(title), land_type=guess_land_type(title + " " + _slug_words(url)),
            posted_at=_bds_posted(_txt(c.select_one(".time")), today), fetched_at=now_s,
            raw={"title": title, "price_text": price_txt, "area_text": area_txt, "location": loc,
                 "price_per_m2_text": _txt(c.select_one(".ppm"))}))
    return out

def parse_saved_html(html: str, only_land=False) -> tuple[str, list[Listing]]:
    kind = detect(html)
    kind_, items = _dispatch(kind, html, only_land)
    for l in items:
        l.kind = guess_kind(l.url, l.title)
    return kind_, items

def _dispatch(kind, html, only_land):
    if kind == "alonhadat":
        return kind, parse_alonhadat(html, only_land)
    if kind == "batdongsan":
        return kind, parse_batdongsan(html, only_land=only_land)
    if kind == "thuviennhadat":
        return kind, parse_thuviennhadat(html, only_land=only_land)
    if kind == "raobannhadat":
        return kind, parse_raobannhadat(html, only_land=only_land)
    return "", []
