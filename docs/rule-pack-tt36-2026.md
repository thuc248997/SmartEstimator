# Rule pack `TT36-2026` v1.0

**Nguồn:** Phụ lục III và IV, Thông tư 36/2026/TT-BXD ngày 26/06/2026 của Bộ Xây dựng (hiệu lực 01/07/2026).
PDF phụ lục: https://cdn.thuvienphapluat.vn/uploads/khoinghiep/2026/06/29/Ph%E1%BB%A5-l%E1%BB%A5c-Th%C3%B4ng-t%C6%B0-36-2026-TT-BXD.pdf (trích bằng `pdftotext` ngày 04/11/2026).
**Tình trạng:** số liệu trích từ PDF chính thức, **chưa được kỹ sư dự toán ký duyệt**; **chưa đối chiếu** đính chính QĐ 1538/QĐ-BXD (28/08/2026) và VBHN 89/2026/VBHN-TT-BXD. File dữ liệu: `backend/fixtures/rule_pack_tt36_2026.json`.

## Bảng 3.8 – thứ tự tính (engine `summary`)

| Ký hiệu | Cách tính |
|---|---|
| T | VL + NC + M |
| C | T × tỷ lệ Bảng 3.3 (hoặc NC × tỷ lệ Bảng 3.4 khi `overhead_basis=LABOR`) × 1,1 nếu vùng núi/biên giới/biển/hải đảo |
| TT | T × tỷ lệ Bảng 3.5 |
| GT | C + TT |
| TL | (T + GT) × tỷ lệ Bảng 3.6 |
| GXDTT | T + GT + TL |
| GTGT | GXDTT × TGTGT (tham số, mặc định 10%) |
| GXD | GXDTT + GTGT |
| LT | GXDTT × tỷ lệ Bảng 3.7; engine tách LT trước thuế, LT×VAT, LT sau thuế (*cách hiểu cần xác nhận*) |

Knc, Km (làm đêm/lễ): nhập ở từng dòng; `Km = 1 + g × (Knc − 1)` do người dùng tính và nhập.

## Bảng 3.3 – chi phí chung (% trên T), ngưỡng chi phí XD trước thuế trong TMĐT (tỷ đồng), **không nội suy**

| Loại | ≤40 | ≤60 | ≤100 | ≤300 | ≤500 | ≤750 | ≤1000 | >1000 |
|---|---|---|---|---|---|---|---|---|
| Dân dụng | 7,3 | 7,1 | 6,7 | 6,5 | 6,2 | 6,1 | 6,0 | 5,8 |
| Tu bổ di tích | 11,6 | 11,1 | 10,3 | 10,1 | 9,9 | 9,8 | 9,6 | 9,4 |
| Công nghiệp | 6,2 | 6,0 | 5,6 | 5,3 | 5,1 | 5,0 | 4,9 | 4,6 |
| Hầm thủy điện, hầm lò | 7,3 | 7,2 | 7,1 | 6,9 | 6,7 | 6,6 | 6,5 | 6,4 |
| Giao thông | 6,2 | 6,0 | 5,6 | 5,3 | 5,1 | 5,0 | 4,9 | 4,6 |
| Hầm giao thông | 7,3 | 7,2 | 7,1 | 6,9 | 6,7 | 6,6 | 6,5 | 6,4 |
| NN & môi trường | 6,1 | 5,9 | 5,5 | 5,3 | 5,1 | 5,0 | 4,8 | 4,6 |
| Đường hầm (NN&MT) | 7,3 | 7,2 | 7,1 | 6,9 | 6,7 | 6,6 | 6,5 | 6,4 |
| Hạ tầng kỹ thuật | 5,5 | 5,3 | 5,0 | 4,8 | 4,5 | 4,4 | 4,3 | 4,0 |

Báo cáo KT-KT → cột ≤40. Nếu dự án chưa có TMĐT duyệt, engine chọn ngưỡng theo GXDTT tính ra (lặp điểm bất động) và phát cảnh báo `THRESHOLD_BASIS_DERIVED`.

## Bảng 3.4 – chi phí chung (% trên NC), ngưỡng NC (tỷ đồng)

| Nội dung | ≤15 | ≤50 | ≤100 | >100 |
|---|---|---|---|---|
| Bảo dưỡng đường bộ, đường sắt, báo hiệu hàng hải (*tên bị đính chính "Sửa chữa"?*) | 66 | 63 | 60 | 56 |
| NN&MT thực hiện hoàn toàn thủ công | 51 | 48 | 45 | 42 |
| Lắp đặt thiết bị công nghệ; đường dây tải điện & TBA; thí nghiệm hiệu chỉnh | 65 | 62 | 59 | 55 |

## Bảng 3.5 – CV không xác định được KL (% trên T)
Dân dụng 2,5; công nghiệp / giao thông / NN&MT / HTKT 2,0; công tác trong hầm 6,5. (HERITAGE → 2,5; EQUIPMENT_INSTALL → 2,0: giả định, cần xác nhận.)

## Bảng 3.6 – TNCTTT (% trên T+GT)
Dân dụng 5,5; công nghiệp 6,0; giao thông 6,0; NN&MT 5,5; HTKT 5,5; lắp đặt thiết bị công nghệ/đường dây-TBA/thí nghiệm hiệu chỉnh 6,0; tự khai thác VL 3,0.

## Bảng 3.7 – nhà tạm (% trên chi phí XD), ngưỡng chi phí XD trước thuế trong TMĐT (tỷ đồng)

| Loại | ≤15 | ≤100 | ≤500 | ≤1000 | >1000 |
|---|---|---|---|---|---|
| Theo tuyến | 2,2 | 2,0 | 1,9 | 1,8 | 1,7 |
| Còn lại | 1,1 | 1,0 | 0,95 | 0,9 | 0,85 |

## Tham số cần xác nhận
1. VAT mặc định 10% (có thể ghi đè theo dự án `Project.vat_rate`).
2. Làm tròn: KL 3, hao phí 4, đơn giá 0, thành tiền 0, HALF_UP.
3. Cách hiểu dòng LT trong Bảng 3.8.
4. Đối chiếu đính chính QĐ 1538/QĐ-BXD → phát hành v1.1 (không sửa v1.0).
