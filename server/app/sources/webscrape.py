"""Tự động mở trang kết quả tìm kiếm theo tỉnh của các trang tin rao rồi đọc bằng htmlimport.

CHƯA CHẠY THỬ TRỰC TIẾP (môi trường phát triển bị chặn mạng); mẫu địa chỉ/phân trang suy ra từ trang người dùng đã lưu.
Các trang này có thể chặn truy cập tự động (403/captcha): khi đó app báo rõ lý do và phần còn lại vẫn chạy.
Tuân thủ điều khoản sử dụng của từng trang; tần suất gọi được giới hạn (nghỉ giữa các trang).
"""
import datetime as dt, math, time
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

class WebSource(Source):
    keyword_search = False
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

    def fetch_area(self, tinh: str, limit: int, max_age_days: int | None, log: list[str]) -> list[Listing]:
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
                    time.sleep(self.min_delay)
                if stop or got_cards == 0:
                    break
            log.append(f"{self.name} · '{slug}': lấy về {n_slug} tin")
        return out

class Alonhadat(WebSource):
    name = "alonhadat"
    parser = staticmethod(hi.parse_alonhadat)
    def page_urls(self, slug, page):
        base = f"https://alonhadat.com.vn/can-ban-nha-dat/{slug}"
        return [base if page == 1 else f"{base}/trang-{page}"]

class Batdongsan(WebSource):
    name = "batdongsan"
    parser = staticmethod(hi.parse_batdongsan)
    min_delay = 3.0
    def page_urls(self, slug, page):
        return [f"https://batdongsan.com.vn/nha-dat-ban-{slug}" + ("" if page == 1 else f"/p{page}")]

class Thuviennhadat(WebSource):
    name = "thuviennhadat"
    parser = staticmethod(hi.parse_thuviennhadat)
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
