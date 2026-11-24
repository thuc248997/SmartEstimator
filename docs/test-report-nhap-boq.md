# Báo cáo kiểm thử — Nhập BoQ từ Excel

Ngày: 24/11/2026 · Nhánh: `feat/nhap-boq-excel` (từ `main` @ `efb630d`) · Môi trường: Docker Compose (Django 5.2.17, DRF 3.18.2, Postgres 16), bản chạy thật tại smartestimator.around-ai.com.

## 1. Tóm tắt

| Hạng mục | Kết quả |
|---|---|
| Test backend (pytest, toàn bộ) | **111 / 111 pass** (32 giây), gồm **31 test mới** của tính năng này |
| Lint / format Python (ruff) | Sạch, 117 file đã đúng định dạng |
| TypeScript (`tsc -b --noEmit`) | Không lỗi |
| Chạy thử trên dữ liệu thật (TT 38/2026, giá Hà Nội) | Đạt, chạy trong transaction rồi rollback, dữ liệu thật không đổi |
| Kiểm thử giao diện (Chrome headless) | Đạt, không lỗi JavaScript |
| Triển khai | Đã build và chạy lại `api` và `worker`; `/healthz` trả `{"status": "ok", "db": "ok"}`; API nhập BoQ trả 401 khi chưa đăng nhập |

**Phạm vi tính năng:**
- Đọc file Excel BoQ bất kỳ, tự dò cột, hạng mục và dòng diễn giải.
- Gợi ý mã TT 38/2026 theo tên có dấu, đơn vị và kích thước; quy đổi đơn vị.
- Tách dòng thiết bị sang Chi phí thiết bị, kèm dòng công lắp đặt.
- Tự áp giá vật liệu từ công bố giá.
- Ghi nhớ lựa chọn mã cho lần nhập sau.
- Nhập xong thì tính dự toán ngay.

## 2. Test tự động mới (`backend/tests/api/test_boq_import.py`)

| Nhóm | Test | Kiểm tra |
|---|---|---|
| Quy đổi đơn vị | `test_conversion_factor` (8 trường hợp) | m3→100m3 = 0,01; m³→1m3; kg→tấn = 0,001; m2→100m2; m→100m; bộ→bộ; m2↔m3 không quy đổi được |
| Đọc số | `test_parse_unit_and_number` | 12,5 · 1.234,5 · 1,234,567 · chữ → None |
| Đọc file | `test_parse_designer_boq_detects_columns_items_and_details` | dò dòng tiêu đề, cột, hạng mục A/B, diễn giải KL, bỏ dòng tổng cộng |
| | `test_parse_two_level_header_and_mismatched_details` | tiêu đề 2 tầng (Khối lượng → Toàn bộ); diễn giải lệch KL thì bỏ diễn giải và cảnh báo |
| | `test_parse_item_column_and_codes_in_file` | cột "Hạng mục" riêng; mã hiệu có sẵn trong file |
| | `test_parse_repeated_header_and_heading_in_other_column` | bỏ dòng tiêu đề lặp; nhận tiêu đề hạng mục nằm ở cột STT ("I. HỆ THỐNG CAMERA") |
| | `test_parse_rejects_non_boq_and_xls`, `test_manual_column_override` | báo lỗi dễ hiểu với file không phải BoQ hoặc file .xls; chỉ định cột bằng tay |
| Gợi ý mã | `test_matcher_uses_dimensions_and_units` | đường kính ≤10 / phi 16 → đúng mã; dày 1,5cm; thiết bị lạ cho độ tin cậy thấp |
| | `test_accents_distinguish_cap_cat` | **hồi quy lỗi thật**: "Cáp Cat6" không còn khớp CH.11210 (đo vẽ mặt cắt, cấp địa hình); tên gõ không dấu vẫn tìm được |
| | `test_router_not_matched_by_dinh_muc` | "Bộ định tuyến Router" không khớp "Lắp đồng hồ đo áp lực, Định mức" |
| | `test_line_kind` (8 trường hợp) | phân loại công tác / thiết bị / trọn gói |
| API + tính toán | `test_preview_then_commit_calculates` | xem trước → nhập → tính xong; quy đổi `820/1000`; ghi chú giữ KL gốc; mã tạm tính TT.01; ghi nhớ lựa chọn |
| | `test_commit_rejects_incompatible_unit_without_factor` | khác loại đơn vị thì từ chối và rollback toàn bộ; có hệ số thì nhập được |
| | `test_equipment_goes_to_equipment_cost_with_install_line` | thiết bị vào Chi phí thiết bị (có/không đơn giá); dòng công lắp "(cho: …)"; vật liệu chính là thiết bị bị đặt giá 0 đ để không tính hai lần; không để hạng mục rỗng |
| | `test_auto_apply_catalog_prices` | áp đúng nhóm theo chương (Xây dựng/Sửa chữa); quy giá tấn → kg; nhiều giá thì không áp; ghi nguồn + trang; chạy lại không áp trùng |
| | `test_preview_bad_file` | file hỏng thì trả 400 kèm hướng dẫn lưu thành .xlsx |

