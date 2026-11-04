from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse

INDEX_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SmartEstimator</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 16px;line-height:1.5;color:#1f2937}
code{background:#f3f4f6;padding:2px 6px;border-radius:4px}li{margin:6px 0}
.warn{background:#fff7ed;border-left:4px solid #f59e0b;padding:8px 12px}
</style></head>
<body><h1>SmartEstimator</h1>
<p>Webapp lập dự toán xây dựng theo định mức và đơn giá Việt Nam —
đợt 1 (backend + engine + xuất Excel, API only).</p>
<ul>
<li><a href="/admin/">Quản trị dữ liệu (Django admin)</a></li>
<li><a href="/api/v1/">API v1 (browsable, cần đăng nhập)</a> — <code>POST /api/v1/auth/token</code> để lấy token</li>
<li><a href="/healthz">/healthz</a></li>
</ul>
<p class="warn">Dữ liệu định mức/giá đang là dữ liệu MẪU; rule pack TT 36/2026 chưa được kỹ sư dự toán ký duyệt.</p>
</body></html>"""


def index(request):
    """Serve the React SPA when built, else a plain info page."""
    spa = Path(settings.FRONTEND_DIST) / "index.html"
    if spa.exists():
        return HttpResponse(spa.read_bytes(), content_type="text/html; charset=utf-8")
    return HttpResponse(INDEX_HTML)


def healthz(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db = "ok"
    except Exception as e:  # noqa: BLE001
        return JsonResponse({"status": "error", "db": str(e)}, status=503)
    return JsonResponse({"status": "ok", "db": db})
