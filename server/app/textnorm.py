"""Chuẩn hoá tiếng Việt, ánh xạ tên đơn vị hành chính cũ <-> mới."""
import csv, re, unicodedata
from pathlib import Path

PREFIXES = ("thanh pho", "thi xa", "thi tran", "phuong", "huyen", "quan", "xa", "tp.", "tp", "tinh")

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

    def aliases(self, name: str) -> set[str]:
        """Tên người dùng nhập + mọi tên cũ/mới tương ứng (dạng đã chuẩn hoá)."""
        c = core_name(name)
        if not c:
            return set()
        return {c} | self.old2new.get(c, set()) | self.new2old.get(c, set())

def contains_phrase(haystack_norm: str, phrase_norm: str) -> bool:
    return bool(phrase_norm) and re.search(rf"(?<![a-z0-9]){re.escape(phrase_norm)}(?![a-z0-9])", haystack_norm) is not None
