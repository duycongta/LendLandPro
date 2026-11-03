from ..models import Listing

class Source:
    """Mỗi nguồn dữ liệu cài đặt search(); trả về danh sách Listing (kèm raw làm chứng cứ).
    Thêm nguồn mới: tạo file mới, kế thừa Source, đăng ký trong sources/__init__.py."""
    name = "base"
    query_search = False    # True: nhận danh sách câu truy vấn tự nhiên (fetch_queries)
    keyword_search = True   # False: nguồn chỉ hỗ trợ lấy theo tỉnh (fetch_area)
    def search(self, keywords: str, limit: int = 50) -> list[Listing]:
        raise NotImplementedError
