import datetime as dt
import os
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .search import build_keywords, location_terms, filter_listings, same_street, rank, select_comps
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

def collect_live(q, xa, huyen, tinh, duong, land_type, months, maxn, src, errors):
    """Thu thập tin mới từ các nguồn trực tuyến, lưu vào SQLite; ghi nhật ký vào q["fetchlog"], lỗi vào errors."""
    # từ khoá tìm: dùng cả tên cũ và mới của xã/huyện để không bỏ sót
    # Từ khoá ngắn (chỉ địa danh) cho kết quả rộng hơn từ khoá dài; lọc chính xác làm ở bước sau
    kws = set()
    for x in (xa, huyen):
        if x.strip():
            kws.add(x.strip())
    if duong.strip():
        kws.add(f"{duong.strip()} {xa.strip() or huyen.strip()}".strip())
    for a in admin.aliases(xa) | admin.aliases(huyen):
        kws.add(a)
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
                store.save(source.fetch_area(tinh or "Gia Lai", maxn, 30 * months or None, q["fetchlog"]))
            except Exception as e:
                errors.append(f"Nguồn {name}: {e}")
        if not source.keyword_search:
            continue
        if hasattr(source, "discover_regions"):
            # Lọc theo khu vực (đầy đủ hơn tìm theo từ khoá, vì nhiều tin không ghi địa danh trong tiêu đề)
            try:
                regs = source.discover_regions([x for x in (xa, huyen, tinh) if x.strip()])
                for code, rname in regs.items():
                    got = source.search_region(code, limit=maxn, max_age_days=30 * months or None)
                    store.save(got)
                    q["fetchlog"].append(f"{name} · toàn bộ đất khu vực '{rname}' (mã {code}): lấy về {len(got)} tin")
                if not regs:
                    q["fetchlog"].append(f"{name}: không xác định được mã khu vực từ địa danh đã nhập")
            except Exception as e:
                errors.append(f"Nguồn {name} (lọc khu vực): {e}")
        for kw in kws:
            try:
                got = source.search(kw, limit=maxn, max_age_days=30 * months or None)
                store.save(got)
                q["fetchlog"].append(f"{name} · '{kw}': lấy về {len(got)} tin")
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
        "url": l.url, "title": l.title, "address": l.address or l.title,
        "source": l.source, "source_label": SOURCE_LABEL.get(l.source, l.source),
        "kind": l.kind, "land_type": l.land_type,
        "area_m2": l.area_m2, "frontage_m": l.frontage_m,
        "price_vnd": l.price_vnd, "price_per_m2": l.price_per_m2,
        "posted_at": l.posted_at, "fetched_at": l.fetched_at,
        "lat": lat if ok_coord else None, "lng": lng if ok_coord else None,
    }

@app.get("/api/health")
def api_health():
    return {"ok": True, "sources": list(SOURCES)}

@app.get("/api/comps")
def api_comps(duong: str = "", xa: str = "", thon: str = "", huyen: str = "", tinh: str = "Gia Lai", area: float = 0, kind: str = "",
              land_type: str = "", months: int = 6, tol: float = 50, discount: float = 10, scope: str = "ward",
              live: int = 0, maxn: int = 100, limit: int = 60, src: str = ""):
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
        collect_live(q, xa, huyen, tinh, duong, land_type, months, maxn, chosen, errors)
    weights = source_weights()
    allr = store.load_all()
    rec = [l for l in allr if recency_tier(l) == 3 or (l.posted_at and (recency_tier(l) <= 2 and _within(l, months)))]
    pairs = select_comps(rec, admin, xa, huyen, tinh, thon, "district", area or None, tol / 100, land_type, kind, duong)
    deduped, merged = dedupe_semantic(pairs, weights)
    extra_district = sum(1 for _, lv, _ in deduped if lv == "huyen")
    if scope != "district":
        deduped = [t for t in deduped if t[1] != "huyen"]
    # ngoại lai về đơn giá: tính trên tin cùng xã/phường có ngày rõ
    base = [l.price_per_m2 for l, lv, _ in deduped if lv != "huyen" and recency_tier(l) <= 2 and l.price_per_m2]
    bounds = price_bounds(base)
    rows = []
    for l, lv, info in deduped:
        tier = recency_tier(l); ppm = l.price_per_m2
        outlier = bool(bounds and ppm and (ppm < bounds[0] or ppm > bounds[1]))
        reason = ("district" if lv == "huyen" else "no_date" if tier == 3 else "outlier" if outlier else
                  "incomplete" if not (l.price_vnd and l.area_m2) else "")
        rows.append((l, lv, info, tier, outlier, reason, source_weight(l.source, weights)))
    def key(r):
        l, lv, info, tier, outlier, reason, w = r
        st_ = 0 if (duong and same_street(l, duong)) else 1
        d = abs(l.area_m2 - area) / area if (area and l.area_m2) else 9
        return ({"thon": 0, "xa": 1, "huyen": 2}[lv], 0 if reason == "" else 1, st_, tier, -w, d)
    rows.sort(key=key)
    ok_rows = [r for r in rows if r[5] == ""]
    res = summarize([r[0] for r in ok_rows], discount=discount / 100)
    wmed = weighted_median([(r[0].price_per_m2, r[6]) for r in ok_rows])
    counts = {lv: sum(1 for r in rows if r[1] == lv) for lv in ("thon", "xa", "huyen")}
    out = []
    for l, lv, info, tier, outlier, reason, w in rows[:limit]:
        d = listing_to_api(l)
        d.update(match_level=lv, weight=w, outlier=outlier, date_tier=tier, dup_count=info["dup_count"], also_on=info["also_on"],
                 eligible_main=(reason == ""), pool_reason=reason)
        out.append(d)
    return {
        "items": out, "total_matched": len(rows), "match_counts": counts, "extra_district_available": extra_district,
        "same_street": sum(1 for r in rows if duong and same_street(r[0], duong)),
        "quality": {"merged_duplicates": merged, "outliers": sum(1 for r in rows if r[5] == "outlier"),
                    "no_date": sum(1 for r in rows if r[5] == "no_date"), "eligible": len(ok_rows),
                    "price_bounds": list(bounds) if bounds else None},
        "stats": {"n_used": res.n_used, "median_per_m2": res.median, "weighted_median_per_m2": wmed, "p25": res.p25, "p75": res.p75, "warning": res.warning},
        "fetchlog": q["fetchlog"], "errors": errors,
    }

def _within(l, months):
    from .quality import days_old
    n = days_old(l)
    return n is not None and (not months or n <= 30 * months)
