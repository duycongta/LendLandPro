# LendLand Pro - quy tắc làm việc

- Giao diện là một file `index.html` ở thư mục gốc, chạy trên GitHub Pages (không có bước build). App Python nằm trong `server/` (chạy: `cd server && python -m uvicorn app.main:app --port 8000`; test: `cd server && python -m pytest -q`).
- **Mỗi lần sửa `index.html` phải nâng phiên bản:** đổi `APP_VERSION` (vd 6.12 -> 6.13) và thêm một dòng mô tả vào `APP_CHANGELOG` ngay dưới nó. Số phiên bản tự hiện ở tiêu đề tab, màn hình khóa, header và báo cáo in để người dùng nhận biết đã nạp code mới.
- Không ghi cứng chuỗi phiên bản ở chỗ khác; dùng `<span data-app-version></span>` nếu cần hiện thêm.
- Không đưa khóa bí mật mới (API key, Master Key) vào code.
- Không tạo dữ liệu giả cho tài sản so sánh: tin do AI tạo phải gắn nhãn "AI tạo - chưa kiểm chứng" và không đưa vào tính giá khi chưa được người dùng xác nhận.
