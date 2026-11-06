"""Tự động mở trang kết quả tìm kiếm theo tỉnh của các trang tin rao rồi đọc bằng htmlimport.

CHƯA CHẠY THỬ TRỰC TIẾP (môi trường phát triển bị chặn mạng); mẫu địa chỉ/phân trang suy ra từ trang người dùng đã lưu.
Các trang này có thể chặn truy cập tự động (403/captcha): khi đó app báo rõ lý do và phần còn lại vẫn chạy.
Tuân thủ điều khoản sử dụng của từng trang; tần suất gọi được giới hạn (nghỉ giữa các trang).
"""
from .. import cancel
import datetime as dt, math, re, time
import requests
from .base import Source
from ..models import Listing
from ..parse import guess_kind
from . import htmlimport as hi

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml", "Accept-Language": "vi-VN,vi;q=0.9",
}
BLOCK_MARKERS = ("just a moment", "captcha", "cf-challenge", "access denied", "attention required")
PER_PAGE = 20
# Gia Lai (mới) = Gia Lai cũ + Bình Định cũ: cả hai tên đều cần tìm
PROVINCE_SLUGS = {"binh dinh": ["binh-dinh"], "gia lai": ["gia-lai", "binh-dinh"]}

class Blocked(Exception):
    pass

def slugs_for(tinh: str) -> list[str]:
    from ..textnorm import core_name, norm
    c = core_name(tinh)
    return PROVINCE_SLUGS.get(c, [norm(tinh).replace(" ", "-")] if c else [])

# Huyện/thị xã/thành phố của Bình Định (cũ): tên chuẩn hoá -> (tiền tố trong địa chỉ, mã Alonhadat). Lấy từ các trang người dùng đã lưu.
BINH_DINH_UNITS = {
    "an lao": ("huyen", 480), "hoai an": ("huyen", 482), "phu cat": ("huyen", 484), "phu my": ("huyen", 485), "tay son": ("huyen", 487),
    "tuy phuoc": ("huyen", 486), "van canh": ("huyen", 488), "vinh thanh": ("huyen", 489), "quy nhon": ("thanh-pho", 479),
    "an nhon": ("thi-xa", 481), "hoai nhon": ("thi-xa", 483),
}
BDS_DISTRICT_SLUGS = {"quy nhon", "phu cat", "an nhon", "tuy phuoc"}      # Batdongsan: chỉ các trang đã thấy trong file người dùng lưu

def unit_slug(huyen: str):
    """'Huyện Tuy Phước' -> ('tuy-phuoc', ('huyen', 486)) hoặc None nếu không phải đơn vị đã biết."""
    from ..textnorm import core_name
    c = core_name(huyen)
    return (c.replace(" ", "-"), BINH_DINH_UNITS[c]) if c in BINH_DINH_UNITS else None

PAGE_TOKEN = re.compile(r"(?:[?&](?:page|trang)=|/trang[-_]{1,2}|/p)(\d+)(?=\.html|/|$|\?|&)")

def page_number(url: str) -> int:
    m = PAGE_TOKEN.search(url)
    return int(m.group(1)) if m else 1

def next_page_url(html: str, current_url: str):
    """Tìm đường dẫn trang kế tiếp trong chính trang vừa tải (không đoán mẫu địa chỉ phân trang)."""
    from urllib.parse import urljoin, urlparse
    from bs4 import BeautifulSoup
    cur = page_number(current_url)
    host = urlparse(current_url).netloc
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        u = urljoin(current_url, a["href"])
        if urlparse(u).netloc == host and PAGE_TOKEN.search(u) and page_number(u) == cur + 1:
            return u
    return None

