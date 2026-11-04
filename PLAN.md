# SmartEstimator — Kế hoạch việc còn lại (TODO)

Cập nhật: 04/11/2026 (sau đợt giao diện tương tự G8)

## Trạng thái hiện tại

- Đợt 1 xong:
  - Docker Compose: Postgres, Redis, api (gunicorn), worker (Celery).
  - Backend Django/DRF.
  - Engine Decimal theo TT 36/2026: công thức 4.1–4.4 và Bảng 3.3–3.8.
  - Xuất Excel 5 sheet có công thức.
  - 52 test pass, ruff sạch.
- Giao diện kiểu Excel (React + AG Grid Community) đã chạy tại https://smartestimator.around-ai.com qua Cloudflare tunnel `around-ai`.
- Dữ liệu định mức và giá hiện là **fixture MẪU** (`backend/fixtures/sample_catalog.json`). Rule pack lấy số thật từ Phụ lục III TT 36/2026.

Ký hiệu: `[ ]` chưa làm · `[?]` cần người dùng xác nhận · ưu tiên P0 > P1 > P2.

---

## 1. Cần người dùng xác nhận (không chặn code)

- [?] Thuế GTGT mặc định **10%** (`vat_rate` trong rule pack).
- [?] Chính sách làm tròn mặc định, kiểu HALF_UP:
  - khối lượng 3 chữ số;
  - hao phí 4 chữ số;
  - giá / đơn giá / thành tiền làm tròn đến đồng (0 chữ số).
- [?] Cách hiểu dòng **LT** (nhà tạm) ở Bảng 3.8: hiện tính `GXDTT × tỷ lệ × (1 + TGTGT)` và để thành dòng riêng.
- [?] Đối chiếu đính chính **QĐ 1538/QĐ-BXD (28/8/2026)** và văn bản hợp nhất 89/2026/VBHN-TT-BXD, rồi phát hành rule pack **v1.1**. Hiện rule pack có cờ `needs_review_errata=true`.

## 2. Bảo mật & vận hành — P0

- [ ] Đổi mật khẩu tài khoản `demo`:
  ```
  docker compose exec api python manage.py changepassword demo
  ```
  Bỏ ghi chú mật khẩu mặc định khỏi README.
- [ ] Bật **Cloudflare Access (Zero Trust)** cho `smartestimator.around-ai.com`. Cần danh sách email hoặc domain được phép truy cập.
- [ ] Commit code lên git:
  - tạo nhánh trước, không commit thẳng `main`;
  - không commit `.env`.
- [ ] Sao lưu Postgres định kỳ (volume `pgdata`): `pg_dump` theo cron và giữ N bản.
- [ ] CI (GitHub Actions) chạy pytest, ruff, `tsc` và build frontend.

## 3. Dữ liệu thật — P0/P1

> 04/11/2026: Đã nạp TT 38/2026 (8.551 mã), giá nhân công QĐ 2036, ca máy QĐ 2037 và công bố giá vật liệu quý III/2026 của Hà Nội. Có nút "Kiểm tra & cập nhật dữ liệu" và lệnh `manage.py update_data`.

- [ ] Bổ sung tệp **QĐ 2075/QĐ-SXD** (31/10/2026, thay QĐ 2037) vào `fixtures/data_sources.json` khi Sở đăng tệp.
- [ ] Sửa 139 bảng TT 38 chưa bóc được; nhờ kỹ sư dự toán đối chiếu ngẫu nhiên theo số trang.
- [ ] Tính giá vữa / bê tông theo cấp phối Phụ lục VII (giá xi măng, cát, đá theo công bố) thay cho nhập tay.
- [ ] Ghép nốt khoảng 12% lượt máy chưa ghép được; cho phép ghép tay (máy định mức ↔ mã M của bảng giá).
- [ ] Đặt cron chạy `update_data` hằng tuần, có thông báo khi có bản mới.
- [ ] Mở rộng sang các tỉnh khác: mỗi tỉnh cần một bộ dò cổng Sở XD và bộ bóc tách riêng.

- [x] **Importer định mức TT 38/2026** (xong 04/11/2026; xem trên). Nguồn: PDF ký số tại datafiles.chinhphu.vn.
  - Parse: mã, tên, đơn vị, hao phí VL/NC/M, dòng "vật liệu khác %" / "máy khác %".
  - Kiểm tra trước khi nạp: trùng mã, thiếu đơn vị, hao phí âm.
  - Nạp thành `DatasetRelease`, có quy trình draft → reviewed → published.
