# LendLand Pro - Tiện ích khảo sát giá BĐS tín dụng

- `index.html`: giao diện web (GitHub Pages: https://duycongta.github.io/LendLandPro/). Số phiên bản hiện ở tiêu đề tab và màn hình PIN.
- `server/`: app Python lấy **tin rao thật có link** (Chợ Tốt, Alonhadat, Batdongsan, Thuviennhadat, Raobannhadat, Google) và cung cấp API cho giao diện.

## Chạy máy chủ khảo giá (trên máy bạn)
```
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```
Sau đó dùng một trong hai cách:
1. Mở https://duycongta.github.io/LendLandPro/ , vào **Quản trị > Máy chủ khảo giá**, để `http://localhost:8000`, bấm **Kiểm tra**.
2. Hoặc mở thẳng **http://localhost:8000/lendland** (cùng giao diện, chạy từ máy chủ này, không cần cấp quyền mạng cục bộ cho trình duyệt).

Chi tiết nguồn tin, khóa Serper/Google/AI và API: xem `server/README.md`.

## Kiểm thử
```
cd server && python -m pytest -q
```
