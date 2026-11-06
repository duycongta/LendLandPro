"""Chuẩn hoá tiếng Việt, ánh xạ tên đơn vị hành chính cũ <-> mới."""
import csv, re, unicodedata
from pathlib import Path

PREFIXES = ("thanh pho", "thi xa", "thi tran", "khu pho", "khu vuc", "phuong", "huyen", "quan", "thon", "xom", "xa", "tp.", "tp", "tinh", "ap")

def strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm(s: str, keep_num: bool = False) -> str:
    s = strip_accents(s or "").lower()
    s = re.sub(r"[^a-z0-9 .,]+" if keep_num else r"[^a-z0-9 ]+", " ", s)
    if keep_num:   # giữ dấu . , giữa các chữ số (1,5 / 1.200.000), bỏ ở chỗ khác
        s = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def core_name(s: str) -> str:
    """Bỏ tiền tố hành chính: 'Phường Nhơn Bình' -> 'nhon binh'."""
    n = norm(s)
    for p in PREFIXES:
        if n.startswith(p + " "):
            return n[len(p) + 1:]
    return n

class AdminMap:
    def __init__(self, path: Path):
        self.old2new: dict[str, set[str]] = {}
        self.new2old: dict[str, set[str]] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                rows = [r for r in csv.reader(f) if r and not r[0].lstrip().startswith("#")]
            for r in rows[1:]:
                if len(r) < 2 or not r[0].strip() or not r[1].strip():
                    continue
                o, n = core_name(r[0]), core_name(r[1])
                self.old2new.setdefault(o, set()).add(n)
                self.new2old.setdefault(n, set()).add(o)

    def with_pairs(self, pairs) -> "AdminMap":
        """Bản sao có thêm các cặp (tên cũ, tên mới) học được từ dữ liệu tin (Chợ Tốt, Alonhadat ghi cả hai tên)."""
        m = AdminMap.__new__(AdminMap)
        m.old2new = {k: set(v) for k, v in self.old2new.items()}
        m.new2old = {k: set(v) for k, v in self.new2old.items()}
        for old, new in pairs:
            o, n = core_name(old), core_name(new)
            if o and n and o != n:
                m.old2new.setdefault(o, set()).add(n)
                m.new2old.setdefault(n, set()).add(o)
        return m

    def children(self, name: str) -> set[str]:
        """Đơn vị cũ được gộp VÀO đơn vị tên này (nếu tên này là tên mới)."""
        return set(self.new2old.get(core_name(name), set()))

    def parents(self, name: str) -> set[str]:
        """Đơn vị mới CHỨA đơn vị tên này (nếu tên này là tên cũ)."""
        return set(self.old2new.get(core_name(name), set()))

    def aliases(self, name: str) -> set[str]:
        """Tên người dùng nhập + mọi tên cũ/mới tương ứng (dạng đã chuẩn hoá)."""
        c = core_name(name)
        if not c:
            return set()
        return {c} | self.old2new.get(c, set()) | self.new2old.get(c, set())

def norm_loc(s: str) -> str:
    """Chuẩn hoá địa chỉ để so khớp đơn vị hành chính: bỏ dấu, thường, 'qui'->'quy', GIỮ dấu phẩy làm ngăn cách."""
    s = strip_accents(s or "").lower()
    s = re.sub(r"\bqui\b", "quy", s)
    s = re.sub(r"[^a-z0-9,]+", " ", s)
    s = re.sub(r"\s*,\s*", " , ", s)
    return re.sub(r"\s+", " ", s).strip()

def core_loc(name: str) -> str:
    """Tên đơn vị bỏ tiền tố hành chính, đã chuẩn hoá như norm_loc (không dấu phẩy)."""
    return norm_loc(core_name(name)).replace(" , ", " ").strip(" ,")

WARD_PREFIX = r"(?:phuong|p|xa|x|thi tran|tt)"

def mentions_ward(hay_loc: str, core: str) -> bool:
    """Tin có nhắc XÃ/PHƯỜNG tên `core` với tiền tố hành chính (phường/p./xã/thị trấn) và không phải tên dài hơn (Quy Nhơn Nam khác Quy Nhơn).
    Tên đường ('Đường Quang Trung', 'Quang Trung, Phường Bồng Sơn') và tên thành phố ('Thành phố Quy Nhơn') KHÔNG được tính."""
    if not core:
        return False
    return re.search(rf"(?<![a-z0-9]){WARD_PREFIX}\s+{re.escape(core)}(?![a-z0-9])(?!\s+(?:nam|bac|dong|tay)(?![a-z0-9]))", hay_loc) is not None

DIST_MARK = re.compile(r"(?<![a-z0-9])(?:thanh pho|tp|thi xa|tx|huyen|quan)\s+([a-z0-9]+(?:\s+[a-z0-9]+){0,2})")

