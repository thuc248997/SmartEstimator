"""Bộ bóc tách TT 38/2026 và bảng giá Hà Nội — chạy trên mẫu nhỏ, không cần mạng."""

from decimal import Decimal

import pytest

from apps.datasync.parsers import hanoi_prices, tt38
from apps.datasync.parsers.match import MachineMatcher, canonical_labor

# Tọa độ thật của bảng AF.111 (trang 479 PDF TT 38/2026): x0 y0 x1 y1 text
AF111 = """
70.9 217.3 119.2 228.1 AF.11100|128.2 217.3 143.6 228.1 BÊ|146.6 217.3 179.9 228.1 TÔNG|182.9 217.3 206.2 228.1 LÓT
209.2 217.3 245.9 228.1 MÓNG|459.6 237.4 480.4 250.7 Đơn|483.2 239.9 492.4 250.7 vị|495.2 239.9 516.8 250.7 tính:
519.6 239.9 534.9 250.7 1m|534.75 239.0 538.75 246.2 3|433.6 262.6 462.2 275.9 Chiều|465.2 262.6 487.2 275.9 rộng
490.2 265.1 512.9 275.9 (cm)|363.5 266.1 384.5 279.4 Đơn|84.4 275.5 100.4 286.3 Mã|103.4 273.0 124.1 286.3 hiệu
140.8 275.5 166.8 286.3 Công|169.8 275.5 183.8 286.3 tác|186.8 275.5 204.1 286.3 xây|207.1 273.0 231.6 286.3 dựng
248.2 275.5 278.9 286.3 Thành|281.9 273.0 305.2 286.3 phần|308.2 275.5 325.5 286.3 hao|328.5 275.5 343.9 286.3 phí
369.3 279.9 378.7 293.2 vị|421.9 282.5 446.5 297.2 \uf0a3\uf032\uf035\uf030|499.8 286.0 524.6 296.8 &gt;250
86.1 306.8 122.4 317.6 AF.111|138.4 306.8 151.7 317.6 Bê|154.7 306.8 176.1 317.6 tông|179.1 306.8 191.7 317.6 lót
194.7 306.8 222.1 317.6 móng|244.75 305.8 261.4 319.1 Vật|264.4 305.8 282.4 319.1 liệu
244.75 325.2 265.2 338.4 Vữa|268.2 327.7 279.6 338.5 bê|282.6 327.7 303.9 338.5 tông|367.3 327.7 376.7 338.5 m
376.7 326.7 380.7 333.9 3|420.7 327.7 447.7 338.5 1,025|498.7 327.7 525.7 338.5 1,025
244.75 348.5 270.8 359.3 Nhân|273.8 348.5 297.1 359.3 công|300.1 348.5 326.7 359.3 nhóm|329.7 348.5 335.7 359.3 2
362.3 348.5 385.7 359.3 công|423.7 348.5 444.7 359.3 1,07|501.7 348.5 522.7 359.3 0,89
244.75 369.4 266.1 380.2 Máy|269.1 369.4 281.7 380.2 thi|284.7 369.4 308.1 380.2 công
244.75 390.2 266.7 401.0 Máy|269.7 387.7 289.1 401.0 trộn|292.1 390.2 313.4 401.0 250l|368.7 390.2 379.3 401.0 ca
420.7 390.2 447.7 401.0 0,095|498.7 390.2 525.7 401.0 0,095
244.75 411.1 266.7 421.9 Máy|269.7 408.6 290.4 421.8 đầm|293.4 411.1 310.7 421.9 bàn|313.7 411.1 319.7 421.9 1
322.7 411.1 340.1 421.9 kW|368.7 411.1 379.3 421.9 ca|420.7 411.1 447.7 421.9 0,089|498.7 411.1 525.7 421.9 0,089
428.2 431.4 440.2 442.2 10|506.2 431.4 518.2 442.2 20
"""


def _bbox(spec: str, appendix_cover: bool = True) -> str:
    words = []
    for line in spec.strip().splitlines():
        for w in line.split("|"):
            x0, y0, x1, y1, text = w.split(" ", 4)
            text = text.encode().decode("unicode_escape") if "\\u" in text else text
            words.append(f'<word xMin="{x0}" yMin="{y0}" xMax="{x1}" yMax="{y1}">{text}</word>')
    cover = (
        '<page width="595" height="842"><word xMin="100" yMin="300" xMax="200" yMax="310">(Phụ</word>'
        '<word xMin="201" yMin="300" xMax="220" yMax="310">lục</word><word xMin="221" yMin="300" xMax="230" yMax="310">II</word>'
        '<word xMin="231" yMin="300" xMax="260" yMax="310">kèm</word><word xMin="261" yMin="300" xMax="290" yMax="310">theo</word></page>'
    )
    return (
        "<doc>"
        + (cover if appendix_cover else "")
        + '<page width="595" height="842">'
        + "".join(words)
        + "</page></doc>"
    )


