"""Regulations: versioned cost rule packs (tỷ lệ chi phí chung, TNCTTT, VAT, nhà tạm...)."""

from django.db import models

from apps.catalog.models import SourceDocument


class CostRulePack(models.Model):
    code = models.CharField(max_length=50)
    version = models.CharField(max_length=20)
    title = models.CharField(max_length=300)
    source = models.ForeignKey(SourceDocument, null=True, blank=True, on_delete=models.PROTECT)
    effective_from = models.DateField(null=True, blank=True)
    data = models.JSONField(help_text="Bảng tỷ lệ và tham số đã kiểm duyệt; xem fixtures/rule_pack_tt36_2026.json")
    is_approved = models.BooleanField(default=False)
    approval_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("code", "version")]
        ordering = ["code", "-version"]

    def __str__(self):
        return f"{self.code} v{self.version}"