class WebSource(Source):
    keyword_search = False
    known_urls: set = frozenset()       # link đã lưu: trang huyện toàn tin đã lưu thì dừng (cào tăng dần)
    parser = staticmethod(lambda html, only_land=True: [])
    min_delay = 2.0

    def page_urls(self, tinh_slug: str, page: int) -> list[str]:
        raise NotImplementedError

    def _get(self, url: str) -> str:
        r = requests.get(url, headers={**HEADERS, "Referer": url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/"}, timeout=25)
        if r.status_code in (403, 429, 503):
            raise Blocked(f"HTTP {r.status_code} (trang chặn truy cập tự động)")
        if r.status_code == 404:
            raise FileNotFoundError("HTTP 404 (địa chỉ trang không tồn tại - mẫu địa chỉ cần chỉnh)")
        r.raise_for_status()
        low = r.text[:3000].lower()
        if any(m in low for m in BLOCK_MARKERS):
            raise Blocked("trang trả về màn hình kiểm tra bot/captcha")
        return r.text

    def district_first_url(self, huyen: str):
        return None

    def fetch_district(self, huyen: str, limit: int, max_age_days: int | None, log: list[str]):
        """Lấy tin theo trang của huyện/thị xã/thành phố (đủ sâu hơn trang cấp tỉnh). None nếu chưa hỗ trợ huyện này."""
        url = self.district_first_url(huyen)
        if not url:
            return None
        out, visited, pages = [], set(), max(1, math.ceil(limit / PER_PAGE))
        cutoff = (dt.date.today() - dt.timedelta(days=max_age_days)).isoformat() if max_age_days else None
        n = 0
        for _ in range(pages):
            visited.add(url)
            try:
                html = self._get(url)
            except Blocked as e:
                log.append(f"{self.name}: {e} — {url}"); return out
            except Exception as e:
                log.append(f"{self.name}: lỗi {e} — {url}"); break
            cards = self.parser(html, only_land=False)
            for l in cards:
                l.kind = guess_kind(l.url, l.title)
            fresh = [l for l in cards if l.url not in self.known_urls]
            out.extend(fresh); n += len(fresh)
            cancel.sleep(self.min_delay)
            if cards and not fresh:             # cả trang đều là tin đã lưu -> các trang sau cũ hơn, dừng
                log.append(f"{self.name} · trang huyện '{huyen}': gặp tin đã lưu, dừng sớm")
                break
            if not cards or (cutoff and all(l.posted_at and l.posted_at < cutoff for l in cards if l.posted_at)):
                break
            url = next_page_url(html, url)
            if not url or url in visited:
                break
        log.append(f"{self.name} · trang huyện '{huyen}': lấy về {n} tin")
        return out

    def fetch_area(self, tinh: str, limit: int, max_age_days: int | None, log: list[str], huyen: str = "") -> list[Listing]:
        if huyen.strip():
            got = self.fetch_district(huyen, limit, max_age_days, log)
            if got is not None:                    # có trang riêng của huyện: đủ sâu hơn trang cấp tỉnh nên không lấy thêm trang tỉnh
                return got
        out, pages = [], max(1, math.ceil(limit / PER_PAGE))
        cutoff = (dt.date.today() - dt.timedelta(days=max_age_days)).isoformat() if max_age_days else None
        for slug in slugs_for(tinh):
            n_slug = 0
            for page in range(1, pages + 1):
                got_cards, stop = 0, False
                for url in self.page_urls(slug, page):
                    try:
                        html = self._get(url)
                    except Blocked as e:
                        log.append(f"{self.name}: {e} — {url}"); return out
                    except Exception as e:
                        log.append(f"{self.name}: lỗi {e} — {url}"); stop = True; break
                    allr = self.parser(html, only_land=False)
                    got_cards += len(allr)
                    for l in allr:
                        l.kind = guess_kind(l.url, l.title)
                    land = allr
                    if cutoff and allr and all(l.posted_at and l.posted_at < cutoff for l in allr if l.posted_at):
                        stop = True
                    out.extend(land); n_slug += len(land)
                    cancel.sleep(self.min_delay)
                if stop or got_cards == 0:
                    break
            log.append(f"{self.name} · '{slug}': lấy về {n_slug} tin")
        return out

class Alonhadat(WebSource):
    name = "alonhadat"
    parser = staticmethod(hi.parse_alonhadat)
    def district_first_url(self, huyen):
        u = unit_slug(huyen)
        return f"https://alonhadat.com.vn/nha-dat/can-ban/nha-dat/binh-dinh/{u[1][1]}/{u[1][0]}-{u[0]}.html" if u else None
    def page_urls(self, slug, page):
        base = f"https://alonhadat.com.vn/can-ban-nha-dat/{slug}"
        return [base if page == 1 else f"{base}/trang-{page}"]

class Batdongsan(WebSource):
    name = "batdongsan"
    parser = staticmethod(hi.parse_batdongsan)
    min_delay = 3.0
    def district_first_url(self, huyen):
        u = unit_slug(huyen)
        return f"https://batdongsan.com.vn/nha-dat-ban-{u[0]}-bdd" if u and u[0].replace("-", " ") in BDS_DISTRICT_SLUGS else None
    def page_urls(self, slug, page):
        return [f"https://batdongsan.com.vn/nha-dat-ban-{slug}" + ("" if page == 1 else f"/p{page}")]

class Thuviennhadat(WebSource):
    name = "thuviennhadat"
    parser = staticmethod(hi.parse_thuviennhadat)
    def district_first_url(self, huyen):
        u = unit_slug(huyen)
        return f"https://thuviennhadat.vn/ban-nha-dat-{u[1][0]}-{u[0]}" if u else None
    def page_urls(self, slug, page):
        return [f"https://thuviennhadat.vn/ban-nha-dat-tinh-{slug}?trang={page}"]

class Raobannhadat(WebSource):
    name = "raobannhadat"
    parser = staticmethod(hi.parse_raobannhadat)
    PROVINCE_ID = {"gia-lai": 23, "binh-dinh": 23}   # sau sáp nhập chỉ còn mã Gia Lai (23)
    def page_urls(self, slug, page):
        pid = self.PROVINCE_ID.get(slug)
        if pid is None or slug == "binh-dinh":      # tránh lấy trùng: Bình Định đã nằm trong Gia Lai (23)
            return []
        return [f"https://raobannhadat.vn/danh-sach-tin?type=ban&category=&province={pid}&page={page}"]
