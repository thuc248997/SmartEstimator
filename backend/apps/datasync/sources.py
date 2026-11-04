"""Dò và tải tài liệu nguồn.

- Định mức TT 38/2026: lấy theo danh sách nguồn (manifest).
- Giá Hà Nội: dò bài mới nhất trong mục "Kinh tế – Vật liệu xây dựng" của cổng soxaydung.hanoi.gov.vn
  (API danh sách bài), đọc tệp đính kèm; gộp với bản tải bổ sung trong manifest, chọn văn bản ban hành mới nhất.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .parsers.hanoi_prices import doc_info

UA = "Mozilla/5.0 (X11; Linux x86_64) SmartEstimator-datasync/1.0"
HN_PORTAL = "https://soxaydung.hanoi.gov.vn"
HN_CATEGORY = "/kinh-te-vat-lieu-xay-dung"
TIMEOUT = 90


@dataclass
class Fetched:
    url: str
    path: Path
    sha256: str
    size: int


@dataclass
class Candidate:
    source_id: str
    urls: list[str]
    issuer: str = ""
    number: str = ""
    title: str = ""
    issued_on: str = ""  # ISO
    effective_from: str = ""
    origin: str = ""  # "portal" | "manifest"
    note: str = ""
    period: str = ""
    files: list[Fetched] = field(default_factory=list)
    text: str = ""  # văn bản (pdftotext -layout) của tệp đầu
    texts: list[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        for f in self.files:
            h.update(f.sha256.encode())
        return h.hexdigest()


def cache_dir() -> Path:
    d = Path(settings.MEDIA_ROOT) / "datasources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def http_get(url: str, data: dict | None = None, headers: dict | None = None) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — URL từ danh sách nguồn cố định
        return r.read()


def download(url: str) -> Fetched:
    raw = http_get(url)
    if not raw.startswith(b"%PDF"):
        raise ValueError(f"Tệp tải về không phải PDF: {url}")
    sha = hashlib.sha256(raw).hexdigest()
    path = cache_dir() / f"{sha}.pdf"
    if not path.exists():
        path.write_bytes(raw)
    return Fetched(url, path, sha, len(raw))


def pdf_text(path: Path, layout: bool = True, first: int | None = None, last: int | None = None) -> str:
    args = ["pdftotext"]
    if layout:
        args.append("-layout")
    if first:
        args += ["-f", str(first)]
    if last:
        args += ["-l", str(last)]
    out = subprocess.run([*args, str(path), "-"], capture_output=True, check=True, timeout=600)
    return out.stdout.decode("utf-8", errors="replace")


def pdf_bbox(path: Path) -> str:
    with tempfile.NamedTemporaryFile(suffix=".html") as tmp:
        subprocess.run(["pdftotext", "-bbox", str(path), tmp.name], check=True, timeout=900)
        return Path(tmp.name).read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- manifest


def load_manifest() -> dict:
    local = json.loads((Path(settings.BASE_DIR) / "fixtures" / "data_sources.json").read_text(encoding="utf-8"))
    url = getattr(settings, "DATA_MANIFEST_URL", "")
    if url:
        try:
            remote = json.loads(http_get(url).decode("utf-8"))
            for sid, entry in remote.get("sources", {}).items():
                local["sources"].setdefault(sid, {"mirrors": []})
                local["sources"][sid]["mirrors"] = entry.get("mirrors", []) + local["sources"][sid].get("mirrors", [])
                if "known_newer" in entry:
                    local["sources"][sid]["known_newer"] = entry["known_newer"]
            local["remote_manifest"] = url
        except Exception as e:  # noqa: BLE001 — manifest từ xa là tùy chọn
            local["remote_manifest_error"] = f"{type(e).__name__}: {e}"
    return local


def manifest_candidates(manifest: dict, sid: str) -> list[Candidate]:
    out = []
    for m in manifest.get("sources", {}).get(sid, {}).get("mirrors", []):
        out.append(
            Candidate(
                source_id=sid,
                urls=[m["url"]] if isinstance(m.get("url"), str) else list(m.get("urls", [])),
                issuer=m.get("issuer", ""),
                number=m.get("number", ""),
                title=m.get("title", ""),
                issued_on=m.get("issued_on", ""),
                effective_from=m.get("effective_from", ""),
                origin="manifest",
                note=m.get("note", ""),
                period=m.get("period", ""),
            )
        )
    return out


# --------------------------------------------------------------------------- cổng Sở Xây dựng Hà Nội


def _hn_posts() -> list[tuple[str, str]]:
    """(tiêu đề, đường dẫn) các bài trong mục Kinh tế – VLXD, mới nhất trước."""
    page = http_get(HN_PORTAL + HN_CATEGORY).decode("utf-8", errors="ignore")

    def var(name: str) -> str:
        m = re.search(rf"{name}\s*=\s*'([^']*)'", page)
        return m.group(1) if m else ""

    sizes = re.findall(r'<option value="([^"]+)">(\d+)</option>', page)
    size_token = next((v for v, n in sizes if n == "50"), sizes[0][0] if sizes else "")
    posts: list[tuple[str, str]] = []
    for idx in range(2):
        chunk = http_get(
            HN_PORTAL + "/api/NewsZone/NewsZone",
            data={
                "PageIndex": idx,
                "PageSize": size_token,
                "Catname": var("mo_CatName"),
                "LanguageId": var("mo_LanguageId"),
                "ZoomSize": var("mo_ZoomSize"),
                "Site": var("mo_SiteId"),
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": HN_PORTAL + HN_CATEGORY},
        ).decode("utf-8", errors="ignore")
        for href, title in re.findall(r'href="([^"]+\.htm)"[^>]*title="([^"]*)"', chunk):
            item = (html.unescape(title).strip(), href)
            if item not in posts:
                posts.append(item)
    return posts


def _hn_attachments(href: str) -> list[str]:
    page = http_get(HN_PORTAL + href if href.startswith("/") else href).decode("utf-8", errors="ignore")
    return sorted(set(re.findall(r"https?://[^\"' ]+\.pdf", page)))


HN_PATTERNS = {
    "hn-labor": re.compile(r"(?i)công bố (đơn )?giá nhân công"),
    "hn-machine": re.compile(r"(?i)giá ca máy"),
    "hn-material": re.compile(r"(?i)công bố giá (một số )?vật liệu xây dựng (quý|tháng)"),
}


def hn_portal_candidate(sid: str) -> Candidate | None:
    pat = HN_PATTERNS[sid]
    for title, href in _hn_posts():
        if pat.search(title):
            urls = _hn_attachments(href)
            if sid == "hn-material":
                # phụ lục giá (bỏ quyết định / văn bản kèm)
                urls = [u for u in urls if "phu-luc" in u.lower()] or urls
            if not urls:
                continue
            period = ""
            m = re.search(r"(?i)quý\s+([IV]+)\s*(?:năm\s*)?/?\s*(\d{4})", title)
            if m:
                period = f"{m.group(2)}-Q{['I', 'II', 'III', 'IV'].index(m.group(1).upper()) + 1}"
            return Candidate(
                sid,
                urls,
                issuer="Sở Xây dựng Hà Nội",
                title=title,
                origin="portal",
                period=period,
                note=HN_PORTAL + href,
            )
    return None


def fill_doc_info(c: Candidate) -> None:
    """Tải tệp và đọc số hiệu / ngày ban hành từ trang đầu nếu manifest chưa ghi."""
    c.files = [download(u) for u in c.urls]
    if not c.number or not c.issued_on:
        info = doc_info(pdf_text(c.files[0].path, first=1, last=3))
        c.number = c.number or info.number
        c.issued_on = c.issued_on or info.issued_on
        c.title = c.title or info.title
