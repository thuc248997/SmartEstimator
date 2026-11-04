"""Luồng cập nhật: nạp định mức + giá (giả lập tải về), lần 2 báo 'đã là bản mới nhất'; API trạng thái và tra giá VL."""

from pathlib import Path

import pytest

from apps.catalog.models import DatasetRelease, WorkItem
from apps.datasync import service, sources
from apps.datasync.models import DataUpdateRun
from apps.pricebook.models import PriceObservation

from .test_parsers import AF111, LABOR_TXT, MACHINE_TXT, _bbox

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_sources(monkeypatch, tmp_path):
    files = {
        "https://x/tt38.pdf": b"%PDF tt38",
        "https://x/labor.pdf": b"%PDF labor",
        "https://x/machine.pdf": b"%PDF machine",
        "https://x/vl.pdf": b"%PDF vl",
    }
    texts = {
        "https://x/labor.pdf": LABOR_TXT,
        "https://x/machine.pdf": MACHINE_TXT,
        "https://x/vl.pdf": "      I - NHÓM VẬT LIỆU CÁT:\n      Bãi A\n 1    Cát vàng     m3     636.364\n",
    }
    by_path = {}

    def download(url):
        import hashlib

        raw = files[url]
        p = tmp_path / (hashlib.sha256(raw).hexdigest() + ".pdf")
        p.write_bytes(raw)
        by_path[str(p)] = url
        return sources.Fetched(url, p, hashlib.sha256(raw).hexdigest(), len(raw))

    manifest = {
        "sources": {
            "tt38-2026": {
                "mirrors": [
                    {
                        "url": "https://x/tt38.pdf",
                        "issuer": "Bộ Xây dựng",
                        "number": "38/2026/TT-BXD",
                        "issued_on": "2026-06-26",
                    }
                ]
            },
            "hn-labor": {"mirrors": [{"url": "https://x/labor.pdf", "issuer": "Sở Xây dựng Hà Nội"}]},
            "hn-machine": {
                "mirrors": [
                    {
                        "url": "https://x/machine.pdf",
                        "issuer": "Sở Xây dựng Hà Nội",
                        "number": "2037/QĐ-SXD",
                        "issued_on": "2026-10-26",
                    }
                ],
                "known_newer": [{"number": "2075/QĐ-SXD", "issued_on": "2026-10-31", "note": "chưa có tệp"}],
            },
            "hn-material": {
                "mirrors": [
                    {
                        "url": "https://x/vl.pdf",
                        "issuer": "Sở Xây dựng Hà Nội",
                        "number": "CBG-Q3",
                        "issued_on": "2026-10-19",
                        "period": "2026-Q3",
                    }
                ]
            },
        }
    }
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(service, "load_manifest", lambda: manifest)
    monkeypatch.setattr(service, "hn_portal_candidate", lambda sid: None)
    monkeypatch.setattr(service, "pdf_text", lambda path, **kw: texts.get(by_path.get(str(path)), LABOR_TXT))
    monkeypatch.setattr(sources, "pdf_text", lambda path, **kw: texts.get(by_path.get(str(path)), LABOR_TXT))
    # bảng AF.111 lặp lại để vượt ngưỡng an toàn 1.000 mã
    monkeypatch.setattr(service, "pdf_bbox", lambda path: _bbox(AF111))
    real = service.tt38.parse_tt38

    def many(bbox):
        recs, rep = real(bbox)
        out = []
        for i in range(600):
            for r in recs:
                r2 = type(r)(**{**r.__dict__, "code": f"ZZ.{i:03d}{r.code[-2:]}", "components": r.components})
                out.append(r2)
        return out, rep

    monkeypatch.setattr(service.tt38, "parse_tt38", many)
    monkeypatch.setattr(service, "MIN_MACHINE_ROWS", 2)
    return Path(tmp_path)


def test_update_then_up_to_date(fake_sources, admin_client):
    r = admin_client.post("/api/v1/data-updates", {}, format="json")
    assert r.status_code == 201, r.content
    run = DataUpdateRun.objects.get(pk=r.data["id"])
    st = {x["source"]: x for x in run.results}
    assert [st[s]["status"] for s in ("tt38-2026", "hn-prices", "hn-material")] == ["updated"] * 3, run.log
    assert any("2075/QĐ-SXD" in w for w in st["hn-prices"]["warnings"])
    norm = DatasetRelease.objects.get(pk=st["tt38-2026"]["release_id"])
    assert WorkItem.objects.filter(release=norm).count() == 1200 and not norm.is_sample
    price = DatasetRelease.objects.get(pk=st["hn-prices"]["release_id"])
    assert price.meta["regions"] == ["Hà Nội - Vùng I", "Hà Nội - Vùng II"] and price.meta["period"] == "2026-10"
    labor = PriceObservation.objects.get(release=price, resource__code="NC.N2", region="Hà Nội - Vùng I")
    assert labor.price == 428000
    mixer = PriceObservation.objects.filter(release=price, resource__name="Máy trộn 250l")
    assert not mixer.exists()  # bảng máy mẫu không có máy trộn 250 lít → không ghép bừa

    again = admin_client.post("/api/v1/data-updates", {}, format="json").data
    assert [x["status"] for x in again["results"]] == ["up_to_date"] * 3
    assert DatasetRelease.objects.filter(kind="NORM", is_sample=False).count() == 1

    status = admin_client.get("/api/v1/data-status").data
    assert status["can_update"] and status["last_run"]["id"] == again["id"]
    items = admin_client.get("/api/v1/catalog/price-items", {"query": "cát,vàng"}).data
    assert items["results"][0]["price"] == "636364.00" and items["results"][0]["period"] == "2026-Q3"


def test_only_staff_can_update(client):
    assert client.post("/api/v1/data-updates", {}, format="json").status_code == 403