def test_tt38_table_parsed_with_column_suffixes_and_symbols():
    recs, rep = tt38.parse_tt38(_bbox(AF111))
    by = {r.code: r for r in recs}
    assert set(by) == {"AF.11110", "AF.11120"}
    a = by["AF.11110"]
    assert a.name == "Bê tông lót móng, Chiều rộng (cm) ≤250" and a.unit == "1m3" and a.appendix == "II"
    comps = {(c.kind, c.name, c.unit): c.quantity for c in a.components}
    assert comps == {
        ("MATERIAL", "Vữa bê tông", "m3"): "1.025",
        ("LABOR", "Nhân công nhóm 2", "công"): "1.07",
        ("MACHINE", "Máy trộn 250l", "ca"): "0.095",
        ("MACHINE", "Máy đầm bàn 1 kW", "ca"): "0.089",
    }
    assert {c.quantity for c in by["AF.11120"].components if c.kind == "LABOR"} == {"0.89"}
    assert rep.records == 2 and not rep.skipped_tables


@pytest.mark.parametrize(
    "base,suffix,code", [("AF.111", "10", "AF.11110"), ("AC.2232", "1", "AC.22321"), ("14.110", "01", "14.11001")]
)
def test_join_code(base, suffix, code):
    assert tt38._join_code(base, suffix) == code


LABOR_TXT = """
 Số: 2036 /QĐ-SXD                  Hà Nội, ngày26 tháng10 năm 2026
  I                  Nhóm nhân công xây dựng
  1    Nhóm 1        chuẩn bị mặt bằng                           409.000 358.000
   2 Nhóm 2 tông, ván khuôn, cốt thép                            428.000 372.000
   3 Nhóm 3 kết cấu sắt thép; cáp thép; trát, ốp, lát,         443.000 386.000
   4 Nhóm 4                                                    470.000 409.000
   1 Nhân công vận hành máy, điều khiển máy                    474.000 407.000
   2 Lái xe                                                    451.000 388.000
   3 Vận hành tầu thuyền (Thuyền trưởng)                       456.000 419.000
   1 Kỹ sư thực hiện khảo sát, thí nghiệm                      451.000 419.000
   2 Thợ lặn                                                   790.000 729.000
   3 Nghệ nhân                                                 707.000 648.000
"""


def test_labor_table_and_doc_info():
    info = hanoi_prices.doc_info(LABOR_TXT)
    assert info.number == "2036/QĐ-SXD" and info.issued_on == "2026-10-26"
    rows = {r.name: (r.vung1, r.vung2) for r in hanoi_prices.parse_labor(LABOR_TXT)}
    assert rows["Nhân công nhóm 2"] == ("428000", "372000") and rows["Nghệ nhân"] == ("707000", "648000")


MACHINE_TXT = """
                  CHƯƠNG I: MÁY VÀ THIẾT
                Máy trộn vữa - dung tích:
      M104.0100
107   M104.0101  80 lít                     200   20,0  5,40  5   4  kWh  1 nhân công vận hành  1x3/7   10.000   7.200   458.300  393.500   520.111   455.311
108   M104.0102  150 lít                    200   20,0  5,40  5   8  kWh  1 nhân công vận hành  1x3/7   15.000  14.400   458.300  393.500   536.954   472.154
                Máy đào 1,25 m3 gắn đầu búa
9     M101.0115                             280   17,0  5,80  5  83  lít diezel  1x4/7   2.150.000  2.238.284  514.539  441.809  4.756.930  4.684.200
                thủy lực/hàm kẹp
"""


def test_machine_table_names_and_prices():
    ms = {m.code: m for m in hanoi_prices.parse_machines(MACHINE_TXT)}
    assert ms["M104.0102"].name == "Máy trộn vữa - dung tích 150 lít"
    assert (ms["M104.0102"].vung1, ms["M104.0102"].vung2) == ("536954", "472154")
    assert ms["M101.0115"].name == "Máy đào 1,25 m3 gắn đầu búa thủy lực/hàm kẹp"


def test_machine_matcher_and_labor_alias():
    m = MachineMatcher(
        [("M104.0101", "Máy trộn vữa - dung tích 80 lít"), ("M104.0102", "Máy trộn vữa - dung tích 150 lít")]
    )
    assert m.match("Máy trộn vữa 150l")[0] == "M104.0102"
    assert m.match("Máy cắt uốn 5 kW") is None
    assert canonical_labor("nhóm 3") == "Nhân công nhóm 3" and canonical_labor("Kỹ sư 4,0/8") == "Kỹ sư"


def test_material_catalog_lines():
    txt = "      I - NHÓM VẬT LIỆU CÁT:\n      Bãi Trung Hà, xã Vật Lại\n 1    Cát đen      m3     281.818\n 2    Cát vàng     m3     636.364\n"
    rows = hanoi_prices.parse_materials(txt)
    assert [(r.name, r.unit, r.price) for r in rows] == [("Cát đen", "m3", "281818"), ("Cát vàng", "m3", "636364")]
    assert "Bãi Trung Hà" in rows[0].context and Decimal(rows[1].price) > 0
