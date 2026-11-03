# Khảo giá tài sản bảo đảm (bản mẫu)

Công cụ HỖ TRỢ khảo giá từ tin rao bán; kết quả chỉ để tham khảo, không thay thế thẩm định giá.

## Chạy
    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    pytest            # kiểm thử lõi (trích xuất, ánh xạ cũ-mới, thống kê)

## Dùng
- Nhập xã/huyện/tỉnh (tên cũ HOẶC mới đều được), diện tích, loại đất → "Khảo giá".
- Tích "Thu thập mới" để app tự lấy tin từ: Chợ Tốt/Nhà Tốt (API), alonhadat, batdongsan, thuviennhadat, raobannhadat (mở trang kết quả theo tỉnh). Các trang web có thể chặn truy cập tự động: lỗi được ghi ở khung "phễu lọc". Nếu một nguồn bị chặn, bỏ tích nguồn đó và dùng các nguồn còn lại hoặc ô "Thêm tin thủ công". Kết quả lưu SQLite (`data/khaogia.sqlite`).
- Tin Facebook/Zalo: dán nội dung vào ô cuối trang, app tự trích giá/diện tích/loại đất; kiểm tra lại số trước khi dùng.
- Xuất Excel có link nguồn, thời điểm thu thập, đánh dấu tin ngoại lai.

## Việc phải làm trước khi dùng thật
1. `data/admin_mapping.csv`: điền bảng ánh xạ tên đơn vị hành chính cũ→mới theo nghị quyết sáp nhập (file chỉ có dòng ví dụ).
2. `app/sources/chotot.py`: chưa kiểm chứng với API thật (môi trường dev bị chặn mạng). Chạy thử, chỉnh `CATEGORY_LAND`, tên trường nếu cần.
3. Thêm nguồn khác (alonhadat, batdongsan…): tạo lớp kế thừa `Source`; cần mẫu HTML thật và kiểm tra điều khoản sử dụng/pháp chế.
4. Chưa có: tra số tờ/số thửa, bán kính theo toạ độ, ảnh chụp trang làm chứng cứ, phân quyền/đăng nhập.

## Nguồn "Tìm qua Google" (tuỳ chọn)
Gửi truy vấn như "bán nhà đất đường X xã Y Gia Lai" tới dịch vụ tìm kiếm Serper.dev, lấy tiêu đề + đoạn trích kèm link thật, trích giá/diện tích. Chỉ đọc đoạn trích, không mở trang đích.
1. Đăng ký tài khoản tại https://serper.dev → vào Dashboard → copy "API Key". (Xem trang giá của họ về gói miễn phí/trả phí.)
2. Đặt biến môi trường trước khi chạy app. Windows PowerShell (cùng cửa sổ với lệnh chạy app):
```
$env:SERPER_API_KEY="dán-khoá-vào-đây"
$env:ANTHROPIC_API_KEY="..."   # tuỳ chọn: AI đọc các đoạn trích mà cách thường không đọc được
python -m uvicorn app.main:app --port 8000
```
3. Mỗi lần khảo giá dùng khoảng 9 lượt tìm (3 câu truy vấn x tối đa 3 trang). Tin do AI trích ghi "google (AI)" trong cột Nguồn: phải mở link kiểm tra lại. Tin Facebook hầu như không có trong kết quả.
Dự phòng (cũ): Google Custom Search (GOOGLE_API_KEY + GOOGLE_CSE_ID) vẫn được hỗ trợ nếu bạn đã có khoá từ trước 2026; Google đóng API này với khách hàng mới và ngừng hẳn 01/01/2027.

## API cho LendLand Pro (giao diện GitHub Pages)
Chạy app Python trên máy bạn (`python -m uvicorn app.main:app --port 8000`), rồi trong LendLand Pro (Quản trị > "Máy chủ khảo giá") để địa chỉ `http://localhost:8000`.
- `GET /api/health`: kiểm tra kết nối.
- `GET /api/comps?xa=&huyen=&tinh=&duong=&area=&kind=dat|nha|can_ho&months=12&tol=100&live=1&maxn=100`: trả tin so sánh THẬT (có link), xếp cùng đường lên đầu. `live=1` thu thập mới từ các trang rao trước (mất vài phút).
- Chỉ các nguồn gốc `https://duycongta.github.io` và `localhost` được phép gọi (đổi bằng biến môi trường `ALLOWED_ORIGIN_REGEX`). Chrome có thể hỏi quyền "truy cập thiết bị trong mạng cục bộ": chọn Cho phép.
