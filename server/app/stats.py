import statistics as st
from dataclasses import dataclass
from .models import Listing

@dataclass
class Result:
    n_used: int
    n_total: int
    median: float | None
    p25: float | None
    p75: float | None
    low: float | None      # sau chiết khấu thương lượng
    high: float | None
    warning: str
    outliers: list

def _q(vals, p):
    vals = sorted(vals); k = (len(vals) - 1) * p
    f = int(k); c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)

def summarize(listings: list[Listing], discount: float = 0.10, min_ok: int = 5) -> Result:
    prices = [(l, l.price_per_m2) for l in listings if l.price_per_m2]
    if not prices:
        return Result(0, len(listings), None, None, None, None, None,
                      "Không có tin nào đủ giá và diện tích để tính.", [])
    vals = [p for _, p in prices]
    outl = []
    if len(vals) >= 4:
        q1, q3 = _q(vals, .25), _q(vals, .75); iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outl = [l for l, p in prices if not lo <= p <= hi]
        vals = [p for l, p in prices if lo <= p <= hi]
    n = len(vals)
    med = st.median(vals); p25, p75 = _q(vals, .25), _q(vals, .75)
    k = 1 - discount
    if n < 3:
        w = f"CẢNH BÁO: chỉ có {n} tin so sánh, không đủ để kết luận. Chỉ mang tính tham khảo thô, cần khảo sát thực tế."
    elif n < min_ok:
        w = f"Cảnh báo: ít mẫu ({n} tin < {min_ok}). Khoảng giá có độ tin cậy thấp, nên mở rộng bán kính/khu vực hoặc bổ sung nguồn."
    else:
        w = ""
    return Result(n, len(listings), med, p25, p75, p25 * k, p75 * k, w, outl)
