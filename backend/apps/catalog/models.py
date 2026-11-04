"""Catalog: source documents, dataset releases, resources, work items and norm components.

Rules (see architecture doc §5):
- Norms/prices are keyed by *release*, never only by code.
- Published releases are immutable; corrections go into a new release.
"""

from django.db import models


class SourceDocument(models.Model):
    """A legal/official document (thông tư, công bố giá, báo giá) that data traces back to."""

    issuer = models.CharField(max_length=200)  # Bộ Xây dựng, Sở XD Hà Nội, ...
    number = models.CharField(max_length=100)  # 36/2026/TT-BXD
    title = models.CharField(max_length=500)
    url = models.URLField(blank=True)
    file = models.FileField(upload_to="sources/", blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    errata_status = models.CharField(
        max_length=200,
        blank=True,
        help_text="Ghi chú đính chính / văn bản hợp nhất chưa áp dụng (nếu có)",
    )
    needs_review_errata = models.BooleanField(default=False)

    class Meta:
        unique_together = [("issuer", "number")]

    def __str__(self):
        return f"{self.number} ({self.issuer})"


class DatasetRelease(models.Model):
    class Kind(models.TextChoices):
        NORM = "NORM", "Định mức"
        PRICE = "PRICE", "Giá"
        RULE = "RULE", "Quy tắc chi phí"
        CATALOG = "CATALOG", "Danh mục giá công bố tham khảo (vật liệu)"

    class Status(models.TextChoices):
        DRAFT = "draft"
        REVIEWED = "reviewed"
        PUBLISHED = "published"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=50)
    region = models.CharField(max_length=100, blank=True)  # tỉnh/thành hoặc "VN"
    effective_from = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    source = models.ForeignKey(SourceDocument, null=True, blank=True, on_delete=models.PROTECT)
    is_sample = models.BooleanField(
        default=False, help_text="TRUE = dữ liệu mẫu minh hoạ, KHÔNG phải số liệu chính thức"
    )
    notes = models.TextField(blank=True)
    meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Thông tin bổ sung: regions, period, documents (nguồn), report (kết quả bóc tách)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("kind", "name", "version")]

    def __str__(self):
        tag = " [SAMPLE]" if self.is_sample else ""
        return f"{self.get_kind_display()} {self.name} v{self.version}{tag}"


class Resource(models.Model):
    """Vật liệu / nhân công / máy — khóa dùng chung giữa định mức và bảng giá."""

    class Kind(models.TextChoices):
        MATERIAL = "MATERIAL", "Vật liệu"
        LABOR = "LABOR", "Nhân công"
        MACHINE = "MACHINE", "Máy thi công"

    code = models.CharField(max_length=50, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=300)
    unit = models.CharField(max_length=30)
    spec = models.CharField(max_length=300, blank=True)
    labor_group = models.CharField(max_length=20, blank=True)  # nhóm nhân công (TT 37)
    labor_grade = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # bậc thợ, vd 3.5/7

    class Meta:
        ordering = ["kind", "code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class WorkItem(models.Model):
    """Mã công tác (vd AF.11111) trong một release định mức."""

    release = models.ForeignKey(DatasetRelease, on_delete=models.PROTECT, related_name="work_items")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=500)
    unit = models.CharField(max_length=30)
    group_code = models.CharField(max_length=30, blank=True)  # chương / nhóm
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("release", "code")]
        ordering = ["code"]
        indexes = [models.Index(fields=["code"]), models.Index(fields=["name"])]

    def __str__(self):
        return f"{self.code} {self.name}"


class NormComponent(models.Model):
    """Hao phí của một nguồn lực cho 1 đơn vị công tác.

    is_other_pct=True → dòng "Vật liệu khác / Máy khác (%)": quantity là % trên tổng chi phí
    VL (hoặc M) chủ yếu, tương ứng K^vl / K^mtc trong công thức 4.1 / 4.4 Phụ lục IV TT 36/2026.
    """

    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="components")
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=Resource.Kind.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    is_other_pct = models.BooleanField(default=False)
    condition = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["kind", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="norm_quantity_non_negative"),
        ]