Test cũ (80 test: engine, fixture, luồng API, datasync) vẫn pass, không phải sửa.

## 3. Chạy thử trên dữ liệu thật

### 3.1 File BoQ xây dựng mẫu (10 công tác)

Bộ định mức thật TT 38/2026 (8.551 mã), bộ giá Hà Nội #4. Chạy trong transaction rồi rollback.
- 10/10 dòng được gắn mã. Quy đổi đúng: 64,8 m3 → 0,648 × 100m3; 33,6 m2 → 0,336 × 100m2; 820 kg → 0,82 tấn.
- Dự toán tính xong (`status = done`).
- Một số gợi ý đã đối chiếu tay: bê tông móng rộng 1,2m → AF.11210 (≤250cm); cốt thép cột d>18 cao ≤6m → AF.61431; trát tường trong dày 1,5cm → AK.21220; ván khuôn móng băng → AF.81111 (độ tin cậy cao).

### 3.2 File BoQ điện nhẹ của trường THCS Đại Mạch 2

File dựng lại từ 90 dòng của lần nhập ngày 24/11 trên bản dự toán #21, thêm 4 tiêu đề hệ thống và 1 dòng tiêu đề lặp.

| Chỉ số | Bản cũ (lần nhập của người dùng) | Bản mới |
|---|---|---|
| Hạng mục nhận được | 1 | 4 |
| Dòng tiêu đề lặp bị đọc thành công tác | 1 | 0 |
| Dòng thiết bị | lẫn vào tiên lượng thành tạm tính | 63 vào Chi phí thiết bị (19 kèm công lắp đặt) |
| Lỗi "không có mã định mức" | 82 | 17 (trọn gói + cáp/máng mà TT 38 không có định mức) |
| Mã sai nghiêm trọng | 2 dòng "Cáp Cat6" → CH.11210 (≈ 172 triệu sai) | 0 |
| Vật liệu được tự áp giá | 0 | 4 (thiếc hàn, nhựa thông, cồn công nghiệp, mỡ bò) |
| Vật liệu chính là thiết bị, đặt 0 đ để không tính hai lần | — | ổ cắm, tủ điện |

## 4. Kiểm thử giao diện (Chrome headless)

API được giả lập bằng dữ liệu xem trước thật lấy từ mục 3.2, nên không đăng nhập vào hệ thống thật. Các bước đã kiểm tra:

