from django.db import models


class CalculationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    revision = models.ForeignKey("projects.EstimateRevision", on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    engine_version = models.CharField(max_length=20)
    input_hash = models.CharField(max_length=64, blank=True)
    output_hash = models.CharField(max_length=64, blank=True)
    snapshot = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True, help_text="Bảng tổng hợp + tổng hợp vật tư")
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class CalculationLine(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name="lines")
    line = models.ForeignKey("projects.EstimateLine", on_delete=models.CASCADE, related_name="+")
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_vl = models.DecimalField(max_digits=18, decimal_places=2)
    unit_nc = models.DecimalField(max_digits=18, decimal_places=2)
    unit_m = models.DecimalField(max_digits=18, decimal_places=2)
    vl = models.DecimalField(max_digits=20, decimal_places=2)
    nc = models.DecimalField(max_digits=20, decimal_places=2)
    m = models.DecimalField(max_digits=20, decimal_places=2)
    direct = models.DecimalField(max_digits=20, decimal_places=2)
    breakdown = models.JSONField(help_text="Cây giải trình: hao phí, giá, nguồn, làm tròn")
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = [("run", "line")]
