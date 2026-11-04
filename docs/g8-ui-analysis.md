# Phân tích giao diện Dự toán G8 và đối chiếu với SmartEstimator

Cập nhật: 04/11/2026

## Nguồn

- *Tài liệu hướng dẫn sử dụng Dự toán – Dự thầu G8, Version 2008*, 54 trang, Công ty CP Công nghệ Hoàng Hà (bản PDF trên qnu.edu.vn). Văn bản được trích bằng `pdftotext`.
  - Tài liệu cũ: căn cứ pháp lý là NĐ 99/2007 và TT 05/2007.
  - Bố cục màn hình và luồng thao tác của G8 về cơ bản vẫn giữ đến bản 2026.
- Trang hướng dẫn nhanh phanmemg8.vn. Bản mới đổi tên một số sheet: *Công Trình*, *Giá Tháng*, *Đầu Vào*, *Nhân Công*, *Máy*, *CVC và Cước bộ*, *THKP hạng mục*.
- Trang sản phẩm G8 Enterprise (danh sách tính năng do nhà phát hành công bố).

Đây là phân tích **chức năng và luồng thao tác** để làm tính năng tương đương. Không sao chép mã nguồn, dữ liệu, giao diện đồ họa hay thương hiệu của G8.

## 1. Bố cục chung của G8

- Giao diện giống Excel nhưng không chạy trên Excel. Các bảng nằm ở tab sheet dưới đáy, và **các sheet liên kết với nhau**: sửa ở một sheet thì các sheet khác tự cập nhật.
- Menu chính: File · Công trình · Đơn giá · Cấu hình · Đấu thầu · Thẩm định · Lập tiến độ · Công cụ.
- Có thể mở nhiều công trình cùng lúc. Phím tắt: Ctrl+N tạo mới, Ctrl+O mở, Ctrl+S lưu.
- Góc dưới trái sheet Công Trình chọn **Tỉnh/TP → bộ đơn giá**. G8 tự suy ra bộ định mức và giá VL/NC/Máy đi kèm, người dùng không phải chọn từng tệp.
- **Đa đơn giá, đa hạng mục**: mỗi hạng mục có thể dùng bộ đơn giá riêng và bộ hệ số chi phí riêng.

## 2. Danh sách sheet của G8 và chức năng

| Sheet G8 | Chức năng |
|---|---|
| **Công Trình** (tiên lượng) | Nhập công tác và diễn giải khối lượng |
| **Giá Tháng / GiaTB** | Liệt kê mọi hao phí VL/NC/Máy của công trình; nhập giá thông báo |
| **Tổng hợp VT** | Tổng hợp vật tư và **chênh lệch giá** (giá TB − giá gốc); nhiều kiểu bảng như THVT, THVT + giá gốc… |
| **Phân tích VT** | Hao phí VL/NC/Máy theo từng mã; thanh tùy biến ẩn/hiện phần |
| **Cước VC** | Cước vận chuyển cho từng vật liệu, có nhiều cung đường |
| **Đầu Vào / Nhân Công / Máy** (bản mới) | Lương đầu vào, phụ cấp, giá nhiên liệu; bù nhân công, bù máy |
| **THKP hạng mục** | Tổng hợp kinh phí của từng hạng mục, chọn thông tư và hệ số |
| **TH Chi phí XD** | Mọi hạng mục: trước thuế, VAT, sau thuế; tổng cộng **bằng số và bằng chữ** |
| **TH Chi phí TB** | Nhập chi phí thiết bị (giá trước thuế, VAT, sau thuế) tách khỏi xây lắp |
| **TH Kinh phí** | Tổng mức toàn công trình; tự tra tỷ lệ chi phí QLDA, tư vấn, thẩm định theo loại và cấp công trình |
| **Chiết tính / Dự thầu / Đơn giá chi tiết** | Chiết tính đơn giá từng công tác (hao phí × giá × hệ số) và đơn giá dự thầu |
| **Bìa** | 2 tờ bìa: Hồ sơ dự toán và Thuyết minh dự toán (tên công trình, địa điểm, chủ đầu tư, đơn vị lập, giá trị) |
| **Thẩm định** | So tiên lượng với định mức và đơn giá; tô **đỏ** chỗ sai và tự đánh dấu để in |

## 3. Thao tác nhập tiên lượng (sheet Công Trình)

**Cột chính:** STT · Mã số đơn giá · Tên công tác / Diễn giải khối lượng · Đơn vị · (Số cấu kiện · Dài · Rộng · Cao, có thể ẩn hoặc hiện) · Khối lượng · Đơn giá VL / NC / Máy · Thành tiền VL / NC / Máy.

