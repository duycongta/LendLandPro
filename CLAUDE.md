# LendLand Pro - quy tắc làm việc

- Ứng dụng là một file `index.html` chạy trên GitHub Pages (không có bước build).
- **Mỗi lần sửa `index.html` phải nâng phiên bản:** đổi `APP_VERSION` (vd 6.6 -> 6.7) và thêm một dòng mô tả vào `APP_CHANGELOG` ngay dưới nó. Số phiên bản tự hiện ở tiêu đề tab, màn hình khóa, header và báo cáo in để người dùng nhận biết đã nạp code mới.
- Không ghi cứng chuỗi phiên bản ở chỗ khác; dùng `<span data-app-version></span>` nếu cần hiện thêm.
- Không đưa khóa bí mật mới (API key, Master Key) vào code.