def district_conflict(listing_raw: dict, hay_loc: str, typed_cores: set) -> bool:
    """True nếu tin chắc chắn thuộc HUYỆN/TP khác (dữ liệu có cấu trúc của nguồn hoặc cụm 'huyện/thị xã/thành phố X' trong địa chỉ)."""
    typed = {t for t in typed_cores if t}
    if not typed:
        return False
    raw = listing_raw if isinstance(listing_raw, dict) else {}
    names = [core_loc(n) for n in (raw.get("area_name"), raw.get("area_name_v3")) if n]
    if names:
        return not any(n in typed or any(n.startswith(t + " ") or t.startswith(n + " ") for t in typed) for n in names)
    marks = DIST_MARK.findall(hay_loc)
    if not marks:
        return False
    return not any(m == t or m.startswith(t + " ") for m in marks for t in typed)

def contains_phrase(haystack_norm: str, phrase_norm: str) -> bool:
    return bool(phrase_norm) and re.search(rf"(?<![a-z0-9]){re.escape(phrase_norm)}(?![a-z0-9])", haystack_norm) is not None


# 63 tỉnh/thành trước sáp nhập (đã chuẩn hoá) - dùng để phát hiện tin thuộc tỉnh khác
PROVINCES = {norm(x) for x in (
    "An Giang", "Bà Rịa Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu", "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước",
    "Bình Thuận", "Cà Mau", "Cần Thơ", "Cao Bằng", "Đà Nẵng", "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai",
    "Hà Giang", "Hà Nam", "Hà Nội", "Hà Tĩnh", "Hải Dương", "Hải Phòng", "Hậu Giang", "Hòa Bình", "Hưng Yên", "Khánh Hòa", "Kiên Giang",
    "Kon Tum", "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định", "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ",
    "Phú Yên", "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình",
    "Thái Nguyên", "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang", "Hồ Chí Minh", "Trà Vinh", "Tuyên Quang", "Vĩnh Long", "Vĩnh Phúc",
    "Yên Bái", "Vũng Tàu")}
# Gộp tỉnh từ 01/07/2025 (63 -> 34 tỉnh/thành): mỗi nhóm = các tỉnh cũ nay cùng một tỉnh mới. Tin đăng có thể ghi tên cũ hoặc tên mới.
# Cần đối chiếu với nghị quyết sáp nhập khi cập nhật.
PROVINCE_MERGES = [{norm(x) for x in grp} for grp in (
    ("Hà Giang", "Tuyên Quang"), ("Yên Bái", "Lào Cai"), ("Bắc Kạn", "Thái Nguyên"), ("Vĩnh Phúc", "Hòa Bình", "Phú Thọ"),
    ("Bắc Giang", "Bắc Ninh"), ("Thái Bình", "Hưng Yên"), ("Hải Dương", "Hải Phòng"), ("Hà Nam", "Nam Định", "Ninh Bình"),
    ("Quảng Bình", "Quảng Trị"), ("Quảng Nam", "Đà Nẵng"), ("Kon Tum", "Quảng Ngãi"), ("Bình Định", "Gia Lai"),
    ("Ninh Thuận", "Khánh Hòa"), ("Đắk Nông", "Bình Thuận", "Lâm Đồng"), ("Phú Yên", "Đắk Lắk"),
    ("Bình Dương", "Bà Rịa Vũng Tàu", "Vũng Tàu", "Hồ Chí Minh"), ("Bình Phước", "Đồng Nai"), ("Long An", "Tây Ninh"),
    ("Sóc Trăng", "Hậu Giang", "Cần Thơ"), ("Bến Tre", "Trà Vinh", "Vĩnh Long"), ("Tiền Giang", "Đồng Tháp"),
    ("Bạc Liêu", "Cà Mau"), ("Kiên Giang", "An Giang"), ("Thừa Thiên Huế", "Huế"))]

def province_aliases(admin: "AdminMap", tinh: str) -> set:
    """Tên tỉnh được chấp nhận = tên người dùng nhập + các tỉnh cùng nhóm sáp nhập. KHÔNG trộn bảng đối chiếu xã/phường
    (bảng đó học từ dữ liệu tin và có thể chứa tên xã, làm danh sách tỉnh sai)."""
    if not (tinh or "").strip():
        return set()
    c = core_name(tinh)
    a = {c} if c else set()
    for grp in PROVINCE_MERGES:
        if a & grp:
            a |= grp
    return a

def province_conflict(hay_norm: str, allowed: set) -> bool:
    """True nếu văn bản nhắc một tỉnh KHÁC với tỉnh của tài sản."""
    return any(contains_phrase(hay_norm, p) for p in PROVINCES if p not in allowed)
