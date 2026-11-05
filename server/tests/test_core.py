from app.parse import parse_price, parse_area, parse_frontage, guess_land_type
from app.textnorm import AdminMap, core_name
from app.models import Listing
from app.search import filter_listings, location_terms
from app.stats import summarize
from pathlib import Path
import csv, tempfile

def test_price():
    assert parse_price("Bán đất giá 1,2 tỷ") == 1.2e9
    assert parse_price("giá 850 triệu") == 850e6
    assert parse_price("2 tỷ 500 triệu") == 2.5e9
    assert parse_price("không có giá") is None

def test_area_land():
    assert parse_area("DT 500m2 đất ở") == 500
    assert parse_area("rộng 1,5 ha") == 15000
    assert guess_land_type("đất vườn cây lâu năm") == "CLN"
    assert guess_land_type("đất rừng keo") == "RSX"
    assert parse_frontage("mặt tiền 5m") == 5

def mk(old_new):
    d = Path(tempfile.mkdtemp()) / "m.csv"
    d.write_text("ten_cu,ten_moi,ghi_chu\n" + old_new, encoding="utf-8"); return AdminMap(d)

def test_mapping_both_ways():
    a = mk("Phường Nhơn Bình,Quy Nhơn Nam,x\n# bỏ qua\n")
    assert "quy nhon nam" in a.aliases("Nhơn Bình")
    assert "nhon binh" in a.aliases("phường Quy Nhơn Nam")

def L(price, area, addr="Phường Nhơn Bình, Quy Nhơn", t="x"):
    return Listing("t", f"u{price}{area}", t, address=addr, price_vnd=price, area_m2=area)

def test_filter_matches_new_name_listing():
    a = mk("Phường Nhơn Bình,Quy Nhơn Nam,x\n")
    items = [L(1e9, 100, "Quy Nhơn Nam, Gia Lai"), L(1e9, 100, "Pleiku, Gia Lai", "b")]
    out = filter_listings(items, location_terms(a, "Nhơn Bình", "", ""), need=1)
    assert len(out) == 1

def test_stats_warning_and_outlier():
    few = summarize([L(1e9, 100), L(1.1e9, 100)])
    assert "CẢNH BÁO" in few.warning
    many = summarize([L(p * 1e8, 100, t=str(p)) for p in (10, 11, 12, 10, 11, 100)])
    assert len(many.outliers) == 1 and many.n_used == 5
    assert many.low < many.p25

def test_street_rank():
    from app.search import same_street, rank
    a = L(1e9, 100, "Đường Nguyễn Huệ, Quy Nhơn", "a"); b = L(1e9, 100, "Đường Lê Lợi, Quy Nhơn", "b")
    assert same_street(a, "Nguyễn Huệ") and same_street(a, "đường nguyễn huệ") and not same_street(b, "Nguyễn Huệ")
    assert rank([b, a], "Nguyễn Huệ", 100)[0] is a

ALO = """<article class="property-item"><a class="link vip" href="https://alonhadat.com.vn/chinh-chu-ban-dat-mat-bien-xa-nhon-ly-tp-quy-nhon-binh-dinh-18961528.html">
<h3 class="property-title">CHÍNH CHỦ BÁN ĐẤT MẶT BIỂN XÃ NHƠN LÝ</h3></a><time class="created-date" datetime="2026-10-29" itemprop="datePosted">Hôm nay</time>
<p class="brief">Mặt tiền 10m. Đất ở</p>
<span class="price"><span itemprop="price" content="30550000000">65 triệu /&nbsp;m²</span></span>
<span class="area" itemprop="floorSize"><span itemprop="value">470</span> <span itemprop="unitText">m²</span></span>
<p class="new-address"><span itemprop="streetAddress">Đường D1</span>, <span itemprop="addressLocality">Phường Quy Nhơn Đông</span>, <span itemprop="addressRegion">Gia Lai</span></p>
<p class="old-address"><span>Đường D1, Phường Quy Nhơn Đông, Thành phố Quy Nhơn, Bình Định</span> (cũ)</p></article>
<article class="property-item"><a class="link" href="https://alonhadat.com.vn/ban-nha-255-nguyen-hue-1.html"><h3 class="property-title">BÁN NHÀ 255 NGUYỄN HUỆ</h3></a></article>"""
BDS = """<div class="js__card js__card-full-web"><a class="js__product-link-for-product-id" href="https://batdongsan.com.vn/ban-dat-phuong-nhon-phu-1/ban-dat-87m-pr46481823">
<div class="re__card-title">BÁN ĐẤT KHU DÂN CƯ 87,5M²</div><span class="re__card-config-price">2,85 tỷ</span><span class="re__card-config-area">87,5 m²</span>
<div class="re__card-location">TP. Quy Nhơn (P. Quy Nhơn Bắc mới)</div><span class="re__card-published-info-published-at">Đăng hôm nay</span></a></div>
<div class="js__card"><a class="js__product-link-for-product-id" href="https://batdongsan.com.vn/ban-can-ho-chung-cu-x/ch-pr1"><div class="re__card-title">Căn hộ 2PN</div></a></div>"""

def test_import_alonhadat_bds():
    from app.sources.htmlimport import parse_saved_html
    k, items = parse_saved_html(ALO)
    assert k == "alonhadat" and len(items) == 2 and [x.kind for x in items] == ["dat", "nha"]
    l = items[0]
    assert l.price_vnd == 30550000000 and l.area_m2 == 470 and l.frontage_m == 10
    assert "Bình Định" in l.address and "Gia Lai" in l.address and l.posted_at == "2026-10-29"
    k, items = parse_saved_html(BDS)
    assert k == "batdongsan" and len(items) == 2 and items[1].kind == "can_ho"
    assert items[0].price_vnd == 2.85e9 and items[0].area_m2 == 87.5 and "Quy Nhơn Bắc" in items[0].address
    assert parse_saved_html("<html></html>")[0] == ""

