import datetime as dt
import os
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .search import build_keywords, location_terms, filter_listings, same_street, rank, select_comps, select_near, listing_coords, suspect_coords, MAX_COORD_KM, haversine_m, parse_kinds, relevance, LEVEL_ORDER
from . import geo, cancel
from .textnorm import core_name, norm, province_aliases, province_conflict
from .learn import learn_pairs
from .quality import dedupe_semantic, recency_tier, price_bounds, source_weight, source_weights, weighted_median
from .sources import SOURCES, parse_manual_text
from .sources.googlesearch import build_queries
from .parse import KIND_LABEL
from .stats import summarize
from .textnorm import AdminMap
from .export import to_xlsx

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Khảo giá tài sản bảo đảm")

# Cho phép app LendLand Pro (GitHub Pages hoặc chạy trên máy) gọi API này. Đổi bằng biến môi trường ALLOWED_ORIGIN_REGEX.
ALLOWED_ORIGIN_REGEX = os.environ.get("ALLOWED_ORIGIN_REGEX", r"https://duycongta\.github\.io|http://(localhost|127\.0\.0\.1)(:\d+)?")
import inspect
_cors_kwargs = dict(allow_origin_regex=ALLOWED_ORIGIN_REGEX, allow_methods=["GET", "OPTIONS"], allow_headers=["*"])
# Chrome yêu cầu "Private Network Access" khi trang https (GitHub Pages) gọi vào máy cục bộ; Starlette mới hỗ trợ sẵn tham số này
if "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters:
    _cors_kwargs["allow_private_network"] = True
