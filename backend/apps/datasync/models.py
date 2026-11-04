"""Nhật ký kiểm tra/cập nhật dữ liệu và danh mục giá vật liệu công bố (tham khảo)."""

from django.conf import settings
from django.db import models

from apps.catalog.models import DatasetRelease


class DataUpdateRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    sources = models.JSONField(default=list, blank=True, help_text="Nguồn cần kiểm tra (rỗng = tất cả)")
    results = models.JSONField(default=list, blank=True)
    log = models.TextField(blank=True)
    error = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class PriceCatalogItem(models.Model):
    """Một dòng trong bảng công bố giá vật liệu (theo nhà sản xuất / địa điểm). Dùng để "áp giá thông báo"
    cho vật liệu trong dự toán: người dùng chọn dòng phù hợp → tạo giá riêng có ghi nguồn."""

    release = models.ForeignKey(DatasetRelease, on_delete=models.CASCADE, related_name="catalog_items")
    name = models.CharField(max_length=500)
    spec = models.CharField(max_length=500, blank=True)
    unit = models.CharField(max_length=30)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    context = models.CharField(max_length=500, blank=True, help_text="Nhóm vật liệu · địa điểm / nhà sản xuất")
    page = models.PositiveIntegerField(default=0)
    document = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["release", "id"]
        indexes = [models.Index(fields=["release", "name"])]