TVN = """<a href="https://thuviennhadat.vn/ban-dat-phuong-quy-nhon-bac/ban-dat-90m-pst1.html" title="Bán đất 90m² mặt tiền 5m"><div class="KinhDoanhNhaDat-index-post-title"><h2>Bán đất</h2></div></a><div></div>"""
TVN = """<div class="w"><a href="https://thuviennhadat.vn/ban-dat-phuong-quy-nhon-bac/ban-dat-90m-pst1.html" title="Bán đất 90m² mặt tiền 5m"><div class="KinhDoanhNhaDat-index-post-title"><h2>Bán đất</h2></div>
<div class="KinhDoanhNhaDat-index-unit-container"><div class="highlight"> 2,1 tỷ </div><div class="highlight"> 90 m² </div></div>
<span class="KinhDoanhNhaDat-index-post-address"> Quy Nhơn, Bình Định </span></a><div class="KinhDoanhNhaDat-index-post-footer"><span class="post-date"> Đăng hôm nay </span></div></div>
<div class="w"><a href="https://thuviennhadat.vn/ban-can-ho-chung-cu-x/ch-pst2.html" title="Căn hộ"><div class="KinhDoanhNhaDat-index-post-title"><h2>Căn hộ</h2></div></a></div>"""
RBN = """<article class="listing-card " data-listing-id="1"><div class="listing-card__body"><h3 class="listing-card__title">
<a href="https://raobannhadat.vn/chi-tiet-tin/ban-dat-xa-nhon-binh-thanh-pho-quy-nhon-binh-dinh-co-so-do-2">Bán đất xã Nhơn Bình</a></h3>
<div class="listing-card__meta"><span class="price">750 triệu</span><span class="area">180 m²</span></div><p class="listing-card__addr"> Gia Lai </p>
<div class="listing-card__foot"><span class="time">2 tháng trước</span></div></div></article>
<article class="listing-card "><div class="listing-card__body"><h3 class="listing-card__title"><a href="https://raobannhadat.vn/chi-tiet-tin/q-terra-view-bien">Q'TERRA đất vàng</a></h3></div></article>"""

def test_import_thuvien_raoban():
    from app.sources.htmlimport import parse_saved_html
    k, items = parse_saved_html(TVN)
    assert k == "thuviennhadat" and len(items) == 2 and items[1].kind == "can_ho"
    assert items[0].price_vnd == 2.1e9 and items[0].area_m2 == 90 and "quy nhon bac" in items[0].address.lower().replace("ơ","o").replace("ắ","a")
    k, items = parse_saved_html(RBN)
    assert k == "raobannhadat" and len(items) == 2
    assert items[0].price_vnd == 750e6 and items[0].area_m2 == 180 and "nhon binh" in items[0].address and "chi tiet" not in items[0].address

def test_webscrape_pages_and_block(monkeypatch):
    import app.sources.webscrape as ws
    class R:
        def __init__(s, code, text): s.status_code, s.text = code, text
        def raise_for_status(s): pass
    calls = []
    def fake(url, headers=None, timeout=None):
        calls.append(url)
        if "trang-2" in url: return R(200, "<html></html>")       # hết tin -> dừng
        return R(200, ALO)
    monkeypatch.setattr(ws.requests, "get", fake); monkeypatch.setattr(ws.time, "sleep", lambda x: None)
    log = []
    got = ws.Alonhadat().fetch_area("Bình Định", 100, None, log)
    assert len(got) == 2 and calls[0].endswith("/can-ban-nha-dat/binh-dinh") and calls[1].endswith("/trang-2")
    monkeypatch.setattr(ws.requests, "get", lambda *a, **k: R(403, ""))
    log = []; assert ws.Alonhadat().fetch_area("Bình Định", 100, None, log) == [] and "chặn" in log[0]
    assert ws.slugs_for("Gia Lai") == ["gia-lai", "binh-dinh"]

def test_google_source(monkeypatch):
    import app.sources.googlesearch as g
    monkeypatch.setenv("SERPER_API_KEY", "k"); monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False); monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    sent = {}
    class R:
        status_code = 200
        text = ""
        def raise_for_status(s): pass
        def json(s): return {"organic": [
            {"title": "Bán đất đường Bạch Đằng Quy Nhơn 100m2 giá 3,2 tỷ", "snippet": "Sổ hồng riêng", "link": "https://x/1"},
            {"title": "Cho thuê đất Bạch Đằng 5 triệu/tháng", "snippet": "", "link": "https://x/2"},
            {"title": "Tin tức thị trường đất Quy Nhơn", "snippet": "không có giá", "link": "https://x/3"}]}
    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, key=headers["X-API-KEY"], q=json["q"], gl=json["gl"]); return R()
    monkeypatch.setattr(g.requests, "post", fake_post); monkeypatch.setattr(g.time, "sleep", lambda x: None)
    log = []
    got = g.GoogleSearch().fetch_queries(g.build_queries("Bạch Đằng", "Quy Nhơn", "", "Bình Định"), 10, log)
    assert sent["url"].startswith("https://google.serper.dev") and sent["key"] == "k" and sent["gl"] == "vn"
    assert got[0].url == "https://x/1" and got[0].price_vnd == 3.2e9 and got[0].area_m2 == 100
    assert all(l.url not in ("https://x/2", "https://x/3") for l in got)
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: type("Q", (), {"status_code": 401, "text": "bad key"})())
    log = []; assert g.GoogleSearch().fetch_queries(["q"], 10, log) == [] and "khoá sai" in log[0]
    monkeypatch.delenv("SERPER_API_KEY"); log = []
    assert g.GoogleSearch().fetch_queries(["q"], 10, log) == [] and "chưa cấu hình" in log[0]

def test_ai_verification():
    from app.sources.googlesearch import _verify_ai
    v = _verify_ai({"price_vnd": 3.2e9, "area_m2": 999, "is_for_sale": True}, "Bán đất 100m2 giá 3,2 tỷ")
    assert v["price_vnd"] == 3.2e9 and "area_m2" not in v      # diện tích 999 không có trong văn bản -> bỏ


def test_kind_and_filter():
    from app.parse import guess_kind
    assert guess_kind("https://x/ban-dat-nen-du-an-abc/p-pr1", "") == "dat"
    assert guess_kind("https://x/ban-can-ho-chung-cu-q/ch-pr1", "") == "can_ho"
    assert guess_kind("https://x/ban-nha-rieng-duong-a/x-pr1", "") == "nha"
    assert guess_kind("", "Bán nhà 2 tầng hẻm Bạch Đằng") == "nha"
    a, b = L(1e9, 100, t="a"), L(3e9, 100, t="b"); a.kind, b.kind = "dat", "nha"
    out = filter_listings([a, b], [], kind="dat")
    assert out == [a]


def _seed(monkeypatch, tmp_path):
    import app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "t.sqlite")
    def mk(url, title, addr, price, area, kind, raw=None, src="chotot"):
        l = Listing(src, url, title, address=addr, price_vnd=price, area_m2=area, kind=kind, posted_at=(__import__("datetime").datetime.now() - __import__("datetime").timedelta(days=5)).isoformat(timespec="seconds"), fetched_at="2026-11-03T10:00:00")
        l.raw = raw or {}
        return l
    store.save([
        mk("https://x/1", "Bán đất đường Bạch Đằng", "Đường Bạch Đằng, Phường Quy Nhơn, Gia Lai", 3e9, 100, "dat", {"latitude": 13.77, "longitude": 109.22}),
        mk("https://x/2", "Đất Lê Lợi", "Đường Lê Lợi, Phường Quy Nhơn, Gia Lai", 2e9, 100, "dat", {"latitude": 99.0, "longitude": 10.0}),
        mk("https://x/3", "Nhà Pleiku", "Pleiku, Gia Lai", 1e9, 100, "nha"),
    ])