- [ ] Nạp đủ nhóm lắp đặt **điện nhẹ** thật (BA/BB…) thay cho dữ liệu mẫu.
- [ ] Importer **bảng giá**: công bố giá VL địa phương, đơn giá nhân công, giá ca máy theo tỉnh và kỳ.
- [ ] Gỡ nhãn "DỮ LIỆU MẪU" khi đã dùng dữ liệu thật.

## 4. Tính năng nghiệp vụ — P1

> Đợt "giao diện tương tự G8" (04/11/2026) đã xong:
> - tra mã chọn nhiều;
> - diễn giải khối lượng nhiều dòng (Số CK × D × R × C);
> - đơn giá tạm tính;
> - menu chuột phải và phím tắt G8 (Insert, F3, F8, Alt+↑↓);
> - sao chép/dán công tác;
> - thông tin công trình và đổi bộ giá;
> - THKP theo hạng mục, TH chi phí XD (bằng chữ), chi phí thiết bị, bìa;
> - Excel 8 sheet.
>
> Phân tích chi tiết: `docs/g8-ui-analysis.md`.

- [x] Nhập đơn giá cho mã tạm tính: nhập VL/NC/M trực tiếp trên dòng (engine 0.2.0, cảnh báo `CUSTOM_ITEM`, không chặn duyệt).
- [ ] **Định mức tự lập** cho từng dòng: sửa hoặc thêm hao phí (G8: "Đơn giá → Định mức", cột "Riêng").
- [ ] **Chênh lệch giá** kiểu G8 (giá gốc ↔ giá thông báo, bảng THVT + giá gốc) và lưu **bảng giá thông báo** dùng lại cho nhiều công trình ("Lắp giá thông báo").
- [ ] **Bộ hệ số chi phí riêng theo hạng mục** (G8: Công trình → Hệ số chi phí xây lắp). Hiện tỷ lệ chọn theo cả công trình rồi áp cho từng hạng mục.
- [ ] **Chiết tính / đơn giá dự thầu / đơn giá chi tiết** (G8: sheet Chiết tính, Dự thầu; menu Đấu thầu, F5).
- [ ] **Nhập tiên lượng từ Excel có mapping cột** và **Thẩm định**: tô đỏ chỗ sai mã, công thức, đơn giá; có báo cáo để in.
- [ ] **Cước vận chuyển**: trọng lượng đơn vị, bậc hàng, loại đường, cự ly; cước bộ, cước sông, bù %, bù tiền.
- [ ] **Quản trị CSDL định mức / đơn giá / giá VL-NC-M** trên web (tìm, lọc nhóm, thêm/sửa, tạo bộ mới dựa trên bộ hiện hành).
- [ ] **Undo/redo** cho thao tác trên lưới.
- [ ] Ghép tiên lượng của nhiều người thành một dự toán (G8: "nối tiên lượng").
- [ ] Phương pháp **bù chênh lệch giá** (đơn giá gốc + chênh lệch), song song với phương pháp giá hiện trường trực tiếp.
- [ ] Màn hình **giải trình (explain)** cho từng thành tiền, gồm KL, định mức, giá, nguồn giá và các bước làm tròn. API đã có; giao diện chưa có.
- [ ] So sánh 2 phiên bản dự toán (diff dòng và tổng).
- [ ] Phân quyền theo vai trò (lập / kiểm tra / phê duyệt) dựa trên `Membership`.
- [ ] Thêm mẫu xuất Excel theo biểu mẫu chủ đầu tư; xuất PDF.

## 5. Giao diện (UX) — P2

- [x] Sắp xếp dòng bằng Alt+↑/↓ và menu chuột phải (kéo-thả chưa làm).
- [ ] Kéo-thả để sắp xếp dòng và hạng mục; di chuyển dòng giữa các hạng mục.
- [ ] Chọn vùng nhiều ô, copy/fill. Range selection là tính năng của AG Grid Enterprise, nên phải tự làm hoặc cân nhắc mua license.
- [ ] Tối ưu cho tablet và điện thoại (hiện tối ưu cho màn hình từ khoảng 1280px).
- [ ] Đưa test UI tự động (Playwright) vào repo và CI.

## 6. Kỹ thuật — P2

- [ ] Celery: hiển thị tiến trình tính cho dự toán lớn (> 500 dòng).
- [ ] Logging / monitoring cho container `api` và `worker`.
- [ ] Rà lại tài liệu `docs/data-dictionary.md` và `docs/rule-pack-tt36-2026.md` sau khi có rule pack v1.1.