| Bước | Kết quả |
|---|---|
| Ribbon Trang chủ → **Nhập BoQ từ Excel** → chọn file | Hiện bảng duyệt với 4 hạng mục |
| Thanh tổng hợp | "Nhập 89 dòng: 9 công tác có mã, 17 tạm tính, 63 thiết bị (19 kèm công lắp đặt) · 27 dòng nên xem lại" |
| Nhập đơn giá thiết bị "2.500.000" | Gửi lên `unit_price = 2500000` |
| Đổi loại dòng Công tác ↔ Thiết bị | Trạng thái đổi theo |
| Tra mã khác (F3) cho một dòng | Mã chọn được gửi đúng (kiểm tra ở bản trước) |
| Bấm **Nhập & tính dự toán** | Có thông báo tóm tắt; hộp thoại "Tự áp giá vật liệu" liệt kê 4 vật liệu đã áp và 7 vật liệu cần nhập tay |
| Lỗi JavaScript | Không có |

## 5. Hạn chế đã biết (không chặn merge)

1. **Gợi ý mã chỉ là gợi ý.** TT 38 có nhiều mã trùng tên, nên phần lớn dòng ở trạng thái "Cần xem".
2. **Bộ TT 38 đã nạp không có định mức** cho cáp mạng, cáp quang, máng/thang cáp, loa, tủ rack, patch panel, wifi. Cần nạp định mức chuyên ngành thông tin – truyền thông.
3. **Tự áp giá chỉ áp khi tên trùng hẳn.** Vật liệu có quy cách (ống nhựa, ống HDPE theo đường kính), sơn màu, xăng… vẫn phải nhập tay.
4. **Ô khối lượng là công thức chưa có giá trị lưu** (file chưa từng mở bằng Excel) thì chưa đọc được, trừ phép tính số học đơn giản. File `.xls` phải lưu lại thành `.xlsx`.
5. **Dữ liệu cũ của bản dự toán #21 chưa được sửa.** Hai dòng CH.11210 vẫn còn; cần nhập lại.
6. **Công lắp đặt tính theo hao phí TT 38 đang nạp.** Ví dụ lắp ống nhựa chìm 0,11 công/m, lắp camera ≈ 1,09 triệu/cái. Nên đối chiếu với bản giấy.
7. **Chưa kiểm thử giao diện trên bản chạy thật.** Bước tạo token đăng nhập cho tài khoản demo bị chặn.

## 6. Bổ sung 24/11/2026 (tối) — giá từ dự toán F1, chống nhân đôi thiết bị

Kết quả kiểm tra:

| Hạng mục | Kết quả |
|---|---|
| Test backend | **112 / 112 pass** |
| Test mới | `test_f1_import_and_fill_custom_lines_and_equipment` |
| Test mở rộng | `test_equipment_goes_to_equipment_cost_with_install_line` (thêm bước nhập lại) |
| Ruff, TypeScript | Không lỗi |

Test F1 kiểm tra:
- đọc sheet "Vật liệu" và kỳ giá; bỏ dòng giá 0 / %;
- quy đổi km → m;
- không ghi đè giá đã nhập;
- không ghép "Ổ cắm mạng" với "Ổ cắm thoại";
- khớp vật liệu gần đúng theo tiền tố khi mọi quy cách cùng một giá.

Test nhập lại kiểm tra: nhập lại cùng file thì 0 thiết bị mới.

Áp lên dữ liệu thật:
- Nạp `Dự toán-THPT Thien Loc-FINAL.xlsm` được 46 vật tư có giá (bảng giá #9, Hà Nội 2026-Q3).
- Áp vào bản dự toán THCS #21:
  - lỗi thiếu giá vật liệu 26 → 18;
  - dòng tạm tính chưa có giá 17 → 9;
  - 4 loại thiết bị được điền giá.
- Xóa 63 thiết bị bị nhân đôi do nhập file 2 lần (người dùng đồng ý; đã đối chiếu 63/63 cặp trùng tên, đơn vị, số lượng; có ghi nhật ký `equipment.dedupe`).

## 7. Cách chạy lại

```bash
docker compose exec api pytest -q tests/api/test_boq_import.py   # 31 test của tính năng
docker compose exec api pytest -q                                # toàn bộ 111 test
docker compose exec api ruff check . && docker compose exec api ruff format --check .
cd frontend && npx tsc -b --noEmit
```
