"""Pricebook: observed prices per resource, region, period and source."""

from django.db import models

from apps.catalog.models import DatasetRelease, Resource


class PriceObservation(models.Model):
    class SourceKind(models.TextChoices):
        OFFICIAL = "OFFICIAL", "Công bố của cơ quan nhà nước"
        QUOTE = "QUOTE", "Báo giá nhà cung cấp"
        SURVEY = "SURVEY", "Khảo sát của công ty"
        MANUAL = "MANUAL", "Nhập tay có lý do"

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    release = models.ForeignKey(DatasetRelease, on_delete=models.PROTECT, related_name="prices")
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="prices")
    region = models.CharField(max_length=100)
    period = models.CharField(max_length=20, help_text="vd 2026-Q3 hoặc 2026-09")
    price = models.DecimalField(max_digits=18, decimal_places=2, help_text="VND, chưa VAT, đã đến hiện trường")
    unit = models.CharField(max_length=30)
    source_kind = models.CharField(max_length=10, choices=SourceKind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("release", "resource", "region", "period")]
        ordering = ["resource__code", "region", "period"]
        indexes = [models.Index(fields=["resource", "region", "period"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="price_non_negative"),
        ]

    def __str__(self):
        return f"{self.resource.code} {self.region} {self.period}: {self.price}"