def test_api_comps_and_ranking(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m
    _seed(monkeypatch, tmp_path)
    c = TestClient(m.app)
    assert c.get("/api/health").json()["ok"] is True
    r = c.get("/api/comps", params={"duong": "Bạch Đằng", "xa": "Quy Nhơn", "tinh": "", "area": 100, "kind": "dat"}).json()
    urls = [i["url"] for i in r["items"]]
    assert urls[0] == "https://x/1" and set(urls) == {"https://x/1", "https://x/2"}      # cùng đường lên đầu; tin Pleiku/nhà bị loại
    assert r["items"][0]["lat"] == 13.77 and r["items"][0]["lng"] == 109.22
    assert r["items"][1]["lat"] is None            # toạ độ ngoài lãnh thổ VN bị bỏ
    assert r["items"][0]["price_per_m2"] == 3e7 and r["same_street"] == 1

def test_api_live_calls_collector(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m
    _seed(monkeypatch, tmp_path)
    called = {}
    def fake(q, xa, huyen, tinh, duong, land_type, months, maxn, src, errors):
        called.update(xa=xa, maxn=maxn, src=list(src)); q["fetchlog"].append("fake: 1 tin")
    monkeypatch.setattr(m, "collect_live", fake)
    r = TestClient(m.app).get("/api/comps", params={"xa": "Quy Nhơn", "live": 1, "maxn": 40, "src": "chotot,alonhadat"}).json()
    assert called == {"xa": "Quy Nhơn", "maxn": 40, "src": ["chotot", "alonhadat"]} and r["fetchlog"] == ["fake: 1 tin"]

def test_api_cors_and_private_network(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m
    _seed(monkeypatch, tmp_path)
    c = TestClient(m.app)
    ok = c.get("/api/health", headers={"Origin": "https://duycongta.github.io"})
    assert ok.headers.get("access-control-allow-origin") == "https://duycongta.github.io"
    bad = c.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in bad.headers
    pre = c.options("/api/comps", headers={"Origin": "https://duycongta.github.io", "Access-Control-Request-Method": "GET",
                                           "Access-Control-Request-Private-Network": "true"})
    assert pre.status_code == 200 and pre.headers.get("access-control-allow-private-network") == "true"


def test_lendland_page_served():
    from fastapi.testclient import TestClient
    import app.main as m
    r = TestClient(m.app).get("/lendland")
    assert r.status_code == 200 and "LendLand Pro" in r.text and "APP_VERSION" in r.text


def test_api_strict_location_levels(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "loc.sqlite")
    def mk(n, addr, title="Bán đất", kind="dat", desc="", src="chotot"):
        l = Listing(src, f"https://x/{n}", title, address=addr, description=desc, price_vnd=1e9 + ord(n) * 1e6, area_m2=150, kind=kind)
        return l
    store.save([
        mk("A", "Thôn Vinh Thạnh 1, Xã Phước Lộc, Huyện Tuy Phước, Bình Định"),
        mk("B", "Xã Phước Lộc, Huyện Tuy Phước, Bình Định, Gia Lai"),
        mk("G", "Xã Phước Lộc", src="alonhadat"),                                   # tin không nhắc tỉnh: vẫn nhận
        mk("C", "Xã Phước An, Huyện Tuy Phước, Bình Định"),                         # cùng huyện khác xã
        mk("D", "Xã Hoài Hải, Thị xã Hoài Nhơn, Bình Định"),                        # khác xã & huyện
        mk("E", "Xã Phước Lộc, Huyện Tam Kỳ, Quảng Ngãi"),                          # trùng tên xã nhưng tỉnh khác
        mk("F", "TP. Quy Nhơn (P. Quy Nhơn Đông mới)", src="batdongsan"),
        mk("H", "Xã Phước Lộc, Huyện Tuy Phước, Bình Định", title="Bán khách sạn mặt tiền", kind=""),   # không rõ loại
        mk("I", "Xã Tuy Phước Tây, Huyện Tuy Phước, Bình Định", desc="cách Phước Lộc 3km"),            # chỉ nhắc xã trong mô tả
    ])
    c = TestClient(m.app)
    p = {"xa": "Xã Phước Lộc", "huyen": "Huyện Tuy Phước", "tinh": "Bình Định", "thon": "Thôn Vinh Thạnh 1", "area": 147, "kind": "dat"}
    r = c.get("/api/comps", params=p).json()
    got = {i["url"].split("/")[-1]: i["match_level"] for i in r["items"]}
    assert got == {"A": "thon", "B": "xa", "G": "xa"}, got
    assert r["items"][0]["url"].endswith("/A")                               # cùng thôn lên đầu
    assert r["extra_district_available"] == 2 and r["match_counts"]["huyen"] == 0      # C và I: cùng huyện, khác xã
    r2 = c.get("/api/comps", params={**p, "scope": "district"}).json()
    got2 = {i["url"].split("/")[-1]: i["match_level"] for i in r2["items"]}
    assert got2 == {"A": "thon", "B": "xa", "G": "xa", "C": "huyen", "I": "huyen"} and r2["items"][-1]["match_level"] == "huyen"
    # Gia Lai (mới) và Bình Định (cũ) là một: nhập tỉnh nào cũng nhận tin nhắc tỉnh còn lại
    r3 = c.get("/api/comps", params={**p, "tinh": "Gia Lai"}).json()
    assert {i["url"].split("/")[-1] for i in r3["items"]} == {"A", "B", "G"}


# ---------------- bộ lọc chất lượng ----------------
import datetime as _dt

def _ago(days):
    return (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="seconds") if days is not None else ""

_TITLES = ["gần chợ mặt tiền đường lớn thuận tiện kinh doanh", "hẻm bê tông sổ hồng riêng chính chủ cần bán", "vị trí đẹp khu dân cư đông đúc yên tĩnh",
           "ngay trường học bệnh viện giao thông thuận lợi", "lô góc hai mặt thoáng rộng rãi vuông vức", "đất vườn cây ăn trái sầu riêng mới trồng",
           "cần tiền bán gấp giá rẻ hơn thị trường", "sát khu công nghiệp dự án đang triển khai", "gần biển view đẹp tiềm năng tăng giá",
           "nhà cấp bốn kèm đất rộng thổ cư toàn bộ", "ven sông thoáng mát không khí trong lành", "mặt đường nhựa xe tải vào tận nơi",
           "tách sổ ngay công chứng trong ngày", "đầu tư sinh lời dòng tiền ổn định lâu dài", "gần ủy ban chợ trung tâm hành chính xã",
           "đất nền phân lô quy hoạch đồng bộ hạ tầng", "bán nhanh trong tuần thương lượng chính chủ", "khu vực an ninh tốt dân trí cao",
           "đường ba gác hẻm thông thoáng ô tô tránh nhau", "lô đất hiếm có tại thôn thuận tiện đi lại", "giá mềm cho người thiện chí",
           "gần nhà thờ chùa trường mầm non", "bán rẻ do gia đình ra nước ngoài định cư", "gần quốc lộ cách mặt đường năm mươi mét", "view đồng ruộng thoáng khu vực yên bình"]
def _L(n, src="chotot", price=3e9, area=100, title=None, desc="", days=10, addr="Xã Phước Lộc, Huyện Tuy Phước, Bình Định", kind="dat"):
    return Listing(src, f"https://x/{n}", title or ("Bán đất " + _TITLES[n % len(_TITLES)]), address=addr, description=desc,
                   price_vnd=price, area_m2=area, kind=kind, posted_at=_ago(days))

def test_phone_extraction():
    from app.quality import extract_phones
    assert extract_phones("LH 0905 123 456 hoặc +84 905.123.456") == {"0905123456"}
    assert extract_phones("giá 1200000000 đồng") == set()

def test_dedupe_by_phone_keeps_trusted_source_and_separate_lots():
    from app.quality import dedupe_semantic
    a = _L(1, "chotot", 3e9, 100, desc="Liên hệ 0905 123 456")
    b = _L(2, "batdongsan", 3.05e9, 101, desc="Bán gấp, LH 0905123456")             # cùng SĐT, cùng diện tích/giá -> trùng
    c = _L(3, "chotot", 3e9, 200, desc="Lô khác của cùng người LH 0905123456")      # cùng SĐT nhưng khác diện tích -> lô khác
    out, merged = dedupe_semantic([(a, "xa"), (b, "xa"), (c, "xa")])
    assert merged == 1 and len(out) == 2
    kept = {o[0].url: o for o in out}
    assert "https://x/2" in kept and kept["https://x/2"][2]["dup_count"] == 1 and kept["https://x/2"][2]["also_on"] == ["chotot"]   # giữ nguồn trọng số cao hơn
    assert "https://x/3" in kept

def test_dedupe_by_text():
    from app.quality import dedupe_semantic
    t = "Bán lô đất mặt tiền đường bê tông gần chợ trường học khu dân cư đông đúc sổ hồng riêng"
    a = _L(1, title=t, area=120); b = _L(2, "alonhadat", title=t + " lh ngay", area=121)
    assert dedupe_semantic([(a, "xa"), (b, "xa")])[1] == 1

def test_price_bounds_and_recency():
    from app.quality import price_bounds, recency_tier
    lo, hi = price_bounds([30, 31, 29, 32, 30, 120])
    assert hi < 120 and lo < 29
    assert price_bounds([30, 31]) is None
    lo3, hi3 = price_bounds([30, 31, 90]); assert hi3 < 90 * 1.0 and lo3 < 30
    assert [recency_tier(_L(i, days=d)) for i, d in enumerate((10, 120, 400, None))] == [0, 1, 2, 3]

def test_api_quality_pipeline(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "q.sqlite")
    items = [_L(i, "chotot", price=(3.0e9 + i * 5e7), area=100 + i, days=10 + i) for i in range(1, 7)]           # 6 tin bình thường
    items += [_L(20, "chotot", price=3e10, area=100, days=5)]                                                      # ngoại lai giá (300 tr/m2)
    items += [_L(21, "alonhadat", price=3.2e9, area=110, days=None)]                                               # không rõ ngày
    items += [_L(22, "chotot", price=3.1e9, area=111, days=400)]                                                   # quá cũ -> loại hẳn
    items += [_L(23, "batdongsan", price=(3.0e9 + 1 * 5e7) + 1e6, area=101, days=3, title="Bán đất " + _TITLES[1] + " lh gấp")]   # trùng tin số 1 (nội dung giống, cùng diện tích và giá)
    store.save(items)
    c = TestClient(m.app)
    r = c.get("/api/comps", params={"xa": "Xã Phước Lộc", "huyen": "Huyện Tuy Phước", "tinh": "Bình Định", "area": 105, "kind": "dat", "months": 6, "tol": 100}).json()
    by = {i["url"].split("/")[-1]: i for i in r["items"]}
    assert "22" not in by                                                    # tin quá 6 tháng bị loại
    assert by["20"]["outlier"] is True and by["20"]["pool_reason"] == "outlier" and by["20"]["eligible_main"] is False
    assert by["21"]["pool_reason"] == "no_date" and by["21"]["date_tier"] == 3 and by["21"]["eligible_main"] is False
    assert "1" not in by and by["23"]["dup_count"] == 1 and by["23"]["also_on"] == ["chotot"]     # tin 1 và 23 gộp, giữ bản từ batdongsan (trọng số cao hơn)
    assert all(by[str(i)]["eligible_main"] for i in range(2, 7)) and by["23"]["eligible_main"]
    assert r["quality"]["merged_duplicates"] == 1 and r["quality"]["outliers"] == 1 and r["quality"]["no_date"] == 1 and r["quality"]["eligible"] == 6
    assert r["stats"]["weighted_median_per_m2"] and r["items"][0]["eligible_main"] is True      # tin đạt chuẩn xếp trước
    assert by["2"]["weight"] == 0.9 and by["21"]["weight"] == 0.8 and by["23"]["weight"] == 1.0


def test_api_version_and_user_scenario(monkeypatch, tmp_path):
    """Tài sản ở Xã Phước Sơn, huyện Tuy Phước: các tin ở Hoài Hải, Vĩnh Phú, Quy Nhơn, An Nhơn... KHÔNG được xuất hiện."""
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "u.sqlite")
    rows = [
        ("1", ", Xã Hoài Hải, Thị xã Hoài Nhơn, Bình Định, , Phường Hoài Nhơn Đông, Gia Lai", "620M2 GÓC 2 MẶT TIỀN TRỰC DIỆN BIỂN HOÀI HẢI", 7e9, 590),
        ("2", "Khu dân cư Vĩnh Phú, Phường Nhơn Thành, Phường An Nhơn Bắc, Thị xã An Nhơn, Bình Định, Gia Lai", "CHÍNH CHỦ BÁN ĐẤT KHU VỰC SÂN BAY PHÙ CÁT", 9.2e9, 955.7),
        ("3", "Đường Hàn Mạc Tử, Phường Quy Nhơn Nam, Thành phố Quy Nhơn, Bình Định, Gia Lai", "Bán khách sạn 3 sao mặt tiền đường hàn mạc tử", 110e9, 510),
        ("4", "Đường D1, Phường Quy Nhơn Đông, Thành phố Quy Nhơn, Bình Định, Gia Lai", "CHÍNH CHỦ BÁN ĐẤT MẶT BIỂN XÃ NHƠN LÝ", 30.55e9, 470),
        ("5", "Duong Hong Linh, Xã Nhơn Mỹ, Phường An Nhơn, Thị xã An Nhơn, Bình Định, Gia Lai", "Ac ai co mua lien he em dat minh ky ban", 0.6e9, 450),
        ("6", "Thôn Xuân Phương, Xã Phước Sơn, Huyện Tuy Phước, Bình Định", "Bán đất thôn Xuân Phương hẻm bê tông", 0.7e9, 700),
    ]
    store.save([Listing("chotot", f"https://x/{n}", t, address=a, price_vnd=pr, area_m2=ar, kind="dat", posted_at=_ago(10)) for n, a, t, pr, ar in rows])
    c = TestClient(m.app)
    assert c.get("/api/health").json()["api_version"] == 9 and "folder" in c.get("/api/health").json()
    r = c.get("/api/comps", params={"xa": "Xã Phước Sơn", "huyen": "Huyện Tuy Phước", "tinh": "Tỉnh Bình Định", "thon": "Thôn Xuân Phương", "area": 751.4, "kind": "dat", "tol": 50}).json()
    assert r["api_version"] == 9
    assert [i["url"].split("/")[-1] for i in r["items"]] == ["6"] and r["items"][0]["match_level"] == "thon"


def test_learned_admin_mapping_matches_new_name_listing(monkeypatch, tmp_path):
    """Tin chỉ ghi tên MỚI (kiểu Batdongsan) vẫn khớp khi người dùng nhập tên CŨ, nhờ cặp cũ-mới học từ tin Chợ Tốt."""
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    from app.learn import learn_pairs
    monkeypatch.setattr(store, "DB", tmp_path / "l.sqlite")
    ct = Listing("chotot", "https://x/ct", "Đất Phước Sơn", address="Xã Phước Sơn, Huyện Tuy Phước, Bình Định, Xã Tuy Phước Đông, Gia Lai", price_vnd=1e9, area_m2=100, kind="dat", posted_at=_ago(5))
    ct.raw = {"ward_name": "Xã Phước Sơn", "ward_name_v3": "Xã Tuy Phước Đông", "area_name": "Huyện Tuy Phước"}
    bd = Listing("batdongsan", "https://x/bd", "Bán đất nền sổ riêng đường bê tông", address="H. Tuy Phước (X. Tuy Phước Đông mới)", price_vnd=1.1e9, area_m2=110, kind="dat", posted_at=_ago(6))
    other = Listing("batdongsan", "https://x/ot", "Bán đất thị trấn", address="H. Tuy Phước (X. Tuy Phước Tây mới)", price_vnd=1.2e9, area_m2=120, kind="dat", posted_at=_ago(7))
    store.save([ct, bd, other])
    assert ("Xã Phước Sơn", "Xã Tuy Phước Đông") in learn_pairs([ct])
    r = TestClient(m.app).get("/api/comps", params={"xa": "Xã Phước Sơn", "huyen": "Huyện Tuy Phước", "tinh": "Bình Định", "area": 105, "kind": "dat"}).json()
    assert {i["url"].split("/")[-1] for i in r["items"]} == {"ct", "bd"} and r["quality"]["learned_admin_pairs"] == 1


def test_webscrape_district_urls_and_pagination(monkeypatch):
    import app.sources.webscrape as ws
    assert ws.unit_slug("Huyện Tuy Phước") == ("tuy-phuoc", ("huyen", 486))
    assert ws.unit_slug("Thành phố Quy Nhơn")[1] == ("thanh-pho", 479) and ws.unit_slug("Xã Phước Sơn") is None
    assert ws.Alonhadat().district_first_url("Huyện Tuy Phước") == "https://alonhadat.com.vn/nha-dat/can-ban/nha-dat/binh-dinh/486/huyen-tuy-phuoc.html"
    assert ws.Thuviennhadat().district_first_url("Huyện Tuy Phước") == "https://thuviennhadat.vn/ban-nha-dat-huyen-tuy-phuoc"
    assert ws.Batdongsan().district_first_url("Huyện Tuy Phước") == "https://batdongsan.com.vn/nha-dat-ban-tuy-phuoc-bdd"
    assert ws.Batdongsan().district_first_url("Huyện Phù Mỹ") is None
    html = '<a href="/x/trang-1">1</a><a href="https://alonhadat.com.vn/x/trang-2">2</a><a href="/x/trang-3">3</a>'
    assert ws.next_page_url(html, "https://alonhadat.com.vn/x") == "https://alonhadat.com.vn/x/trang-2"
    assert ws.next_page_url(html, "https://alonhadat.com.vn/x/trang-2") == "https://alonhadat.com.vn/x/trang-3"
    assert ws.next_page_url("<a href='/y'>a</a>", "https://alonhadat.com.vn/x") is None
    assert ws.next_page_url('<a href="?trang=2">2</a>', "https://thuviennhadat.vn/ban-nha-dat-huyen-tuy-phuoc") == "https://thuviennhadat.vn/ban-nha-dat-huyen-tuy-phuoc?trang=2"
    # fetch_district đi theo liên kết phân trang có trong trang
    pages = {"https://alonhadat.com.vn/nha-dat/can-ban/nha-dat/binh-dinh/486/huyen-tuy-phuoc.html": ALO + '<a href="/nha-dat/can-ban/nha-dat/binh-dinh/486/huyen-tuy-phuoc/trang-2">2</a>',
             "https://alonhadat.com.vn/nha-dat/can-ban/nha-dat/binh-dinh/486/huyen-tuy-phuoc/trang-2": ALO.replace("18961528", "18961529")}
    class R:
        status_code = 200
        def __init__(s, t): s.text = t
        def raise_for_status(s): pass
    seen = []
    monkeypatch.setattr(ws.requests, "get", lambda url, **k: (seen.append(url), R(pages[url]))[1]); monkeypatch.setattr(ws.time, "sleep", lambda x: None)
    log = []
    got = ws.Alonhadat().fetch_area("Bình Định", 100, None, log, huyen="Huyện Tuy Phước")
    assert len(seen) == 2 and len(got) == 4 and "trang huyện" in log[0]                    # ALO có 2 thẻ tin/trang, 2 trang
    seen.clear(); ws.Alonhadat().fetch_area("Bình Định", 20, None, [], huyen="Xã Phước Sơn")          # không phải đơn vị đã biết -> lấy trang tỉnh
    assert seen and "binh-dinh" in seen[0] and "huyen-" not in seen[0]


def test_chotot_province_filter_and_codes(monkeypatch):
    import app.sources.chotot as ct
    calls = []
    class R:
        status_code = 200
        def __init__(s, ads): s.ads = ads
        def raise_for_status(s): pass
        def json(s): return {"ads": s.ads}
    def ad(region, rv2, ward, ward_v3, area_v2=704301, wcode=7340):
        return {"list_id": 1, "region_name": region, "region_name_v3": "Gia Lai" if region == "Bình Định" else region, "region_v2": rv2, "area_name": "Huyện Tuy Phước", "area_v2": area_v2,
                "ward_name": ward, "ward_name_v3": ward_v3, "ward": wcode, "subject": "x"}
    def fake(url, params=None, headers=None, timeout=None):
        calls.append(dict(params)); q = params.get("q", "")
        if "region_v2" not in params:
            return R([ad("Ninh Thuận", 7045, "Xã Phước Sơn", "Xã Phước Sơn"), ad("Bình Định", 7043, "Xã Phước Sơn", "Xã Tuy Phước Đông")])
        return R([ad("Bình Định", 7043, "Xã Phước Sơn", "Xã Tuy Phước Đông")]) if params.get("o", 0) == 0 else R([])
    monkeypatch.setattr(ct.requests, "get", fake); monkeypatch.setattr(ct.time, "sleep", lambda x: None)
    c = ct.Chotot()
    assert c.discover_regions(["Xã Phước Sơn"], allowed={"binh dinh", "gia lai"}) == {7043: "Bình Định"}          # bỏ Ninh Thuận (trùng tên xã)
    assert set(c.discover_regions(["Xã Phước Sơn"])) == {7043, 7045}                                                 # không giới hạn tỉnh thì lấy cả hai
    wards, areas = c.discover_codes(7043, {"phuoc son", "tuy phuoc dong"}, {"tuy phuoc"})
    assert wards == {(704301, 7340)} and areas == {704301}
    calls.clear(); got = c.search_codes(7043, 704301, 7340, limit=20)
    assert calls[0]["region_v2"] == 7043 and calls[0]["area_v2"] == 704301 and calls[0]["ward"] == 7340 and len(got) == 1


def test_geo_parse_and_ssrf():
    from app import geo
    assert geo.parse_maps_url("https://www.google.com/maps/place/X/@13.80,109.20,17z/data=!3d13.795063!4d109.190325") == (13.795063, 109.190325, "pin")
    assert geo.parse_maps_url("https://www.google.com/maps/@13.8,109.2,17z")[2] == "center"
    assert geo.parse_maps_url("https://www.google.com/maps?q=13.7,109.1")[2] == "query"
    assert geo.parse_maps_url("https://www.google.com/maps") is None
    assert geo.host_ok("https://maps.app.goo.gl/abc") and geo.host_ok("https://www.google.com.vn/maps/x")
    for bad in ("http://maps.app.goo.gl/x", "https://evil.com/maps", "https://maps.app.goo.gl.evil.com/x", "https://127.0.0.1/", "https://169.254.169.254/",
                "https://user@maps.app.goo.gl/x", "https://maps.app.goo.gl:8080/x", "file:///etc/passwd"):
        assert not geo.host_ok(bad), bad

def test_resolve_follows_only_google(monkeypatch):
    from app import geo
    class R:
        def __init__(s, code, loc=None): s.status_code = code; s.headers = {"Location": loc} if loc else {}
        def close(s): pass
    class S:
        def __init__(s, hops): s.hops = hops; s.calls = []
        def get(s, url, **kw):
            assert kw.get("allow_redirects") is False
            s.calls.append(url); return s.hops[url]
    ok = S({"https://maps.app.goo.gl/a": R(302, "https://www.google.com/maps/place/X/@13.8,109.2,17z/data=!3d13.795063!4d109.190325")})
    final, err = geo.resolve_short_url("https://maps.app.goo.gl/a", session=ok)
    assert err is None and geo.parse_maps_url(final)[:2] == (13.795063, 109.190325)
    evil = S({"https://maps.app.goo.gl/a": R(302, "http://169.254.169.254/latest")})
    final, err = geo.resolve_short_url("https://maps.app.goo.gl/a", session=evil)
    assert err and evil.calls == ["https://maps.app.goo.gl/a"]          # không gọi tới địa chỉ nội bộ

def test_api_resolve_endpoint():
    from fastapi.testclient import TestClient
    import app.main as m
    c = TestClient(m.app)
    assert c.get("/api/resolve", params={"url": "https://evil.com/x"}).json()["ok"] is False
    j = c.get("/api/resolve", params={"url": "https://www.google.com/maps/@13.8,109.2,17z/data=!3d13.795063!4d109.190325"}).json()
    assert j["ok"] and j["lat"] == 13.795063 and j["kind"] == "pin"
    assert c.get("/api/resolve", params={"url": "https://www.google.com/maps/@1.0,1.0,17z"}).json()["ok"] is False      # ngoài Việt Nam

def test_near_ward_distance_pool(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "n.sqlite")
    def mkl(n, addr, lat=None, lng=None, price=1e9, area=100):
        raw = {"latitude": lat, "longitude": lng} if lat else {}
        return Listing("chotot", f"https://x/{n}", f"Bán đất lô {n} khu {n}", address=addr, price_vnd=price, area_m2=area, kind="dat", posted_at=_ago(10), raw=raw)
    store.save([
        mkl(1, "Xã Phước Sơn, Huyện Tuy Phước, Bình Định", 13.7951, 109.1904),                        # cùng xã, có tọa độ
        mkl(2, "Xã Phước Hòa, Huyện Tuy Phước, Bình Định", 13.7990, 109.1904),                        # xã khác, ~430 m -> near
        mkl(3, "Xã Phước Hòa, Huyện Tuy Phước, Bình Định", 13.8300, 109.1904),                        # xã khác, ~3.9 km -> loại
        mkl(4, "Xã Phước Hòa, Huyện Tuy Phước, Bình Định"),                                           # không có tọa độ -> loại
        mkl(5, "Xã Phước Hòa, Huyện Phù Cát, Quảng Ngãi", 13.7960, 109.1905),                         # tỉnh khác -> loại
    ])
    c = TestClient(m.app)
    p = {"xa": "Xã Phước Sơn", "huyen": "Huyện Tuy Phước", "tinh": "Bình Định", "area": 100, "kind": "dat", "lat": 13.795063, "lng": 109.190325, "radius_m": 1000}
    r = c.get("/api/comps", params=p).json()
    by = {i["url"].split("/")[-1]: i for i in r["items"]}
    assert set(by) == {"1", "2"}
    assert by["2"]["match_level"] == "near" and by["2"]["eligible_main"] is False and by["2"]["pool_reason"] == "near_ward" and 300 < by["2"]["distance_m"] < 600
    assert by["1"]["match_level"] == "xa" and by["1"]["distance_m"] < 50 and r["match_counts"]["near"] == 1
    assert r["stats"]["n_used"] == 1                                       # tin near không tính giá
    r2 = c.get("/api/comps", params={k: v for k, v in p.items() if k not in ("lat", "lng")}).json()
    assert {i["url"].split("/")[-1] for i in r2["items"]} == {"1"} and r2["items"][0]["distance_m"] is None

def test_admin_names_from_data(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    monkeypatch.setattr(store, "DB", tmp_path / "a.sqlite")
    store.save([Listing("chotot", "https://x/1", "Bán đất", address="a", price_vnd=1e9, area_m2=100, kind="dat", posted_at=_ago(5),
                        raw={"ward_name": "Phường Nhơn Bình", "ward_name_v3": "Phường Quy Nhơn Nam"})])
    c = TestClient(m.app)
    assert c.get("/api/admin_names", params={"name": "Nhơn Bình"}).json()["now_named"] == ["Phường Quy Nhơn Nam"]
    assert c.get("/api/admin_names", params={"name": "Phường Quy Nhơn Nam"}).json()["formerly"] == ["Phường Nhơn Bình"]
    j = c.get("/api/admin_names", params={"name": "Xã Không Có"}).json(); assert j["now_named"] == [] and j["formerly"] == []


def test_api_reverse_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m, app.geo as geo
    monkeypatch.setattr(geo, "reverse_chain", lambda la, ln: {"ok": True, "ward": "Phường Nhơn Bình", "district": "Thị xã An Nhơn", "province": "Bình Định", "source": "X", "tried": []})
    c = TestClient(m.app)
    j = c.get("/api/reverse", params={"lat": 13.795, "lng": 109.19}).json()
    assert j["ok"] and j["ward"] == "Phường Nhơn Bình"
    assert c.get("/api/reverse", params={"lat": 1, "lng": 1}).json()["ok"] is False


def test_province_merge_phu_yen_dak_lak(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store
    from app.textnorm import province_aliases, province_conflict
    assert {"phu yen", "dak lak"} <= province_aliases(m.admin, "Phú Yên") and {"binh dinh", "gia lai"} <= province_aliases(m.admin, "Gia Lai")
    assert not province_conflict("phuong song cau dak lak", province_aliases(m.admin, "Phú Yên"))
    assert province_conflict("phuong song cau khanh hoa", province_aliases(m.admin, "Phú Yên"))
    monkeypatch.setattr(store, "DB", tmp_path / "p.sqlite")
    store.save([
        Listing("chotot", "https://x/1", "Bán đất mặt tiền", address="Phường Xuân Phú, Thị xã Sông Cầu, Phú Yên, Đắk Lắk", price_vnd=3e9, area_m2=135, kind="dat", posted_at=_ago(10)),
        Listing("chotot", "https://x/2", "Bán đất khu phố", address="Phường Xuân Phú, Thị xã Sông Cầu, Khánh Hòa", price_vnd=3e9, area_m2=135, kind="dat", posted_at=_ago(10)),
        Listing("chotot", "https://x/3", "Bán đất khác", address="Phường Xuân Thành, Thị xã Sông Cầu, Phú Yên", price_vnd=2e9, area_m2=135, kind="dat", posted_at=_ago(10)),
    ])
    r = TestClient(m.app).get("/api/comps", params={"xa": "Phường Xuân Phú", "huyen": "Thị xã Sông Cầu", "tinh": "Phú Yên", "area": 135, "kind": "dat"}).json()
    assert [i["url"].split("/")[-1] for i in r["items"]] == ["1"]
    d = r["diagnostics"]
    assert d["stored"] == 3 and d["other_province"] == 1 and d["same_ward"] == 1 and d["same_district_other_ward"] == 1 and d["stored_by_source"] == {"chotot": 3}


def test_cancel_stops_live_collection(monkeypatch, tmp_path):
    import threading, time as _t
    from fastapi.testclient import TestClient
    import app.main as m, app.store as store, app.cancel as cancel
    monkeypatch.setattr(store, "DB", tmp_path / "c.sqlite")
    started = threading.Event(); steps = []
    def slow_collect(q, *a, **k):
        started.set()
        for i in range(200):
            steps.append(i); cancel.sleep(0.05)       # mô phỏng nguồn chờ giữa các trang
    monkeypatch.setattr(m, "collect_live", slow_collect)
    c = TestClient(m.app); res = {}
    th = threading.Thread(target=lambda: res.update(r=c.get("/api/comps", params={"xa": "Xã A", "tinh": "Bình Định", "live": 1, "job": "J1"}).json()))
    th.start(); assert started.wait(5); _t.sleep(0.2)
    assert c.get("/api/cancel", params={"job": "J1"}).json()["ok"]
    th.join(5); assert not th.is_alive()
    assert res["r"]["cancelled"] is True and res["r"]["items"] == [] and len(steps) < 50
    assert "J1" not in cancel._cancelled                                   # đã dọn
    # job khác không bị ảnh hưởng
    cancel.cancel("OTHER"); tok = cancel.start("J2"); cancel.check(); cancel.finish(tok, "J2"); cancel._cancelled.discard("OTHER")

def test_cancel_not_swallowed_by_except_exception():
    import app.cancel as cancel
    tok = cancel.start("J3"); cancel.cancel("J3")
    try:
        try:
            cancel.check()
        except Exception:
            assert False, "Cancelled bị nuốt"
    except cancel.Cancelled:
        pass
    finally:
        cancel.finish(tok, "J3")


def test_province_aliases_ignore_ward_pairs():
    import app.main as m
    from app.textnorm import province_aliases
    adm = m.admin.with_pairs({("Phú Yên", "Phú Đông"), ("Phú Thạnh", "Phú Yên")})      # cặp học nhầm từ dữ liệu
    assert province_aliases(adm, "Tỉnh Phú Yên") == {"phu yen", "dak lak"}
    assert province_aliases(adm, "") == set()

def test_chotot_ward_scan_limits_to_district(monkeypatch):
    from app.sources.chotot import Chotot
    import app.cancel as cancel
    monkeypatch.setattr(cancel, "sleep", lambda s: None)
    def ad(area, ward, wname, an): return {"area_v2": area, "ward": ward, "ward_name": wname, "ward_name_v3": wname, "area_name": an, "area_name_v3": an}
    c = Chotot()
    def fake_page(**p):
        if "q" in p:                        # tìm theo từ khóa: có Xuân Phú ở huyện khác (mã 111) và tin của Sông Cầu (mã 704602)
            return [ad(111, 9001, "Phường Xuân Phú", "Thành phố Tuy Hòa"), ad(704602, 5, "Phường Xuân Thành", "Thị xã Sông Cầu")]
        if p.get("area_v2") == 704602:     # quét huyện Sông Cầu: có phường Xuân Phú mã 77
            return [ad(704602, 77, "Phường Xuân Phú", "Thị xã Sông Cầu")] + [ad(704602, 5, "Phường Xuân Thành", "Thị xã Sông Cầu")] * 3
        return []
    monkeypatch.setattr(c, "_page", fake_page)
    wards, areas = c.discover_codes(7046, {"xuan phu"}, {"song cau"})
    assert areas == {704602} and wards == {(704602, 77)}


def test_roads_from_overpass_and_endpoint(monkeypatch):
    from app import geo
    import app.main as m
    from fastapi.testclient import TestClient
    lat, lng = 13.8, 109.2
    def way(name, hw, dlat):       # đường chạy ngang (đông-tây) cách điểm dlat độ vĩ
        return {"tags": {"name": name, "highway": hw}, "geometry": [{"lat": lat + dlat, "lon": lng - 0.001}, {"lat": lat + dlat, "lon": lng + 0.001}]}
    els = [way("Đường Lê Thành Phương", "secondary", 0.0001), way("Hẻm 12 Lê Thành Phương", "service", 0.0003),
           way("Đường Lê Thành Phương", "secondary", 0.0004), way("Đường Trần Hưng Đạo", "residential", 0.0005), {"tags": {"highway": "path"}, "geometry": []}]
    r = geo.roads_from_overpass(els, lat, lng)
    assert [x["name"] for x in r] == ["Đường Lê Thành Phương", "Hẻm 12 Lê Thành Phương", "Đường Trần Hưng Đạo"]
    assert 10 <= r[0]["distance_m"] <= 12 and r[0]["alley"] is False and r[1]["alley"] is True and 32 <= r[1]["distance_m"] <= 35
    monkeypatch.setattr(geo, "fetch_overpass_roads", lambda la, ln, rad: els)
    j = TestClient(m.app).get("/api/roads", params={"lat": lat, "lng": lng}).json()
    assert j["ok"] and j["roads"][0]["name"] == "Đường Lê Thành Phương"
    def boom(*a): raise RuntimeError("mạng")
    monkeypatch.setattr(geo, "fetch_overpass_roads", boom)
    assert TestClient(m.app).get("/api/roads", params={"lat": lat, "lng": lng}).json()["ok"] is False
    assert TestClient(m.app).get("/api/roads", params={"lat": 1, "lng": 1}).json()["ok"] is False


def test_reverse_parsers():
    from app import geo
    assert geo.parse_nominatim({"suburb": "Phường Nhơn Bình", "county": "Thị xã An Nhơn", "state": "Bình Định"}) == {"ward": "Phường Nhơn Bình", "district": "Thị xã An Nhơn", "province": "Bình Định"}
    assert geo.parse_photon({"features": [{"properties": {"locality": "Xuân Phú", "county": "Sông Cầu", "state": "Phú Yên"}}]}) == {"ward": "Xuân Phú", "district": "Sông Cầu", "province": "Phú Yên"}
    assert geo.parse_photon({"features": []}) == {"ward": "", "district": "", "province": ""}
    els = [{"tags": {"admin_level": "8", "name": "Phường Xuân Phú"}}, {"tags": {"admin_level": "6", "name": "Thị xã Sông Cầu"}}, {"tags": {"admin_level": "4", "name": "Phú Yên"}},
           {"tags": {"admin_level": "2", "name": "Việt Nam"}}, {"tags": {"admin_level": "8"}}]
    assert geo.parse_overpass_areas(els) == {"ward": "Phường Xuân Phú", "district": "Thị xã Sông Cầu", "province": "Phú Yên"}

def test_reverse_chain_falls_through():
    from app import geo
    class R:
        def __init__(s, data, code=200): s.data = data; s.status_code = code
        def raise_for_status(s):
            if s.status_code >= 400: raise RuntimeError(s.status_code)
        def json(s): return s.data
    class S:
        def __init__(s): s.calls = []
        def get(s, url, **kw):
            s.calls.append(url)
            if "nominatim" in url: raise ConnectionError("10061")                       # bị chặn như máy người dùng
            if "photon" in url: return R({"features": [{"properties": {"city": "Sông Cầu"}}]})  # thiếu tỉnh -> bỏ qua
            raise AssertionError(url)
        def post(s, url, **kw):
            s.calls.append(url); return R({"elements": [{"tags": {"admin_level": "8", "name": "Phường Xuân Phú"}}, {"tags": {"admin_level": "4", "name": "Phú Yên"}}]})
    sess = S(); r = geo.reverse_chain(13.4, 109.3, session=sess)
    assert r["ok"] and r["ward"] == "Phường Xuân Phú" and r["province"] == "Phú Yên" and r["source"].startswith("Overpass")
    assert [("nominatim" in c) or ("photon" in c) or ("overpass" in c) for c in sess.calls] == [True, True, True] and len(r["tried"]) == 2
    # nguồn đầu thành công thì dừng ngay
    class S2(S):
        def get(s, url, **kw): s.calls.append(url); return R({"address": {"suburb": "Phường A", "state": "Tỉnh B"}})
    s2 = S2(); r = geo.reverse_chain(13.4, 109.3, session=s2); assert r["source"] == "OpenStreetMap Nominatim" and len(s2.calls) == 1
    # tất cả thất bại
    class S3(S):
        def get(s, url, **kw): raise ConnectionError("x")
        def post(s, url, **kw): raise ConnectionError("x")
    r = geo.reverse_chain(13.4, 109.3, session=S3()); assert r["ok"] is False and len(r["tried"]) == 3
