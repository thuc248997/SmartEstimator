"""Projects: công trình → revision → hạng mục → dòng công tác."""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.catalog.models import DatasetRelease, Resource, WorkItem
from apps.regulations.models import CostRulePack


class ConstructionType(models.TextChoices):
    """Loại công trình theo Bảng 3.3/3.5/3.6 Phụ lục III TT 36/2026 (keys khớp rule pack JSON)."""

    CIVIL = "CIVIL", "Công trình dân dụng"
    HERITAGE = "HERITAGE", "Tu bổ, phục hồi di tích"
    INDUSTRIAL = "INDUSTRIAL", "Công trình công nghiệp"
    HYDRO_TUNNEL = "HYDRO_TUNNEL", "Đường hầm thủy điện, hầm lò"
    TRANSPORT = "TRANSPORT", "Công trình giao thông"
    TRANSPORT_TUNNEL = "TRANSPORT_TUNNEL", "Hầm giao thông"
    AGRI_ENV = "AGRI_ENV", "Nông nghiệp và môi trường"
    AGRI_TUNNEL = "AGRI_TUNNEL", "Đường hầm (NN&MT)"
    INFRA = "INFRA", "Hạ tầng kỹ thuật"
    EQUIPMENT_INSTALL = "EQUIPMENT_INSTALL", "Lắp đặt thiết bị công nghệ / đường dây & TBA / thí nghiệm hiệu chỉnh"


class Project(models.Model):
    class OverheadBasis(models.TextChoices):
        DIRECT = "DIRECT", "Trên chi phí trực tiếp (Bảng 3.3)"
        LABOR = "LABOR", "Trên chi phí nhân công (Bảng 3.4)"

    name = models.CharField(max_length=300)
    code = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=300, blank=True)
    investor = models.CharField(max_length=300, blank=True, help_text="Chủ đầu tư")
    consultant = models.CharField(max_length=300, blank=True, help_text="Đơn vị lập dự toán / tư vấn")
    preparer = models.CharField(max_length=150, blank=True, help_text="Người lập")
    checker = models.CharField(max_length=150, blank=True, help_text="Người kiểm tra / chủ trì")
    region = models.CharField(max_length=100, help_text="Địa phương lấy giá, khớp PriceObservation.region")
    price_period = models.CharField(max_length=20, help_text="Kỳ giá, khớp PriceObservation.period")
    construction_type = models.CharField(max_length=30, choices=ConstructionType.choices)
    overhead_basis = models.CharField(max_length=10, choices=OverheadBasis.choices, default=OverheadBasis.DIRECT)
    labor_overhead_row = models.CharField(
        max_length=40, blank=True, help_text="Dòng Bảng 3.4 khi overhead_basis=LABOR (vd EQUIPMENT_INSTALL)"
    )
    is_remote_area = models.BooleanField(default=False, help_text="Vùng núi/biên giới/biển/hải đảo → hệ số 1,1")
    is_linear = models.BooleanField(default=False, help_text="Công trình theo tuyến (Bảng 3.7)")
    is_feasibility_report_only = models.BooleanField(
        default=False, help_text="Dự án chỉ lập báo cáo KT-KT → cột ≤40 Bảng 3.3"
    )
    approved_construction_cost_bn = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Chi phí XD trước thuế của công trình trong TMĐT được duyệt (tỷ đồng) để chọn ngưỡng; "
        "để trống → lấy theo kết quả tính",
    )
    rule_pack = models.ForeignKey(CostRulePack, on_delete=models.PROTECT)
    norm_release = models.ForeignKey(DatasetRelease, on_delete=models.PROTECT, related_name="+")
    price_release = models.ForeignKey(DatasetRelease, on_delete=models.PROTECT, related_name="+")
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True, help_text="Ghi đè VAT của rule pack (vd 0.08)"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class EstimateRevision(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        REVIEW = "review"
        APPROVED = "approved"
        ISSUED = "issued"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    snapshot = models.JSONField(null=True, blank=True, help_text="Input snapshot bị khóa khi approve")
    content_hash = models.CharField(max_length=64, blank=True)
    approved_run = models.ForeignKey(
        "calculation.CalculationRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "number")]
        ordering = ["project", "number"]

    @property
    def is_locked(self) -> bool:
        return self.status in (self.Status.APPROVED, self.Status.ISSUED)

    def lines_qs(self):
        return EstimateLine.objects.filter(item__revision=self)

    def __str__(self):
        return f"{self.project.name} / rev {self.number}"


class ProjectItem(models.Model):
    """Hạng mục công trình."""

    revision = models.ForeignKey(EstimateRevision, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=300)

    class Meta:
        ordering = ["revision", "order", "id"]

    def __str__(self):
        return self.name


class EstimateLine(models.Model):
    """Một dòng công tác trong tiên lượng."""

    item = models.ForeignKey(ProjectItem, on_delete=models.CASCADE, related_name="lines")
    order = models.PositiveIntegerField(default=0)
    work_item = models.ForeignKey(WorkItem, null=True, blank=True, on_delete=models.PROTECT)
    custom_code = models.CharField(max_length=30, blank=True, help_text="Mã tạm tính / vận dụng khi không có work_item")
    name = models.CharField(max_length=500)
    unit = models.CharField(max_length=30)
    quantity_expr = models.TextField(blank=True, help_text="Công thức khối lượng, vd 2*(3.5+4.2)*0.22")
    quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    k_nc = models.DecimalField(max_digits=6, decimal_places=4, default=1, help_text="Hệ số NC làm đêm/lễ (Knc)")
    k_m = models.DecimalField(max_digits=6, decimal_places=4, default=1, help_text="Hệ số máy làm đêm/lễ (Km)")
    note = models.CharField(max_length=500, blank=True)
    details = models.JSONField(
        default=list,
        blank=True,
        help_text="Diễn giải khối lượng: [{text, expr, n, l, w, h, value}]; khi có → quantity = Σ value",
    )
    manual_vl = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, help_text="Đơn giá VL tạm tính (nhập tay)"
    )
    manual_nc = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    manual_m = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    version = models.PositiveIntegerField(default=1, help_text="Optimistic concurrency")

    class Meta:
        ordering = ["item", "order", "id"]

    @property
    def code(self) -> str:
        return self.work_item.code if self.work_item_id else self.custom_code


class ResourceOverride(models.Model):
    """Giá nhập tay cho một nguồn lực trong một revision (không ghi đè dữ liệu gốc)."""

    revision = models.ForeignKey(EstimateRevision, on_delete=models.CASCADE, related_name="overrides")
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("revision", "resource")]


class EquipmentCost(models.Model):
    """Chi phí thiết bị (sheet TH chi phí thiết bị) — tách khỏi chi phí xây dựng."""

    revision = models.ForeignKey(EstimateRevision, on_delete=models.CASCADE, related_name="equipment")
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=500)
    unit = models.CharField(max_length=30, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Đơn giá trước thuế")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.10"))
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["revision", "order", "id"]