else:                                       # Starlette cũ: tự thêm header phản hồi
    @app.middleware("http")
    async def private_network_access(request, call_next):
        response = await call_next(request)
        if request.headers.get("access-control-request-private-network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
app.add_middleware(CORSMiddleware, **_cors_kwargs)
tpl = Jinja2Templates(directory=str(BASE / "templates"))
admin = AdminMap(BASE.parent / "data" / "admin_mapping.csv")
LAND = {"": "Tất cả", "ONT": "Đất ở nông thôn (ONT)", "ODT": "Đất ở đô thị (ODT)", "CLN": "Cây lâu năm (CLN)",
        "BHK": "Cây hàng năm (BHK/LUC)", "RSX": "Đất rừng sản xuất (RSX)", "NTS": "Nuôi trồng thuỷ sản", "NN": "Nông nghiệp khác"}

def fmt(v):
    return f"{v:,.0f}".replace(",", ".") if v else "-"
tpl.env.filters["vnd"] = fmt
tpl.env.globals["KIND_LABEL"] = KIND_LABEL

def recent(items, months):
    """Bỏ tin đăng quá `months` tháng (0 = không giới hạn). Tin không rõ ngày đăng vẫn giữ."""
    if not months:
        return items
    cut = (dt.datetime.now() - dt.timedelta(days=30 * months)).isoformat(timespec="seconds")
    return [l for l in items if not l.posted_at or l.posted_at >= cut]

def evaluate(q: dict):
    groups = location_terms(admin, q["xa"], q["huyen"], q["tinh"])
    allr = store.load_all()
    rec = recent(allr, q["months"])
    loc = filter_listings(rec, groups, need=q["need"])
    items = filter_listings(rec, groups, need=q["need"], area=q["area"] or None, tol=q["tol"] / 100,
                            land_type=q["land_type"], kind=q["kind"])
    q["funnel"] = [("Tổng số tin đã lưu trong máy", len(allr)), (f"Còn lại sau lọc thời gian ({q['months']} tháng)", len(rec)),
                   ("Còn lại sau lọc địa danh", len(loc)),
                   (f"Còn lại sau lọc diện tích (±{q['tol']:.0f}%) và loại đất", len(items))]
    items = rank(items, q["duong"], q["area"] or None)
    ss = [l for l in items if q["duong"] and same_street(l, q["duong"])]
    d = q["discount"] / 100
    if len(ss) >= 3:   # đủ tin cùng đường: ưu tiên làm cơ sở tính
        res, basis = summarize(ss, discount=d), "street"
    else:
        res, basis = summarize(items, discount=d), "area"
    return items, res, ss, basis

def qdict(xa, huyen, tinh, area, land_type, discount, need, duong="", months=0, tol=50, kind=""):
    return dict(tol=tol, months=months, duong=duong.strip(), xa=xa.strip(), huyen=huyen.strip(), tinh=tinh.strip(), area=area or 0,
                land_type=land_type, discount=discount, need=need, kind=kind)

KEYWORD_CAP = 60        # tối đa tin cho mỗi truy vấn rộng (từ khóa, trang huyện, cả khu vực): các truy vấn rộng nhiều tin không đúng phường
MIN_WARD_HITS = 10      # truy vấn theo mã phường/xã đã cho từng này tin thì bỏ qua các truy vấn từ khóa rộng

def build_keywords_list(xa, huyen, duong):
    """Từ khóa tìm kiếm ít và không trùng: xã/phường người nhập, 'đường + xã', tối đa 2 tên phường MỚI chứa phường đó; tên huyện chỉ khi không nhập xã."""
    from .textnorm import core_name, norm
    out, seen_norm, seen_core = [], set(), set()
    def add(k):
        k = (k or "").strip()
        if not k or norm(k) in seen_norm:
            return
        c = core_name(k)
        if c in seen_core:
            return                                   # 'quang trung' trùng lõi với 'Phường Quang Trung'
        seen_norm.add(norm(k)); seen_core.add(c); out.append(k)
    if xa.strip():
        add(xa)
        if duong.strip():
            add(f"{duong.strip()} {xa.strip()}")
        for p_ in sorted(admin.parents(xa))[:2]:     # tên phường mới (đã học từ tin) để không bỏ sót tin chỉ ghi tên mới
            add(p_)
    elif huyen.strip():
        add(huyen)
        if duong.strip():
            add(f"{duong.strip()} {huyen.strip()}")
    return out

def collect_live(q, xa, huyen, tinh, duong, land_type, months, maxn, src, errors):
    """Thu thập tin mới từ các nguồn trực tuyến, lưu vào SQLite; ghi nhật ký vào q["fetchlog"], lỗi vào errors.
    Tiết kiệm: truy vấn theo mã phường/xã (chính xác, ít tin) làm trước; truy vấn từ khóa rộng chỉ khi ít hơn MIN_WARD_HITS tin; mỗi truy vấn rộng
    tối đa KEYWORD_CAP tin và dừng sớm khi gặp tin đã lưu (cào tăng dần)."""
    known = store.known_urls()
    for s_ in SOURCES.values():
        s_.known_urls = known
    kws = build_keywords_list(xa, huyen, duong)
    cap = min(maxn, KEYWORD_CAP)
    max_age = 30 * months or None
    chosen = set(src) if src else set(SOURCES)
    for name, source in SOURCES.items():
        if name not in chosen:
            continue
        if getattr(source, "query_search", False):
            try:
                store.save(source.fetch_queries(build_queries(duong, xa, huyen, tinh, land_type), maxn, q["fetchlog"]))
            except Exception as e:
                errors.append(f"Nguồn {name}: {e}")
        if hasattr(source, "fetch_area"):
            try:
                store.save(source.fetch_area(tinh or "Gia Lai", cap, max_age, q["fetchlog"], huyen=huyen))
            except Exception as e:
                errors.append(f"Nguồn {name}: {e}")
        if not source.keyword_search:
            continue
        ward_hits = 0
        if hasattr(source, "discover_regions"):
            # Lọc theo khu vực (đầy đủ hơn tìm theo từ khoá, vì nhiều tin không ghi địa danh trong tiêu đề)
            try:
                from .textnorm import province_aliases
                regs = source.discover_regions([x for x in (xa, huyen, tinh) if x.strip()], allowed=province_aliases(admin, tinh))
                for code, rname in regs.items():
                    # Mã phường/xã và huyện (Chợ Tốt) trước: chính xác và ít tin
                    wards, areas = source.discover_codes(code, admin.aliases(xa) if xa.strip() else set(), admin.aliases(huyen) if huyen.strip() else set())
                    for area_c, ward_c in sorted(wards):
                        got = source.search_codes(code, area_c, ward_c, limit=maxn, max_age_days=max_age)
                        store.save(got); ward_hits += len(got); q["fetchlog"].append(f"{name} · theo phường/xã (mã {ward_c}): lấy về {len(got)} tin")
                    for area_c in sorted(areas - {a for a, _ in wards}):
                        got = source.search_codes(code, area_c, None, limit=cap, max_age_days=max_age, incremental=True)
                        store.save(got); q["fetchlog"].append(f"{name} · theo huyện (mã {area_c}): lấy về {len(got)} tin mới")
                    if not wards and not areas:      # không xác định được phường/huyện: mới lấy tin mới nhất cả khu vực
                        got = source.search_region(code, limit=cap, max_age_days=max_age, incremental=True)
                        store.save(got); q["fetchlog"].append(f"{name} · toàn bộ khu vực '{rname}' (mã {code}): lấy về {len(got)} tin mới nhất")
                if not regs:
                    q["fetchlog"].append(f"{name}: không xác định được mã khu vực từ địa danh đã nhập")
            except Exception as e:
                errors.append(f"Nguồn {name} (lọc khu vực): {e}")
        if ward_hits >= MIN_WARD_HITS:
            q["fetchlog"].append(f"{name}: đã có {ward_hits} tin theo mã phường/xã, bỏ qua tìm theo từ khóa rộng để nhanh và đỡ tốn")
            continue
        for kw in kws:
            try:
                got = source.search(kw, limit=cap, max_age_days=max_age, incremental=True)
                store.save(got)
                q["fetchlog"].append(f"{name} · '{kw}': lấy về {len(got)} tin mới")
            except Exception as e:
                errors.append(f"Nguồn {name} (từ khoá '{kw}'): {e}")


@app.get("/lendland", response_class=HTMLResponse)
def lendland_page():
    """Phục vụ giao diện LendLand Pro (index.html ở thư mục gốc repo) từ chính máy chủ này:
    mở http://localhost:8000/lendland thì cùng nguồn gốc với API, không cần CORS / quyền mạng cục bộ."""
    f = BASE.parent.parent / "index.html"
    if not f.exists():
        return HTMLResponse("Không tìm thấy index.html. Hãy chạy từ thư mục server của repo LendLandPro.", status_code=404)
    return HTMLResponse(f.read_text(encoding="utf-8"))

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return tpl.TemplateResponse(request, "index.html", dict(land=LAND, q=None, items=None, res=None,
                                aliases=None, errors=[], ss=[], basis="", sources=list(SOURCES)))

@app.post("/search", response_class=HTMLResponse)
def search(request: Request, duong: str = Form(""), xa: str = Form(""), huyen: str = Form(""), tinh: str = Form("Gia Lai"),
           area: float = Form(0), land_type: str = Form(""), discount: float = Form(10),
           need: int = Form(1), live: str = Form(""), src: list[str] = Form([]),
           months: int = Form(12), maxn: int = Form(200), tol: float = Form(50), kind: str = Form("")):
    q = qdict(xa, huyen, tinh, area, land_type, discount, need, duong, months, tol, kind)
    q["maxn"] = maxn
    q["fetchlog"] = []
    errors = []
    if live:
        collect_live(q, xa, huyen, tinh, duong, land_type, months, maxn, src, errors)
    items, res, ss, basis = evaluate(q)
    shown = [sorted(admin.aliases(x)) for x in (xa, huyen) if x.strip()]
    return tpl.TemplateResponse(request, "index.html", dict(land=LAND, q=q, items=items, res=res,
                                aliases=shown, errors=errors, ss=ss, basis=basis, sources=list(SOURCES)))

@app.post("/paste", response_class=HTMLResponse)
def paste(request: Request, text: str = Form(...), url: str = Form(""), address: str = Form("")):
    l = parse_manual_text(text, url=url, address=address)
    store.save([l])
    return tpl.TemplateResponse(request, "pasted.html", dict(l=l))

@app.get("/export.xlsx")
def export(duong: str = "", xa: str = "", huyen: str = "", tinh: str = "Gia Lai", area: float = 0, land_type: str = "", kind: str = "",
           discount: float = 10, need: int = 1, months: int = 12, tol: float = 50):
    q = qdict(xa, huyen, tinh, area, land_type, discount, need, duong, months, tol, kind)
    items, res, ss, basis = evaluate(q)
    data = to_xlsx(q, items, res, ss)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=khao-gia.xlsx"})


# ---------------- API cho LendLand Pro ----------------
SOURCE_LABEL = {"chotot": "Chợ Tốt / Nhà Tốt", "alonhadat": "Alonhadat", "batdongsan": "Batdongsan", "thuviennhadat": "Thư Viện Nhà Đất",
                "raobannhadat": "Raobannhadat"}

def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None

def listing_to_api(l):
    raw = l.raw if isinstance(l.raw, dict) else {}
    lat, lng = _num(raw.get("latitude")), _num(raw.get("longitude"))
    ok_coord = lat is not None and lng is not None and 8 < lat < 24 and 102 < lng < 110     # trong lãnh thổ VN
    return {
        "url": l.url, "title": l.title, "address": l.address or l.title, "description": (l.description or "")[:500],
        "source": l.source, "source_label": SOURCE_LABEL.get(l.source, l.source),
        "kind": l.kind, "land_type": l.land_type,
        "area_m2": l.area_m2, "frontage_m": l.frontage_m,
        "price_vnd": l.price_vnd, "price_per_m2": l.price_per_m2,
        "posted_at": l.posted_at, "fetched_at": l.fetched_at,
        "lat": lat if ok_coord else None, "lng": lng if ok_coord else None,
    }

API_VERSION = 13     # 13: tâm khảo sát center=pin|area (area = ước lượng khu vực, không loại tin), tin 'near' có tọa độ thật trong bán kính LÊN BẢNG CHÍNH khi tâm là ghim thật, bỏ tọa độ mặc định/lặp/quá xa, tra tọa độ ước lượng (est) cho tin không có tọa độ (distance_est), radius_m mặc định 2000, tin không có tọa độ -> Hàng chờ (no_coord) khi đã có >= 3 tin đạt chuẩn có khoảng cách thật. 12: so khớp phường nghiêm ngặt (xa_moi), lọc loại tài sản nhiều loại, bán kính 1.5 km, điểm sát thửa (score), limit mặc định 25, cào ít và tăng dần. 11: /api/roads mở rộng bán kính 60->150 m khi trống. 10: /api/reverse chuẩn hóa tổ/khu phố->hamlet, hạ ưu tiên tên tiếng Anh. 9: /api/reverse có chuỗi dự phòng. 8: thêm /api/roads. 7: thêm job + /api/cancel (dừng khảo sát). 6: thêm diagnostics trong /api/comps. 5: thêm /api/reverse. 4: thêm /api/resolve, /api/admin_names, lat/lng/radius_m + distance_m. 3: lọc địa danh nghiêm ngặt (match_level) + bộ lọc chất lượng. Giao diện từ chối máy chủ có API_VERSION thấp hơn.

@app.get("/api/health")
def api_health():
    return {"ok": True, "api_version": API_VERSION, "folder": str(BASE.parent), "sources": list(SOURCES)}

@app.get("/api/comps")
def api_comps(duong: str = "", xa: str = "", thon: str = "", huyen: str = "", tinh: str = "Gia Lai", area: float = 0, kind: str = "",
              land_type: str = "", months: int = 6, tol: float = 50, discount: float = 10, scope: str = "ward",
              live: int = 0, maxn: int = 100, limit: int = 25, src: str = "",
              lat: float = 0, lng: float = 0, radius_m: float = 2000, job: str = "", center: str = "pin", est: int = 8):
    """Tin so sánh THẬT (có link), đã qua các bộ lọc chất lượng:
    - bắt buộc cùng xã/phường và không thuộc tỉnh khác; cùng thôn/xóm, cùng đường xếp trước (scope=district: thêm tin cùng huyện, khác xã);
    - gộp tin trùng (cùng SĐT+diện tích+giá, hoặc nội dung giống nhau), giữ bản từ nguồn tin cậy hơn;
    - ưu tiên tin có ngày đăng rõ trong 3-6 tháng; tin không rõ ngày KHÔNG đưa lên bảng chính;
    - ngoại lai về đơn giá (IQR) bị gắn cờ, không đưa lên bảng chính;
    - trọng số theo nguồn (data/source_weights.json) khi xếp hạng và tính trung vị có trọng số.
    live=1: thu thập mới từ các trang rao trước (mất vài phút)."""
    q = qdict(xa, huyen, tinh, area, land_type, discount, 1, duong, months, tol, kind)
    q["maxn"] = maxn
    q["fetchlog"] = []
    errors = []
    if live:
        chosen = [x for x in src.split(",") if x.strip()]
        tok = cancel.start(job)
        try:
            collect_live(q, xa, huyen, tinh, duong, land_type, months, maxn, chosen, errors)
        except cancel.Cancelled:
            return {"api_version": API_VERSION, "cancelled": True, "items": [], "fetchlog": q["fetchlog"], "errors": errors}
        finally:
            cancel.finish(tok, job)
    weights = source_weights()
    allr = store.load_all()
    learned = learn_pairs(allr)
    admin_eff = admin.with_pairs(learned)        # bảng ánh xạ cũ-mới: file CSV + các cặp học từ dữ liệu tin
    rec = [l for l in allr if recency_tier(l) == 3 or (l.posted_at and (recency_tier(l) <= 2 and _within(l, months)))]
    pairs = select_comps(rec, admin_eff, xa, huyen, tinh, thon, "district", area or None, tol / 100, land_type, kind, duong)
    deduped, merged = dedupe_semantic(pairs, weights)
    diag = diagnose(allr, rec, admin_eff, xa, huyen, tinh, thon, len(pairs))
    extra_district = sum(1 for _, lv, _ in deduped if lv == "huyen")
    if scope != "district":
        deduped = [t for t in deduped if t[1] != "huyen"]
    have_pt = bool(lat and lng and geo.in_vietnam(lat, lng))
    soft = (center == "area")                    # tâm chỉ là ước lượng khu vực (chưa ghim thửa): dùng để xếp hạng/hiển thị, không loại tin và không đưa tin 'near' lên bảng chính
    radius = min(max(radius_m, 100), 5000)
    kinds = parse_kinds(kind)
    bad = suspect_coords(allr)                   # tọa độ mặc định/lặp của nguồn: bỏ
    near_pairs = []
    if have_pt:          # tin khác xã nhưng có tọa độ thật trong bán kính: lên bảng chính khi tâm là ghim thật (nếu đủ ngày, giá, diện tích), ngược lại chỉ Hàng chờ
        taken = {l.url for l, _, _ in deduped}
        near_pairs = [(l, "near", {"dup_count": 0, "also_on": []}) for l, _ in
                      select_near(rec, taken, admin_eff, tinh, lat, lng, radius, area or None, tol / 100, land_type, kind, bad)]
        deduped = deduped + near_pairs
    # khoảng cách thật (chỉ nguồn có tọa độ) quanh tâm
    dist, dist_est = {}, {}
    if have_pt:
        for l, _, _ in deduped:
            c = listing_coords(l, bad)
            if c:
                d0 = haversine_m(lat, lng, c[0], c[1])
                if d0 <= MAX_COORD_KM * 1000:    # quá xa (vd tọa độ mặc định ở TP.HCM) là tọa độ sai: bỏ
                    dist[l.url] = d0
        if est and live:     # tin không có tọa độ: ước lượng từ đường + xã (chỉ cho vài tin điểm cao nhất, có nhớ kết quả)
            from .estimate import estimate_points
            cands = [l for l, lv, _ in sorted(deduped, key=lambda t: (-relevance(t[0], t[1], None, radius, area or None, duong, kinds, recency_tier(t[0]))[0], LEVEL_ORDER[t[1]]))
                     if l.url not in dist]
            try:
                pts = estimate_points(cands, (lat, lng), max_new=max(0, min(est, 12)))
            except cancel.Cancelled:
                pts = {}
            for u, pt in pts.items():
                dist_est[u] = haversine_m(lat, lng, pt[0], pt[1])
    def far(l, lv):
        return (not soft) and lv in ("thon", "xa") and dist.get(l.url) is not None and dist[l.url] > radius      # cùng phường nhưng ngoài bán kính quanh thửa (chỉ khi đã ghim thật)
    # ngoại lai về đơn giá: tính trên tin cùng xã/phường đúng tên, trong bán kính, có ngày rõ
    base = [l.price_per_m2 for l, lv, _ in deduped if (lv in ("thon", "xa") or (lv == "near" and not soft)) and not far(l, lv) and recency_tier(l) <= 2 and l.price_per_m2]
    bounds = price_bounds(base)
    rows = []
    for l, lv, info in deduped:
        tier = recency_tier(l); ppm = l.price_per_m2
        outlier = bool(bounds and ppm and (ppm < bounds[0] or ppm > bounds[1]))
        reason = ("near_ward" if (lv == "near" and soft) else "new_ward" if lv == "xa_moi" else "district" if lv == "huyen" else "far" if far(l, lv) else
                  "no_date" if tier == 3 else "outlier" if outlier else "incomplete" if not (l.price_vnd and l.area_m2) else "")
        score, parts = relevance(l, lv, dist.get(l.url, dist_est.get(l.url)), radius, area or None, duong, kinds, tier)
        rows.append((l, lv, info, tier, outlier, reason, source_weight(l.source, weights), score, parts))
    def key(r):
        l, lv, info, tier, outlier, reason, w, score, parts = r
        return (0 if reason == "" else 1, -score, LEVEL_ORDER[lv], tier, -w)
    # Có ghim thật và đã có >= 3 tin đạt chuẩn với khoảng cách thật trong bán kính: tin cùng xã nhưng KHÔNG có tọa độ không kiểm chứng được độ gần -> Hàng chờ (xã mới sáp nhập rất rộng)
    if have_pt and not soft:
        verified = sum(1 for r in rows if r[5] == "" and r[0].url in dist and dist[r[0].url] <= radius)
        if verified >= 3:
            rows = [(r[0], r[1], r[2], r[3], r[4], ("no_coord" if (r[5] == "" and r[0].url not in dist) else r[5]), r[6], r[7], r[8]) for r in rows]
    rows.sort(key=key)
    ok_rows = [r for r in rows if r[5] == ""]
    res = summarize([r[0] for r in ok_rows], discount=discount / 100)
    wmed = weighted_median([(r[0].price_per_m2, r[6]) for r in ok_rows])
    counts = {lv: sum(1 for r in rows if r[1] == lv) for lv in ("thon", "xa", "xa_moi", "huyen", "near")}
    out = []
    for l, lv, info, tier, outlier, reason, w, score, parts in rows[:max(1, limit)]:
        d = listing_to_api(l)
        d.update(match_level=lv, weight=w, outlier=outlier, date_tier=tier, dup_count=info["dup_count"], also_on=info["also_on"],
                 eligible_main=(reason == ""), pool_reason=reason, distance_m=None, score=score, score_parts=parts)
        if l.url in dist:
            d["distance_m"] = round(dist[l.url])
        elif l.url in dist_est:
            d["distance_m"] = round(dist_est[l.url]); d["distance_est"] = True
        out.append(d)
    return {
        "api_version": API_VERSION,
        "items": out, "center": ("area" if soft else "pin") if have_pt else "", "radius_m": radius, "total_matched": len(rows), "match_counts": counts, "extra_district_available": extra_district,
        "same_street": sum(1 for r in rows if duong and same_street(r[0], duong)),
        "quality": {"learned_admin_pairs": len(learned), "merged_duplicates": merged, "outliers": sum(1 for r in rows if r[5] == "outlier"),
                    "no_date": sum(1 for r in rows if r[5] == "no_date"), "eligible": len(ok_rows),
                    "price_bounds": list(bounds) if bounds else None},
        "stats": {"n_used": res.n_used, "median_per_m2": res.median, "weighted_median_per_m2": wmed, "p25": res.p25, "p75": res.p75, "warning": res.warning},
        "diagnostics": diag,
        "fetchlog": q["fetchlog"], "errors": errors,
    }

def _within(l, months):
    from .quality import days_old
    n = days_old(l)
    return n is not None and (not months or n <= 30 * months)


@app.get("/api/resolve")
def api_resolve(url: str):
    """Mở link Google Maps rút gọn (maps.app.goo.gl) và trả về tọa độ. Chỉ chấp nhận tên miền Google (chống SSRF)."""
    if not geo.host_ok(url):
        return {"ok": False, "error": "Chỉ hỗ trợ link https của Google Maps."}
    try:
        final, err = geo.resolve_short_url(url)
    except Exception as e:
        return {"ok": False, "error": f"Không mở được link: {e}"}
    p = geo.parse_maps_url(final)
    if err or not p:
        return {"ok": False, "error": err or "Link không chứa tọa độ."}
    lat, lng, kind = p
    if not geo.in_vietnam(lat, lng):
        return {"ok": False, "error": f"Tọa độ {lat}, {lng} nằm ngoài Việt Nam."}
    return {"ok": True, "lat": lat, "lng": lng, "kind": kind, "final_url": final}

@app.get("/api/admin_names")
def api_admin_names(name: str):
    """Tên cũ / tên mới của một xã, phường, huyện, đã học từ chính các tin (Chợ Tốt, Alonhadat ghi cả hai tên).
    Chỉ trả những gì có trong dữ liệu; không có thì trả rỗng (không đoán)."""
    c = core_name(name)
    if not c:
        return {"ok": True, "now_named": [], "formerly": []}
    now_named, formerly = set(), set()      # now_named: tên mới của đơn vị mang tên cũ này; formerly: tên cũ của đơn vị mang tên mới này
    for old, new in learn_pairs(store.load_all()):
        if core_name(old) == c:
            now_named.add(new)
        if core_name(new) == c:
            formerly.add(old)
    return {"ok": True, "now_named": sorted(now_named), "formerly": sorted(formerly)}


@app.get("/api/reverse")
def api_reverse(lat: float, lng: float):
    """Tra xã/phường, huyện, tỉnh từ tọa độ bằng chuỗi nguồn dự phòng OpenStreetMap Nominatim -> Photon -> Overpass (gọi từ máy chủ, tránh trình duyệt/DNS bị chặn)."""
    if not geo.in_vietnam(lat, lng):
        return {"ok": False, "error": "Tọa độ nằm ngoài Việt Nam."}
    return geo.reverse_chain(lat, lng)


def diagnose(allr, rec, admin_eff, xa, huyen, tinh, thon, n_after_filters):
    """Giải thích vì sao ít/không có tin: số tin đã lưu theo nguồn, bị loại do khác tỉnh, khớp xã/phường, còn lại sau lọc diện tích/loại."""
    from collections import Counter
    from .search import classify_location
    allowed = province_aliases(admin_eff, tinh)
    other_prov = ward_hit = district_hit = 0
    for l in rec:
        hay = norm(l.address + " " + l.title + ("" if l.address else " " + l.description))
        if allowed and province_conflict(hay, allowed):
            other_prov += 1
            continue
        lv = classify_location(l, admin_eff, xa, huyen, tinh, thon, "district")
        if lv in ("thon", "xa"):
            ward_hit += 1
        elif lv == "huyen":
            district_hit += 1
    return {"stored": len(allr), "stored_by_source": dict(Counter(l.source for l in allr)), "recent": len(rec),
            "other_province": other_prov, "same_ward": ward_hit, "same_district_other_ward": district_hit,
            "after_filters": n_after_filters, "province_names_accepted": sorted(allowed)}



@app.get("/api/cancel")
def api_cancel(job: str):
    """Dừng khảo sát đang thu thập (mã job do giao diện gửi kèm /api/comps)."""
    cancel.cancel(job)
    return {"ok": True}


@app.get("/api/roads")
def api_roads(lat: float, lng: float, radius_m: float = 60):
    """Tên đường/hẻm gần vị trí (OpenStreetMap), kèm khoảng cách. Chỉ gợi ý để người dùng chọn; hẻm ở Việt Nam thường không có tên trên bản đồ."""
    if not geo.in_vietnam(lat, lng):
        return {"ok": False, "error": "Tọa độ nằm ngoài Việt Nam."}
    try:
        radius = min(max(radius_m, 20), 150)
        roads = geo.roads_from_overpass(geo.fetch_overpass_roads(lat, lng, radius), lat, lng)
        if not roads and radius < 150:          # không thấy đường nào: mở rộng bán kính tới 150 m
            radius = 150
            roads = geo.roads_from_overpass(geo.fetch_overpass_roads(lat, lng, radius), lat, lng)
    except Exception as e:
        return {"ok": False, "error": f"Không tra được đường gần đây: {e}"}
    return {"ok": True, "roads": roads, "radius_m": radius}