1. **Gõ mã đủ rồi Enter** (vd `AF.11111`) để nhận công tác.
2. **Tra mã theo phần đầu mã**: gõ `AE` rồi Enter (hoặc Enter 2 lần khi ô trống) để mở danh sách *Tra công tác*. Danh sách có **ô tích chọn nhiều mã** và nút chấp nhận để chèn tất cả.
3. **Tra theo tên**: gõ từ khóa vào cột Tên, có thể nhiều từ cách nhau bằng dấu phẩy (vd `Trát,75`), rồi Enter. Danh sách lọc theo tất cả từ khóa.
4. **Diễn giải khối lượng** nằm ngay dưới dòng công tác, mỗi diễn giải một dòng:
   - Dòng kết thúc bằng `:` là ghi chú.
   - `Móng M1: 1.2*1.8*0.85` là chú thích + công thức, ngăn cách bằng dấu `:`.
   - Dòng chỉ có công thức thì gõ thẳng công thức.
   - Hoặc nhập theo cột **Dài × Rộng × Cao × Số cấu kiện**.
   - Khối lượng công tác = tổng các dòng diễn giải.
   - Nếu dòng gõ vào không phải công thức cũng không phải ghi chú, G8 coi đó là từ khóa tra cứu.
5. **Chèn dòng**: Insert, hoặc chuột phải → *Chèn dòng*. **Xóa dòng**: F8, hoặc chuột phải → *Xóa dòng*.
6. **Sao chép công tác**: bôi đen nhiều hàng → chuột phải → *Sao chép công tác* → *Dán các công tác*. Sao chép kèm cả hao phí và diễn giải.
7. **Thêm hạng mục**: gõ mã `HM` dưới dòng tổng hạng mục trước đó.
8. **Hệ số chi phí xây lắp** (menu Công trình): bộ hệ số riêng theo từng hạng mục.

## 4. Giá và dữ liệu gốc

- Nhập giá thông báo theo hai cách:
  - (a) nhập thẳng vào cột giá TB, chỉ áp cho công trình hiện tại;
  - (b) tạo **bảng giá thông báo** dùng lại cho nhiều công trình: chuột phải → *Lắp giá thông báo*.
- **Đơn giá → Vật liệu / Nhân công / Ca máy / Định mức / Đơn giá**: các màn hình sửa CSDL.
  - Màn hình định mức có 2 bảng: *Bảng định mức* phía trên và *Bảng hao phí* phía dưới.
  - Có tìm theo mã hoặc tên, lọc theo nhóm, và **tạo định mức mới** (trắng hoặc dựa trên bộ hiện hành).
  - Cột "Riêng" cho phép hao phí chỉ áp cho một tỉnh.

## 5. Tiện ích khác

- **Xuất Excel** toàn bộ hồ sơ, đầy đủ công thức. Có thể xuất toàn bộ hoặc chọn bảng.
- **Lấy tiên lượng từ Excel**: chọn kiểu file có sẵn, hoặc khai báo cột và sheet (mapping).
- **Thẩm định** toàn bộ dự án: báo lỗi về mã, công thức khối lượng và đơn giá VL/NC/Máy.
- **Tiến độ thi công**: sơ đồ ngang, biểu đồ nhân lực, xuất AutoCAD.
- **Cước vận chuyển**: theo trọng lượng đơn vị, bậc hàng, loại đường, cự ly; có cước bộ, cước sông, bù % và bù tiền; có thể sửa mẫu tính.

## 6. Đối chiếu với SmartEstimator

| Chức năng G8 | SmartEstimator trước đợt này | Đợt này |
|---|---|---|
| Lưới giống Excel, tab sheet, thanh công thức | ✅ có | — |
| Gõ mã, gợi ý theo mã hoặc tên | ✅ (chọn được 1 mã) | **Tra mã**: nhiều từ khóa `Trát,75`, phần đầu mã `AE`, lọc nhóm, xem hao phí, **tích chọn nhiều mã** |
| Diễn giải khối lượng nhiều dòng (ghi chú / công thức / D×R×C×CK) | ❌ chỉ một công thức | ✅ dòng con dưới công tác |
| Chuột phải: chèn, xóa (F8), sao chép/dán công tác | ❌ | ✅ menu chuột phải, F8, Ctrl+C/V công tác, Alt+↑↓ di chuyển |
| Mã tạm tính có đơn giá | ❌ ra 0đ | ✅ nhập đơn giá VL/NC/M tạm tính; sửa Knc/Km |
| Thông tin công trình (chủ đầu tư, đơn vị lập…) | ❌ | ✅ hộp thoại + đổi bộ giá / kỳ giá ("áp giá") |
| THKP theo hạng mục | ❌ chỉ toàn công trình | ✅ |
| TH Chi phí XD (theo hạng mục, bằng chữ) | ❌ | ✅ |
| TH Chi phí thiết bị | ❌ | ✅ |
| Bìa hồ sơ | ❌ | ✅ (web + Excel) |
| Giá riêng cho dự án, có lý do | ✅ | — |
| Chênh lệch giá (giá gốc ↔ giá TB) | ❌ (phương pháp giá trực tiếp) | để sau — cần bộ đơn giá gốc |
| Bộ hệ số riêng theo hạng mục | ❌ | để sau |
| Chiết tính, đơn giá dự thầu | một phần (sheet Phân tích) | để sau |
| Nhập Excel có mapping cột, Thẩm định | ❌ | để sau (P1) |
| Quản trị định mức / đơn giá / định mức tự lập | ❌ (chỉ đọc API) | để sau (P1) |
| Cước vận chuyển | ❌ | để sau (P1) |
| Tiến độ thi công, biểu đồ nhân lực | ❌ | để sau (P2) |
