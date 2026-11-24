from django.db import models

from apps.catalog.models import DatasetRelease, WorkItem


class BoqMatchMemory(models.Model):
    """Ghi nhớ lựa chọn mã của người lập dự toán: lần sau gặp đúng tên công tác + loại đơn vị
    trong BoQ thì gợi ý luôn mã đó (độ tin cậy cao), không phải chọn lại."""

    release = models.ForeignKey(DatasetRelease, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=500, help_text="Tên công tác BoQ đã chuẩn hóa (bỏ dấu, viết thường)")
    unit_base = models.CharField(max_length=30, blank=True)
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="+")
    hits = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("release", "key", "unit_base")]
        verbose_name = "Ghi nhớ ghép mã BoQ"

    def __str__(self):
        return f"{self.key} → {self.work_item.code}"
