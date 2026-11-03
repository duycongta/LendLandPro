"""Bộ lọc chất lượng tin so sánh: gộp tin trùng (số điện thoại / nội dung), ngày đăng, ngoại lai giá, trọng số nguồn."""
import datetime as dt, json, re, statistics as st
from pathlib import Path
from .models import Listing
from .textnorm import norm

WEIGHTS_FILE = Path(__file__).resolve().parent.parent / "data" / "source_weights.json"
DEFAULT_WEIGHTS = {"batdongsan": 1.0, "chotot": 0.9, "alonhadat": 0.8, "thuviennhadat": 0.7, "raobannhadat": 0.7, "google": 0.5, "mac_dinh": 0.6}

def source_weights() -> dict:
    try:
        w = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in w.items() if not k.startswith("_")}}
    except Exception:
        return dict(DEFAULT_WEIGHTS)

def source_weight(source: str, weights: dict | None = None) -> float:
    w = weights or source_weights()
    key = (source or "").split(" ")[0].lower()          # "google (AI)" -> "google"
    return float(w.get(key, w.get("mac_dinh", 0.6)))

# ---------- 3. Gộp tin trùng ----------
PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}(?!\d)")

def extract_phones(text: str) -> set:
    out = set()
    for m in PHONE_RE.finditer(text or ""):
        d = re.sub(r"\D", "", m.group(0))
        if d.startswith("84"):
            d = "0" + d[2:]
        if 9 <= len(d) <= 11:
            out.add(d)
    return out

def _tokens(l: Listing) -> set:
    t = norm((l.title or "") + " " + (l.description or "")[:400])
    return {w for w in t.split() if len(w) >= 3}

def _close(a, b, tol):
    return a is not None and b is not None and a > 0 and b > 0 and abs(a - b) / max(a, b) <= tol

def same_property(a: Listing, b: Listing) -> bool:
    """Cùng một tài sản đăng lặp: (cùng SĐT + cùng diện tích ±3% + cùng giá ±10%) hoặc (nội dung giống >=85% + cùng diện tích ±3% + giá ±15%).
    Cùng SĐT nhưng khác diện tích/giá là lô khác của cùng môi giới -> KHÔNG gộp."""
    area_ok = _close(a.area_m2, b.area_m2, 0.03)
    if extract_phones(a.title + " " + a.description) & extract_phones(b.title + " " + b.description) and area_ok and _close(a.price_vnd, b.price_vnd, 0.10):
        return True
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) >= 6 and len(tb) >= 6 and area_ok and _close(a.price_vnd, b.price_vnd, 0.15) and len(ta & tb) / len(ta | tb) >= 0.85:
        return True
    return False

def dedupe_semantic(pairs, weights=None):
    """pairs: [(Listing, level)] -> ([(Listing, level, info)], số tin đã gộp). Giữ bản có trọng số nguồn cao nhất, rồi mới nhất."""
    LV = {"thon": 0, "xa": 1, "huyen": 2}
    groups = []
    for l, lv in pairs:
        for g in groups:
            if same_property(g[0][0], l):
                g.append((l, lv)); break
        else:
            groups.append([(l, lv)])
    out, merged = [], 0
    for g in groups:
        g.sort(key=lambda t: t[0].posted_at or "", reverse=True)                 # mới nhất trước
        g.sort(key=lambda t: -source_weight(t[0].source, weights))               # rồi ưu tiên nguồn tin cậy hơn (sắp ổn định)
        best_l, best_lv = g[0]
        best_lv = min((x[1] for x in g), key=lambda v: LV[v])           # giữ mức khớp địa danh tốt nhất trong nhóm
        also = sorted({x[0].source.split(" ")[0] for x in g[1:] if x[0].source != best_l.source})
        out.append((best_l, best_lv, {"dup_count": len(g) - 1, "also_on": also}))
        merged += len(g) - 1
    return out, merged

# ---------- 2. Ngày đăng ----------
def days_old(l: Listing, today: dt.date | None = None):
    if not l.posted_at:
        return None
    try:
        d = dt.datetime.fromisoformat(l.posted_at[:19]).date()
    except ValueError:
        try:
            d = dt.date.fromisoformat(l.posted_at[:10])
        except ValueError:
            return None
    return ((today or dt.date.today()) - d).days

def recency_tier(l: Listing, today=None) -> int:
    """0: <=90 ngày, 1: <=180 ngày, 2: cũ hơn, 3: không rõ ngày đăng."""
    n = days_old(l, today)
    if n is None:
        return 3
    return 0 if n <= 90 else 1 if n <= 180 else 2

# ---------- 1. Ngoại lai giá ----------
def price_bounds(values):
    """(thấp, cao) theo IQR 1.5 khi >=5 mẫu; khi 3-4 mẫu dùng ngưỡng [0.4x, 2.5x] trung vị; <3 mẫu: không kết luận."""
    v = sorted(x for x in values if x and x > 0)
    if len(v) < 3:
        return None
    med = st.median(v)
    if len(v) >= 5:
        def q(p):
            k = (len(v) - 1) * p; f = int(k); c = min(f + 1, len(v) - 1); return v[f] + (v[c] - v[f]) * (k - f)
        q1, q3 = q(.25), q(.75); iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        # IQR quá hẹp khi các giá gần bằng nhau: tối thiểu cho phép ±40% quanh trung vị
        return (min(lo, med * 0.6), max(hi, med * 1.4))
    return (med * 0.4, med * 2.5)

def weighted_median(pairs):
    """pairs: [(giá/m2, trọng số)] -> trung vị có trọng số."""
    p = sorted((v, w) for v, w in pairs if v and w > 0)
    if not p:
        return None
    half = sum(w for _, w in p) / 2; acc = 0
    for v, w in p:
        acc += w
        if acc >= half:
            return v
